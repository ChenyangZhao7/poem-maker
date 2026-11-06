from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import yaml

Tone = Literal["平", "仄"]

_PUNCT = set(" \t\r\n，。、；：,.;:")
_MARKER_YUN = ("（韵）", "(韵)")
_MARKER_JU = ("（句）", "(句)")
_MARKER_PING = ("（平韵）", "(平韵)")
_MARKER_ZE = ("（仄韵）", "(仄韵)")
_MARKER_CHANGE = ("（换韵）", "(换韵)")


class CipaiParseError(Exception):
    def __init__(self, line_no: int, col: int, message: str):
        self.line_no = line_no
        self.col = col
        self.message = message
        super().__init__(f"第 {line_no} 行第 {col} 列：{message}")


@dataclass(frozen=True)
class CipaiLine:
    pattern: str
    rhyme: bool
    rhyme_tone: Tone | None
    section: int


@dataclass(frozen=True)
class Cipai:
    name: str
    variant: str
    lines: tuple[CipaiLine, ...]

    @property
    def line_count(self) -> int:
        return len(self.lines)

    @property
    def section_count(self) -> int:
        return max((line.section for line in self.lines), default=-1) + 1

    @property
    def rhyme_lines(self) -> tuple[CipaiLine, ...]:
        return tuple(line for line in self.lines if line.rhyme)


def normalize_pattern(text: str, line_no: int = 1) -> tuple[str, bool, Tone | None]:
    pattern: list[str] = []
    rhyme = False
    tone: Tone | None = None
    index = 0
    while index < len(text):
        char = text[index]

        if char in _PUNCT:
            index += 1
            continue

        matched_marker = False
        for marker in _MARKER_CHANGE:
            if text.startswith(marker, index):
                rhyme = True
                index += len(marker)
                matched_marker = True
                break
        if matched_marker:
            continue

        for marker in _MARKER_PING:
            if text.startswith(marker, index):
                rhyme = True
                tone = "平"
                index += len(marker)
                matched_marker = True
                break
        if matched_marker:
            continue

        for marker in _MARKER_ZE:
            if text.startswith(marker, index):
                rhyme = True
                tone = "仄"
                index += len(marker)
                matched_marker = True
                break
        if matched_marker:
            continue

        for marker in _MARKER_YUN:
            if text.startswith(marker, index):
                rhyme = True
                index += len(marker)
                matched_marker = True
                break
        if matched_marker:
            continue

        for marker in _MARKER_JU:
            if text.startswith(marker, index):
                index += len(marker)
                matched_marker = True
                break
        if matched_marker:
            continue

        if text.startswith("可平可仄", index):
            pattern.append("中")
            index += 4
            continue

        if char in "⊙中":
            pattern.append("中")
        elif char == "○":
            pattern.append("平")
        elif char == "●":
            pattern.append("仄")
        elif char in "平仄":
            pattern.append(char)
        elif char == "△":
            rhyme = True
            tone = "平"
        elif char == "▲":
            rhyme = True
            tone = "仄"
        else:
            raise CipaiParseError(line_no, index + 1, f"非法谱字符：{char!r}")
        index += 1

    if not pattern:
        raise CipaiParseError(line_no, 1, "谱为空")
    return "".join(pattern), rhyme, tone


def parse_spectrum(text: str) -> Cipai:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").splitlines()
    name = ""
    name_index = 0
    for i, raw in enumerate(lines):
        if raw.strip():
            name = raw.strip()
            name_index = i
            break
    if not name:
        raise CipaiParseError(1, 1, "缺少词牌名")

    sections: list[list[CipaiLine]] = []
    current: list[CipaiLine] = []
    for line_no, raw in enumerate(lines[name_index + 1 :], start=name_index + 2):
        line = raw.strip()
        if not line or line == "---":
            if current:
                sections.append(current)
                current = []
            continue
        pattern, rhyme, tone = normalize_pattern(line, line_no=line_no)
        current.append(CipaiLine(pattern, rhyme, tone, len(sections)))
    if current:
        sections.append(current)
    if not sections:
        raise CipaiParseError(1, 1, "缺少谱行")

    return Cipai(
        name=name,
        variant="自定义",
        lines=tuple(line for section in sections for line in section),
    )


def _validate_pattern(pattern: str, line_no: int) -> str:
    if not pattern:
        raise CipaiParseError(line_no, 1, "pattern 为空")
    for col, char in enumerate(pattern, start=1):
        if char not in "平仄中":
            raise CipaiParseError(line_no, col, f"pattern 含非法字符：{char!r}")
    return pattern


def load_cipai(path: Path) -> Cipai:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise CipaiParseError(1, 1, f"{path} 不是合法的词牌 YAML")
    name = str(data.get("name") or "").strip()
    if not name:
        raise CipaiParseError(1, 1, "缺少 name")
    variant = str(data.get("variant") or "正体").strip()

    sections = data.get("sections")
    if not isinstance(sections, list) or not sections:
        raise CipaiParseError(1, 1, "缺少 sections")

    result: list[CipaiLine] = []
    line_no = 1
    for section_index, section in enumerate(sections):
        if not isinstance(section, dict) or not isinstance(section.get("lines"), list):
            raise CipaiParseError(line_no, 1, "section 缺少 lines")
        for item in section["lines"]:
            line_no += 1
            if not isinstance(item, dict):
                raise CipaiParseError(line_no, 1, "谱行必须是表")
            pattern = _validate_pattern(str(item.get("pattern") or ""), line_no)
            rhyme = bool(item.get("rhyme", False))
            tone = item.get("rhyme_tone")
            if tone not in (None, "平", "仄"):
                raise CipaiParseError(line_no, 1, "rhyme_tone 必须是 平/仄")
            result.append(CipaiLine(pattern, rhyme, tone, section_index))

    if not result:
        raise CipaiParseError(1, 1, "没有谱行")
    return Cipai(name=name, variant=variant, lines=tuple(result))
