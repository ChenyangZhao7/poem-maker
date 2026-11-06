from __future__ import annotations

from dataclasses import dataclass

from eh_poem_style.models import Issue, PoemDraft, Report
from eh_poem_style.xinyun import resolve_rhyme


@dataclass(frozen=True)
class ShiSpec:
    genre: str
    line_length: int
    line_count: int | None
    first_rhyme: bool
    rhyme_group: str | None = None


_GENRES: dict[str, tuple[int, int | None]] = {
    "五律": (5, 8),
    "七律": (7, 8),
    "五绝": (5, 4),
    "七绝": (7, 4),
}


def spec_for_genre(
    genre: str,
    line_length: int = 5,
    first_rhyme: bool = True,
    rhyme_group: str | None = None,
) -> ShiSpec:
    if genre == "古体":
        return ShiSpec(genre, line_length, None, first_rhyme, rhyme_group)
    try:
        length, count = _GENRES[genre]
    except KeyError as exc:
        raise ValueError(f"未知诗体裁：{genre}") from exc
    return ShiSpec(genre, length, count, first_rhyme, rhyme_group)


def strip_punctuation(line: str) -> str:
    return "".join(ch for ch in line if "\u3400" <= ch <= "\u9fff")


def validate_shi(draft: PoemDraft, spec: ShiSpec) -> Report:
    issues: list[Issue] = []
    lines = [strip_punctuation(line) for line in draft.lines]

    if spec.line_count is not None and len(lines) != spec.line_count:
        issues.append(
            Issue(
                "error",
                "line_count",
                f"{spec.genre} 应为 {spec.line_count} 句，实际 {len(lines)} 句",
            )
        )

    for line_no, line in enumerate(lines, start=1):
        if len(line) != spec.line_length:
            issues.append(
                Issue(
                    "error",
                    "line_length",
                    f"第 {line_no} 句 {len(line)} 字，应为 {spec.line_length} 字",
                    line=line_no,
                )
            )

    rhyme_indices = [index for index in range(len(lines)) if index % 2 == 1]
    if spec.first_rhyme and lines:
        rhyme_indices.insert(0, 0)

    rhyme_chars: list[str] = []
    for index in rhyme_indices:
        line = lines[index] if index < len(lines) else ""
        if not line:
            issues.append(
                Issue(
                    "error",
                    "rhyme_mismatch",
                    f"第 {index + 1} 句为空，无法取韵脚",
                    line=index + 1,
                )
            )
            continue
        rhyme_chars.append(line[-1])

    if rhyme_chars:
        resolution = resolve_rhyme(rhyme_chars, preferred=spec.rhyme_group)
        if resolution.group is None:
            issues.append(
                Issue(
                    "error",
                    "rhyme_mismatch",
                    f"韵脚 {'/'.join(rhyme_chars)} 不属于同一韵部",
                )
            )
        elif spec.rhyme_group is not None and resolution.group != spec.rhyme_group:
            issues.append(
                Issue(
                    "error",
                    "rhyme_mismatch",
                    f"韵脚属 {resolution.group}，要求 {spec.rhyme_group}",
                )
            )
        for note in resolution.notes:
            issues.append(Issue("warning", "polyphony", note))

        if len(set(rhyme_chars)) != len(rhyme_chars):
            issues.append(
                Issue(
                    "error",
                    "duplicate_rhyme",
                    f"韵脚重复：{'/'.join(rhyme_chars)}",
                )
            )

    return Report(tuple(issues))
