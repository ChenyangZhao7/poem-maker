from __future__ import annotations

import difflib
import json
import re
import shutil
from dataclasses import dataclass
from datetime import date
from pathlib import Path

_TITLE_RE = re.compile(r"^##\s+(\d+)\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Poem:
    title: str
    lines: tuple[str, ...]
    genre: str
    cipai: str | None
    raw: str


def detect_cipai(title: str) -> str | None:
    if "·" not in title:
        return None
    left = title.split("·", 1)[0].strip()
    left = re.sub(r"^\d+\s+", "", left).strip()
    return left or None


def parse_seed_markdown(text: str) -> tuple[list[Poem], list[str]]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_TITLE_RE.finditer(text))
    poems: list[Poem] = []
    dupes: list[str] = []
    seen: set[tuple[str, ...]] = set()

    for index, match in enumerate(matches):
        number = match.group(1)
        raw_title = match.group(2).strip()
        full_title = f"{number} {raw_title}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        lines = tuple(
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.lstrip().startswith(">")
        )
        if not lines:
            continue
        key = tuple(lines)
        if key in seen:
            dupes.append(full_title)
            continue
        seen.add(key)
        cipai = detect_cipai(raw_title)
        poems.append(
            Poem(
                title=full_title,
                lines=lines,
                genre="词" if cipai else "诗",
                cipai=cipai,
                raw="\n".join(lines),
            )
        )
    return poems, dupes


def import_seed(src: Path, dst: Path) -> tuple[int, list[str]]:
    if src.resolve() != dst.resolve():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    poems, dupes = parse_seed_markdown(dst.read_text(encoding="utf-8"))
    return len(poems), dupes


def _metadata(run_dir: Path, original: str) -> tuple[str, str, str | None]:
    title = "untitled"
    genre = "诗"
    cipai: str | None = None

    request_path = run_dir / "request.json"
    if request_path.exists():
        data = json.loads(request_path.read_text(encoding="utf-8"))
        genre = str(data.get("genre") or genre)
        raw_cipai = data.get("cipai")
        cipai = str(raw_cipai) if raw_cipai else None

    attempt_path = run_dir / "attempt-1.json"
    if attempt_path.exists():
        data = json.loads(attempt_path.read_text(encoding="utf-8"))
        title = str(data.get("title") or title)
        genre = str(data.get("genre") or genre)
        raw_cipai = data.get("cipai")
        if raw_cipai:
            cipai = str(raw_cipai)

    first = original.splitlines()[0].strip() if original.splitlines() else ""
    if first.startswith("# "):
        title = first[2:].strip() or title
    return title, genre, cipai


def accept_run(
    run_id: str,
    edited_path: Path | None = None,
    runs_dir: Path = Path("runs"),
    poems_dir: Path = Path("corpus/poems"),
) -> Path:
    run_dir = runs_dir / run_id
    original = (run_dir / "draft.md").read_text(encoding="utf-8")
    edited = (
        edited_path.read_text(encoding="utf-8")
        if edited_path is not None
        else original
    )
    title, genre, cipai = _metadata(run_dir, original)

    diff_lines = list(
        difflib.unified_diff(
            original.splitlines(),
            edited.splitlines(),
            fromfile="draft",
            tofile="edited",
            lineterm="",
        )
    )
    diff = "\n".join(diff_lines) if diff_lines else "（无修改）"

    today = date.today()
    slug = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-")[:40] or "untitled"
    out = poems_dir / f"{today:%Y}" / f"{today:%m}" / f"{today:%Y-%m-%d}-{slug}.md"
    out.parent.mkdir(parents=True, exist_ok=True)

    cipai_value = json.dumps(cipai, ensure_ascii=False) if cipai else "null"
    content = (
        "---\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"date: {today:%Y-%m-%d}\n"
        f"genre: {json.dumps(genre, ensure_ascii=False)}\n"
        f"cipai: {cipai_value}\n"
        "status: final\n"
        "source: generated\n"
        "---\n\n"
        f"{edited.strip()}\n\n"
        "## 修改记录\n\n"
        "```diff\n"
        f"{diff}\n"
        "```\n"
    )
    out.write_text(content, encoding="utf-8")
    return out
