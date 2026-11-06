from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Sequence

from eh_poem_style.cipai import Cipai
from eh_poem_style.corpus import Poem
from eh_poem_style.models import GenerateRequest, PoemDraft
from eh_poem_style.validate.shi import ShiSpec


class DraftParseError(Exception):
    """模型输出不是可用的诗词 JSON。"""


@dataclass(frozen=True)
class PromptContext:
    style_card: str
    examples: Sequence[Poem]
    spec: ShiSpec | None
    cipai: Cipai | None
    rhyme_groups: Sequence[str]
    candidate_chars: Sequence[str]


def _extract_json(text: str) -> dict:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    raise DraftParseError("未找到 JSON 对象")


def parse_draft(text: str) -> PoemDraft:
    data = _extract_json(text)

    title = data.get("title")
    genre = data.get("genre")
    lines = data.get("lines")
    if not isinstance(title, str) or not title.strip():
        raise DraftParseError("缺少字符串字段 title")
    if not isinstance(genre, str) or not genre.strip():
        raise DraftParseError("缺少字符串字段 genre")
    if (
        not isinstance(lines, list)
        or not lines
        or not all(isinstance(line, str) and line.strip() for line in lines)
    ):
        raise DraftParseError("lines 必须是非空字符串列表")

    cipai = data.get("cipai")
    if cipai is not None and not isinstance(cipai, str):
        raise DraftParseError("cipai 必须是字符串或 null")
    rhyme = data.get("rhyme", [])
    if not isinstance(rhyme, list) or not all(isinstance(item, str) for item in rhyme):
        raise DraftParseError("rhyme 必须是字符串列表")
    notes = data.get("notes", "")
    if not isinstance(notes, str):
        notes = ""

    return PoemDraft(
        title=title.strip(),
        genre=genre.strip(),
        cipai=cipai.strip() if cipai else None,
        lines=[line.strip() for line in lines],
        rhyme=[item.strip() for item in rhyme],
        notes=notes,
    )


_SCHEMA = (
    '{"title": "题目", "genre": "五绝/七绝/五律/七律/古体/词", '
    '"cipai": null 或词牌名, "lines": ["第一句", "第二句"], '
    '"rhyme": ["韵脚字"], "notes": "可选"}'
)


def _examples_text(examples: Sequence[Poem]) -> str:
    if not examples:
        return "（暂无）"
    return "\n\n".join(
        f"《{poem.title}》\n" + "\n".join(poem.lines) for poem in examples
    )


def _ci_rules(cipai: Cipai, rhyme_groups: Sequence[str]) -> str:
    lines = [f"词牌：{cipai.name}（{cipai.variant}）"]
    rhyme_index = 0
    for line in cipai.lines:
        marker = ""
        if line.rhyme:
            group = rhyme_groups[rhyme_index] if rhyme_index < len(rhyme_groups) else "?"
            rhyme_index += 1
            marker = f"（韵，{group}"
            if line.rhyme_tone:
                marker += f"，{line.rhyme_tone}声"
            marker += "）"
        lines.append(f"{line.pattern}{marker}")
    return "\n".join(lines)


def build_messages(request: GenerateRequest, ctx: PromptContext) -> list[dict]:
    system = (
        "你是一位中文旧体诗词写作者。请严格模仿给定作者的个人风格，"
        "不要模仿古代名家。\n"
        "【硬规则】\n"
        "- 只输出一个 JSON 对象，不要 Markdown 代码块，不要解释。\n"
        f"- JSON 字段：{_SCHEMA}\n"
        "- 诗不要求平仄，但句数、每句字数、押韵必须合规。\n"
        "- 词必须逐字合谱：平仄、句读、韵位、韵部都要对；不合格会被退回重写。\n"
        "- 韵脚必须从给定候选字中选；候选不够时可用同韵部其他字，但必须同部。\n"
        "- 不要整句照抄作者原作；学习用词、意象、句法，不复用无关原句。"
    )

    parts = [f"【任务】{request.prompt}", f"【体裁】{request.genre}"]
    if ctx.spec is not None:
        spec = ctx.spec
        parts.append(
            "【诗规格】"
            f"{spec.genre}；每句 {spec.line_length} 字；"
            f"句数 {spec.line_count if spec.line_count is not None else '不限'}；"
            f"首句{'入韵' if spec.first_rhyme else '不入韵'}。"
        )
        if spec.rhyme_group:
            parts.append(f"【韵部】{spec.rhyme_group}")
    if ctx.cipai is not None:
        parts.append("【词牌谱】\n" + _ci_rules(ctx.cipai, ctx.rhyme_groups))
    if ctx.rhyme_groups:
        parts.append("【韵部】" + "、".join(ctx.rhyme_groups))
    if ctx.candidate_chars:
        parts.append("【候选韵脚字】" + "、".join(ctx.candidate_chars))
    parts.append("【风格卡】\n" + ctx.style_card)
    parts.append("【作者作品】\n" + _examples_text(ctx.examples))

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": "\n\n".join(parts)},
    ]
