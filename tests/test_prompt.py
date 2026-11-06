from pathlib import Path

import pytest

from eh_poem_style.cipai import load_cipai
from eh_poem_style.corpus import Poem
from eh_poem_style.models import GenerateRequest
from eh_poem_style.prompt import (
    DraftParseError,
    PromptContext,
    build_messages,
    parse_draft,
)
from eh_poem_style.validate.shi import spec_for_genre


def test_parse_code_fence():
    text = (
        "好的，结果如下：\n```json\n"
        '{"title":"t","genre":"七绝","cipai":null,"lines":["a","b"],"rhyme":["b"]}\n'
        "```\n"
    )
    d = parse_draft(text)
    assert d.lines == ["a", "b"]
    assert d.rhyme == ["b"]


def test_parse_pure_json():
    d = parse_draft('{"title":"t","genre":"五绝","cipai":null,"lines":["一句"]}')
    assert d.title == "t"
    assert d.cipai is None


def test_parse_missing_field_raises():
    with pytest.raises(DraftParseError):
        parse_draft('{"title":"t"}')


def test_parse_no_json_raises():
    with pytest.raises(DraftParseError):
        parse_draft("我写不出来")


def test_build_messages_for_shi():
    ctx = PromptContext(
        style_card="常用字：荒草",
        examples=[Poem("01 测试", ("荒草高天斜风吹",), "诗", None, "")],
        spec=spec_for_genre("七绝", first_rhyme=False),
        cipai=None,
        rhyme_groups=("十唐",),
        candidate_chars=("光", "黄"),
    )
    messages = build_messages(
        GenerateRequest(prompt="写夜游多瑙河", genre="七绝"),
        ctx,
    )
    system = messages[0]["content"]
    user = messages[1]["content"]
    assert "只输出一个 JSON" in system
    assert "诗不要求平仄" in system
    assert "十唐" in user
    assert "光" in user
    assert "写夜游多瑙河" in user
    assert "荒草" in user


def test_build_messages_for_ci():
    cipai = load_cipai(Path("data/cipai/rumengling.yaml"))
    ctx = PromptContext(
        style_card="常用字：荒草",
        examples=[Poem("01 测试", ("荒草高天斜风吹",), "诗", None, "")],
        spec=None,
        cipai=cipai,
        rhyme_groups=("七尤",) * 6,
        candidate_chars=("有", "酒"),
    )
    messages = build_messages(
        GenerateRequest(prompt="写晨林惊鸟", genre="词", cipai="如梦令"),
        ctx,
    )
    system = messages[0]["content"]
    user = messages[1]["content"]
    assert "词必须" in system
    assert "如梦令" in user
    assert "中仄仄平平仄" in user
    assert "七尤" in user
