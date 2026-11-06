from __future__ import annotations

import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

from eh_poem_style.corpus import Poem
from eh_poem_style.models import LLMClient
from eh_poem_style.pingze import cjk
from eh_poem_style.xinyun import resolve_rhyme

DEFAULT_EXAMPLE_COUNT: int | None = None

_STOP = set("的 了 不 人 一 是 在 有 我 他 这 那 中 上 下 来 去 时 日 天 云 山 水".replace(" ", ""))

_IMAGERY = (
    "自然：风、月、云、山、水、星、夜；"
    "器物：灯、酒、舟、碑、钟；"
    "时序：春、秋、年、古；"
    "情感：孤、愁、归、望。"
)

_FORBIDDEN = "网络语、过于浓艳的形容词、生僻典故、整句照抄原作。"


@dataclass(frozen=True)
class StyleStats:
    poem_count: int
    ci_count: int
    char_freq: Counter[str]
    line_lengths: Counter[int]
    shi_rhyme_groups: Counter[str]
    ci_rhyme_groups: Counter[str]
    top_ngrams: list[str]


FEWSHOT_PATH = Path("style/fewshot.txt")


def load_fewshot(
    poems: Sequence[Poem], path: Path = FEWSHOT_PATH
) -> list[Poem]:
    """按 style/fewshot.txt 的标题顺序取精选示例；文件缺失时退回全部。"""
    if not path.exists():
        return list(poems)
    titles = [
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    by_title = {poem.title: poem for poem in poems}
    selected = [by_title[title] for title in titles if title in by_title]
    return selected or list(poems)


def analyze_corpus(poems: Sequence[Poem]) -> StyleStats:
    chars: Counter[str] = Counter()
    lengths: Counter[int] = Counter()
    shi_groups: Counter[str] = Counter()
    ci_groups: Counter[str] = Counter()
    ngrams: Counter[str] = Counter()

    for poem in poems:
        for line in poem.lines:
            clean = cjk(line)
            lengths[len(clean)] += 1
            chars.update(clean)
            for index in range(len(clean) - 1):
                bigram = clean[index : index + 2]
                if bigram[0] in _STOP or bigram[1] in _STOP:
                    continue
                ngrams[bigram] += 1
        rhyme_chars = [
            cjk(line)[-1] for line in poem.lines[1::2] if cjk(line)
        ]
        if rhyme_chars:
            resolution = resolve_rhyme(rhyme_chars)
            if resolution.group:
                target = ci_groups if poem.genre == "词" else shi_groups
                target[resolution.group] += 1

    return StyleStats(
        poem_count=len(poems),
        ci_count=sum(1 for poem in poems if poem.genre == "词"),
        char_freq=chars,
        line_lengths=lengths,
        shi_rhyme_groups=shi_groups,
        ci_rhyme_groups=ci_groups,
        top_ngrams=[ngram for ngram, _ in ngrams.most_common(12)],
    )


def _examples_text(poems: Sequence[Poem]) -> str:
    blocks: list[str] = []
    for poem in poems:
        blocks.append(f"《{poem.title}》\n" + "\n".join(poem.lines))
    return "\n\n".join(blocks)


def _stats_card(stats: StyleStats, poems: Sequence[Poem]) -> str:
    top_chars = "、".join(char for char, _ in stats.char_freq.most_common(30)) or "（暂无）"
    top_ngrams = "、".join(stats.top_ngrams) or "（暂无）"
    lengths = "、".join(
        f"{length}言" for length, _ in stats.line_lengths.most_common(3)
    ) or "（暂无）"
    shi_groups = "、".join(
        f"{group}（{count}）" for group, count in stats.shi_rhyme_groups.most_common(5)
    ) or "（暂无）"
    ci_groups = "、".join(
        f"{group}（{count}）" for group, count in stats.ci_rhyme_groups.most_common(5)
    ) or "（暂无）"

    return (
        "# 风格卡（草稿）\n\n"
        f"## 常用字\n{top_chars}\n\n"
        f"## 高频词组\n{top_ngrams}\n\n"
        f"## 意象域\n{_IMAGERY}\n\n"
        f"## 句法\n以{lengths}为主；短句直陈，少用长调铺陈。\n\n"
        "## 情感\n苍凉、怀古、理想未酬，偶尔自嘲；不堆砌华丽辞藻。\n\n"
        f"## 用韵\n诗：{shi_groups}；词：{ci_groups}\n\n"
        f"## 忌用\n{_FORBIDDEN}\n\n"
        f"## 示例\n{_examples_text(poems)}"
    )


def build_style_card(
    stats: StyleStats,
    poems: Sequence[Poem],
    llm: LLMClient | None = None,
    example_count: int | None = DEFAULT_EXAMPLE_COUNT,
) -> str:
    selected = list(poems) if example_count is None else list(poems)[:example_count]
    fallback = _stats_card(stats, selected)

    if llm is None:
        return fallback

    prompt = (
        "根据下面的统计与作品，写一份中文诗词风格卡。"
        "保留小节：常用字、高频词组、意象域、句法、情感、用韵、忌用。"
        "只输出风格卡正文，不要解释，不要评价。\n\n"
        f"统计：{stats.poem_count} 首（词 {stats.ci_count} 首）；"
        f"常用字：{dict(stats.char_freq.most_common(30))}；"
        f"行长：{dict(stats.line_lengths)}；"
        f"诗韵：{dict(stats.shi_rhyme_groups)}；"
        f"词韵：{dict(stats.ci_rhyme_groups)}。\n\n"
        f"作品：\n{_examples_text(selected)}"
    )
    try:
        text = llm.complete(
            [
                {"role": "system", "content": "你是中文诗词风格分析助手。"},
                {"role": "user", "content": prompt},
            ]
        ).strip()
    except Exception:
        return fallback
    if not text:
        return fallback
    if "示例" not in text:
        text += f"\n\n## 示例\n{_examples_text(selected)}"
    return text


def _default_editor(text: str) -> str:
    path = Path(tempfile.gettempdir()) / "eh-style-card.md"
    path.write_text(text, encoding="utf-8")
    subprocess.run(["notepad", str(path)], check=False)
    return path.read_text(encoding="utf-8") or text


def review_style_card(
    draft: str,
    llm: LLMClient | None = None,
    input_fn: Callable[[str], str] = input,
    editor: Callable[[str], str] | None = None,
) -> str | None:
    edit = editor or _default_editor
    card = draft
    while True:
        print(card)
        try:
            choice = input_fn("回车接受 / e 编辑 / r 让模型改 / q 放弃：").strip().lower()
        except EOFError:
            return None
        if choice in {"", "a"}:
            return card
        if choice == "q":
            return None
        if choice == "e":
            card = edit(card)
            continue
        if choice == "r":
            feedback = input_fn("想改哪里？").strip()
            if not feedback:
                continue
            if llm is None:
                print("未配置模型，无法自动修改；请用 e 直接编辑。")
                continue
            try:
                revised = llm.complete(
                    [
                        {
                            "role": "system",
                            "content": (
                                "你在修改一份中文诗词风格卡。保留原有结构，"
                                "只按用户意见增删改，直接输出完整风格卡，不解释。"
                            ),
                        },
                        {
                            "role": "user",
                            "content": f"当前风格卡：\n{card}\n\n修改意见：{feedback}",
                        },
                    ]
                ).strip()
                if revised:
                    card = revised
            except Exception as exc:
                print(f"修改失败：{exc}")
            continue
        print("未知选项，请输入回车 / e / r / q。")


def write_style_card(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def load_style_card(path: Path) -> str:
    return path.read_text(encoding="utf-8")
