from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from pypinyin import Style, pinyin

RHYME_GROUPS: dict[str, str] = {
    "a": "一麻", "ia": "一麻", "ua": "一麻",
    "o": "二波", "e": "二波", "uo": "二波",
    "ie": "三皆", "ve": "三皆",
    "ai": "四开", "uai": "四开",
    "ei": "五微", "ui": "五微", "uei": "五微",
    "ao": "六豪", "iao": "六豪",
    "ou": "七尤", "iu": "七尤", "iou": "七尤",
    "an": "八寒", "ian": "八寒", "uan": "八寒", "van": "八寒",
    "en": "九文", "in": "九文", "un": "九文", "vn": "九文",
    "ang": "十唐", "iang": "十唐", "uang": "十唐",
    "eng": "十一庚", "ing": "十一庚", "ong": "十一庚", "iong": "十一庚",
    "i": "十二齐", "v": "十二齐", "er": "十二齐",
    "u": "十四姑",
}

_ZHI_INITIALS = {"zh", "ch", "sh", "r", "z", "c", "s"}


@dataclass(frozen=True)
class RhymeResolution:
    group: str | None
    notes: tuple[str, ...] = ()


def _final_groups(final: str, initial: str) -> tuple[str, ...]:
    final = final.replace("ü", "v")
    if final == "i" and initial in _ZHI_INITIALS:
        return ("十三支",)
    group = RHYME_GROUPS.get(final)
    return (group,) if group else ()


def _ordered_groups(char: str) -> list[str]:
    finals = pinyin(char, style=Style.FINALS, heteronym=True)
    initials = pinyin(char, style=Style.INITIALS, heteronym=True)
    if not finals or not finals[0]:
        return []
    final_values = finals[0]
    initial_values = initials[0] if initials else [""]
    seen: list[str] = []
    for index, final in enumerate(final_values):
        initial = initial_values[index] if index < len(initial_values) else initial_values[0]
        for group in _final_groups(final or "", initial or ""):
            if group not in seen:
                seen.append(group)
    return seen


def rhyme_groups(char: str) -> frozenset[str]:
    return frozenset(_ordered_groups(char))


def resolve_rhyme(
    chars: Sequence[str], preferred: str | None = None
) -> RhymeResolution:
    if not chars:
        return RhymeResolution(None)

    ordered = [_ordered_groups(char) for char in chars]
    if any(not groups for groups in ordered):
        return RhymeResolution(None)

    common = set(ordered[0])
    for groups in ordered[1:]:
        common &= set(groups)
    if not common:
        return RhymeResolution(None)

    if preferred is not None and preferred in common:
        return RhymeResolution(preferred)

    costs: dict[str, int] = {}
    for group in common:
        costs[group] = sum(groups.index(group) for groups in ordered)
    best_cost = min(costs.values())
    best = [group for group, cost in costs.items() if cost == best_cost]
    if len(best) != 1:
        return RhymeResolution(None, tuple(sorted(best)))

    chosen = best[0]
    notes = tuple(
        f"多音字：{char} 按 {chosen} 读"
        for char, groups in zip(chars, ordered)
        if groups.index(chosen) > 0
    )
    return RhymeResolution(chosen, notes)


def context_rhyme_group(line: str) -> str | None:
    """按整句上下文取末字的常用读音，再归部。"""
    text = "".join(ch for ch in line if "\u3400" <= ch <= "\u9fff")
    if not text:
        return None
    finals = pinyin(text, style=Style.FINALS, heteronym=False)
    initials = pinyin(text, style=Style.INITIALS, heteronym=False)
    if not finals or not finals[-1]:
        return None
    final = (finals[-1][0] or "").replace("ü", "v")
    initial = (initials[-1][0] if initials and initials[-1] else "") or ""
    groups = _final_groups(final, initial)
    return groups[0] if groups else None


def candidates(group: str, chars: Iterable[str]) -> list[str]:
    return [char for char in chars if group in rhyme_groups(char)]
