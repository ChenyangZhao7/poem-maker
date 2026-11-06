from __future__ import annotations

from typing import Sequence

from eh_poem_style.cipai import Cipai
from eh_poem_style.models import Issue, PoemDraft, Report
from eh_poem_style.pingze import cjk, tone_of_line
from eh_poem_style.xinyun import rhyme_groups as char_rhyme_groups


def validate_ci(
    draft: PoemDraft,
    cipai: Cipai,
    rhyme_groups: Sequence[str],
) -> Report:
    rhyme_lines = cipai.rhyme_lines
    if len(rhyme_groups) != len(rhyme_lines):
        raise ValueError(
            f"韵部数量 {len(rhyme_groups)} 与谱的韵位 {len(rhyme_lines)} 不一致"
        )

    issues: list[Issue] = []
    lines = [cjk(line) for line in draft.lines]

    if len(lines) != cipai.line_count:
        issues.append(
            Issue(
                "error",
                "line_count",
                f"《{cipai.name}》应为 {cipai.line_count} 句，实际 {len(lines)} 句",
            )
        )

    for line_no, (line, spec_line) in enumerate(zip(lines, cipai.lines), start=1):
        if len(line) != len(spec_line.pattern):
            issues.append(
                Issue(
                    "error",
                    "line_length",
                    f"第 {line_no} 句 {len(line)} 字，应为 {len(spec_line.pattern)} 字",
                    line=line_no,
                )
            )
            continue

        tones = tone_of_line(line)
        for index, (char, expected) in enumerate(
            zip(line, spec_line.pattern), start=1
        ):
            if expected == "中":
                continue
            actual = tones[index - 1] if index - 1 < len(tones) else None
            if actual is None:
                issues.append(
                    Issue(
                        "error",
                        "unknown_char",
                        f"第 {line_no} 句第 {index} 字「{char}」无法判定平仄",
                        line=line_no,
                        index=index,
                    )
                )
            elif actual != expected:
                issues.append(
                    Issue(
                        "error",
                        "tone_mismatch",
                        f"第 {line_no} 句第 {index} 字「{char}」应{expected}实{actual}",
                        line=line_no,
                        index=index,
                    )
                )

    rhyme_index = 0
    for line_no, spec_line in enumerate(cipai.lines, start=1):
        if not spec_line.rhyme:
            continue
        required = rhyme_groups[rhyme_index]
        rhyme_index += 1
        line = lines[line_no - 1] if line_no - 1 < len(lines) else ""
        if not line:
            issues.append(
                Issue(
                    "error",
                    "rhyme_mismatch",
                    f"第 {line_no} 句为空，无法取韵脚",
                    line=line_no,
                )
            )
            continue

        char = line[-1]
        groups = char_rhyme_groups(char)
        if not groups:
            issues.append(
                Issue(
                    "error",
                    "unknown_char",
                    f"第 {line_no} 句韵脚「{char}」无法判定韵部",
                    line=line_no,
                    index=len(line),
                )
            )
        elif required not in groups:
            issues.append(
                Issue(
                    "error",
                    "rhyme_mismatch",
                    f"第 {line_no} 句韵脚「{char}」属 {'/'.join(sorted(groups))}，要求 {required}",
                    line=line_no,
                    index=len(line),
                )
            )

        if spec_line.rhyme_tone is not None:
            tones = tone_of_line(line)
            actual = tones[-1] if tones else None
            if actual != spec_line.rhyme_tone:
                issues.append(
                    Issue(
                        "error",
                        "rhyme_tone_mismatch",
                        f"第 {line_no} 句韵脚「{char}」应{spec_line.rhyme_tone}实{actual or '未知'}",
                        line=line_no,
                        index=len(line),
                    )
                )

    return Report(tuple(issues))
