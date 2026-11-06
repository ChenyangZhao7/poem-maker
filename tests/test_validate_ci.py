from pathlib import Path

import pytest

from eh_poem_style.cipai import load_cipai
from eh_poem_style.models import PoemDraft
from eh_poem_style.validate.ci import validate_ci


def ci_draft(lines, name="如梦令"):
    return PoemDraft(title="t", genre="词", cipai=name, lines=lines)


def test_rumengling_known_work_passes():
    lines = [
        "昨夜雨疏风骤",
        "浓睡不消残酒",
        "试问卷帘人",
        "却道海棠依旧",
        "知否",
        "知否",
        "应是绿肥红瘦",
    ]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["七尤"] * 6)
    assert r.ok


def test_wrong_char_count_fails():
    lines = [
        "昨夜雨疏风",
        "浓睡不消残酒",
        "试问卷帘人",
        "却道海棠依旧",
        "知否",
        "知否",
        "应是绿肥红瘦",
    ]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["七尤"] * 6)
    assert any(i.code == "line_length" for i in r.issues)


def test_wrong_rhyme_group_fails():
    lines = [
        "昨夜雨疏风骤",
        "浓睡不消残酒",
        "试问卷帘人",
        "却道海棠依旧",
        "知否",
        "知否",
        "应是绿肥红瘦",
    ]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["一麻"] * 6)
    assert any(i.code == "rhyme_mismatch" for i in r.issues)


def test_wrong_tone_fails():
    lines = [
        "昨夜雨疏雨骤",
        "浓睡不消残酒",
        "试问卷帘人",
        "却道海棠依旧",
        "知否",
        "知否",
        "应是绿肥红瘦",
    ]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["七尤"] * 6)
    assert any(i.code == "tone_mismatch" for i in r.issues)


def test_xiangjianhuan_switch_rhyme_passes():
    lines = [
        "无言独上西楼",
        "月如钩",
        "寂寞梧桐深院锁清秋",
        "剪不断",
        "理还乱",
        "是离愁",
        "别是一般滋味在心头",
    ]
    c = load_cipai(Path("data/cipai/xiangjianhuan.yaml"))
    plan = ["七尤", "七尤", "七尤", "八寒", "八寒", "七尤", "七尤"]
    assert validate_ci(ci_draft(lines, "相见欢"), c, plan).ok


def test_rhyme_plan_length_mismatch_raises():
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    with pytest.raises(ValueError):
        validate_ci(ci_draft(["知否"] * 7), c, ["七尤"])

