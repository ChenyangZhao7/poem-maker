from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence

from eh_poem_style.cipai import Cipai
from eh_poem_style.corpus import Poem
from eh_poem_style.llm import LLMError
from eh_poem_style.models import GenerateRequest, Issue, PoemDraft, Report
from eh_poem_style.pingze import cjk, tone_of_char
from eh_poem_style.prompt import (
    DraftParseError,
    PromptContext,
    build_messages,
    parse_draft,
)
from eh_poem_style.style import StyleStats
from eh_poem_style.validate.ci import validate_ci
from eh_poem_style.validate.shi import ShiSpec, spec_for_genre, validate_shi
from eh_poem_style.xinyun import candidates as rhyme_candidates
from eh_poem_style.xinyun import rhyme_groups as char_rhyme_groups


@dataclass(frozen=True)
class GenerationResult:
    draft: PoemDraft
    report: Report
    attempts: int
    run_dir: Path


@dataclass(frozen=True)
class Constraints:
    shi_spec: ShiSpec | None
    rhyme_groups: tuple[str, ...]
    candidate_chars: tuple[str, ...]


def check_copy(
    lines: Sequence[str], seed_lines: Sequence[str]
) -> tuple[Issue, ...]:
    seed = {cjk(line) for line in seed_lines}
    issues: list[Issue] = []
    for index, line in enumerate(lines, start=1):
        clean = cjk(line)
        if clean and clean in seed:
            issues.append(
                Issue(
                    "error",
                    "copy_line",
                    f"第 {index} 句整句照抄原作：{clean}",
                    line=index,
                )
            )
    return tuple(issues)


def _has_tone(char: str, group: str, tone: str) -> bool:
    return tone_of_char(char) == tone and group in char_rhyme_groups(char)


def _pick_group(
    counter,
    tone: str | None,
    chars: Iterable[str],
    fallback: str,
) -> str:
    chars = list(chars)
    if counter:
        for group, _ in counter.most_common():
            if tone is None or any(_has_tone(ch, group, tone) for ch in chars):
                return group
    return fallback


def prepare_constraints(
    request: GenerateRequest,
    cipai: Cipai | None,
    stats: StyleStats | None,
    chars: Iterable[str],
) -> Constraints:
    char_list = list(chars)

    if request.genre != "词":
        if request.rhyme_group:
            group: str | None = request.rhyme_group
        elif stats is not None and stats.shi_rhyme_groups:
            group = _pick_group(stats.shi_rhyme_groups, None, char_list, "十唐")
        else:
            group = None
        spec = spec_for_genre(
            request.genre,
            line_length=request.line_length,
            first_rhyme=request.first_rhyme,
            rhyme_group=group,
        )
        return Constraints(
            shi_spec=spec,
            rhyme_groups=(group,) if group else (),
            candidate_chars=(
                tuple(rhyme_candidates(group, char_list)) if group else ()
            ),
        )

    if cipai is None:
        raise ValueError("生成词时必须提供词牌")
    groups: list[str] = []
    previous_tone: str | None = None
    previous_group: str | None = None
    for line in cipai.rhyme_lines:
        tone = line.rhyme_tone or "平"
        if tone == previous_tone and previous_group is not None:
            group = previous_group
        elif request.rhyme_group and any(
            _has_tone(ch, request.rhyme_group, tone) for ch in char_list
        ):
            group = request.rhyme_group
        elif stats is not None:
            group = _pick_group(
                stats.ci_rhyme_groups,
                tone,
                char_list,
                "十唐" if tone == "平" else "七尤",
            )
        else:
            group = "十唐" if tone == "平" else "七尤"
        groups.append(group)
        previous_tone = tone
        previous_group = group

    all_candidates: list[str] = []
    for group in groups:
        for char in rhyme_candidates(group, char_list):
            if char not in all_candidates:
                all_candidates.append(char)

    return Constraints(
        shi_spec=None,
        rhyme_groups=tuple(groups),
        candidate_chars=tuple(all_candidates),
    )


def _slug(text: str) -> str:
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", text).strip("-")
    return slug[:24] or "run"


def _write_run(
    run_dir: Path,
    request: GenerateRequest,
    attempts: Sequence[tuple[str, PoemDraft | None]],
    draft: PoemDraft | None,
    report: Report,
) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "request.json").write_text(
        json.dumps(asdict(request), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    for index, (raw, parsed) in enumerate(attempts, start=1):
        (run_dir / f"attempt-{index}.txt").write_text(raw, encoding="utf-8")
        if parsed is not None:
            (run_dir / f"attempt-{index}.json").write_text(
                json.dumps(asdict(parsed), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
    if draft is not None:
        (run_dir / "draft.md").write_text(
            f"# {draft.title}\n\n" + "\n".join(draft.lines) + "\n",
            encoding="utf-8",
        )
    report_lines = ["# 校验报告", ""]
    if report.ok:
        report_lines.append("通过")
    for issue in report.issues:
        location = []
        if issue.line is not None:
            location.append(f"第 {issue.line} 句")
        if issue.index is not None:
            location.append(f"第 {issue.index} 字")
        prefix = " ".join(location)
        report_lines.append(
            f"- [{issue.level}] {issue.code} {prefix} {issue.message}".strip()
        )
    (run_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def generate(
    request: GenerateRequest,
    client,
    style_card: str,
    examples: Sequence[Poem],
    cipai: Cipai | None,
    stats: StyleStats | None,
    runs_dir: Path = Path("runs"),
) -> GenerationResult:
    chars = [ch for poem in examples for line in poem.lines for ch in cjk(line)]
    constraints = prepare_constraints(request, cipai, stats, chars)
    ctx = PromptContext(
        style_card=style_card,
        examples=examples,
        spec=constraints.shi_spec,
        cipai=cipai,
        rhyme_groups=constraints.rhyme_groups,
        candidate_chars=constraints.candidate_chars,
    )
    messages = build_messages(request, ctx)
    run_dir = runs_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{_slug(request.prompt)}"

    attempts: list[tuple[str, PoemDraft | None]] = []
    draft: PoemDraft | None = None
    report = Report()
    seed_lines = [line for poem in examples for line in poem.lines]

    max_attempts = max(1, request.max_attempts)
    for attempt in range(1, max_attempts + 1):
        try:
            raw = client.complete(
                messages,
                response_format={"type": "json_object"},
            )
        except LLMError as exc:
            attempts.append(("", None))
            report = Report((Issue("error", "llm_error", str(exc)),))
            if attempt < max_attempts:
                continue
            break

        parsed: PoemDraft | None = None
        try:
            parsed = parse_draft(raw)
        except DraftParseError as exc:
            report = Report((Issue("error", "parse_error", str(exc)),))
        else:
            if request.genre == "词":
                if cipai is None:
                    raise ValueError("生成词时必须提供词牌")
                report = validate_ci(parsed, cipai, constraints.rhyme_groups)
            else:
                if constraints.shi_spec is None:
                    raise ValueError("生成诗时缺少诗规格")
                report = validate_shi(parsed, constraints.shi_spec)
            report = Report(report.issues + check_copy(parsed.lines, seed_lines))
            draft = parsed
        attempts.append((raw, parsed))

        if report.ok:
            break
        if attempt < max_attempts:
            messages = messages + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "上一版校验未通过："
                    + "；".join(issue.message for issue in report.issues)
                    + "。只改错处，保留已合规部分，仍只输出 JSON。",
                },
            ]

    _write_run(run_dir, request, attempts, draft, report)
    if draft is None:
        draft = PoemDraft(
            title="",
            genre=request.genre,
            cipai=request.cipai,
            lines=[],
        )
    return GenerationResult(
        draft=draft,
        report=report,
        attempts=len(attempts),
        run_dir=run_dir,
    )
