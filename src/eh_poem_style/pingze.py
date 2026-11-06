from __future__ import annotations

from typing import Literal

from pypinyin import Style, pinyin


class PingzeError(Exception):
    """无法从拼音结果判定平仄。"""


def cjk(text: str) -> str:
    """只保留汉字，去掉标点、空白与拉丁字符。"""
    return "".join(ch for ch in text if "\u3400" <= ch <= "\u9fff")


def _tone_from_syllable(syllable: str) -> str | None:
    if not syllable:
        return None
    marker = syllable[-1]
    if marker in "12":
        return "平"
    if marker in "34":
        return "仄"
    return None


def tone_of_line(line: str) -> tuple[str | None, ...]:
    """按整句上下文取最常用读音，返回每个汉字的现代平仄。"""
    text = cjk(line)
    if not text:
        return ()
    try:
        readings = pinyin(text, style=Style.TONE3, heteronym=False)
    except Exception as exc:  # pragma: no cover - pypinyin failure is defensive
        raise PingzeError(f"无法取音：{line!r}") from exc
    return tuple(_tone_from_syllable(item[0] if item else "") for item in readings)


def tone_of_char(char: str) -> str | None:
    """单字默认读音的平仄。"""
    tones = tone_of_line(char)
    return tones[0] if tones else None


def is_tone(
    char: str,
    expected: Literal["平", "仄"],
    context: str | None = None,
) -> bool:
    if context is not None:
        tones = tone_of_line(context)
        index = cjk(context).find(char)
        return index >= 0 and index < len(tones) and tones[index] == expected
    return tone_of_char(char) == expected
