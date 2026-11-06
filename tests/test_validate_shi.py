from eh_poem_style.models import PoemDraft
from eh_poem_style.validate.shi import ShiSpec, spec_for_genre, validate_shi


def draft(lines, genre="七绝"):
    return PoemDraft(title="t", genre=genre, cipai=None, lines=lines)


def test_wu_jue_passes():
    d = draft(["白日依山尽", "黄河入海流", "欲穷千里目", "更上一层楼"], "五绝")
    r = validate_shi(d, spec_for_genre("五绝", first_rhyme=False))
    assert r.ok


def test_user_qi_lu_passes():
    lines = [
        "荒草高天斜风吹",
        "斑石浅壑矗无声",
        "耳畔忽闻琵琶行",
        "悲顿心起愁难平",
        "烦杂琐事细细数",
        "妄学石林历永恒",
        "败军小卒几顺命",
        "乍有抬眼望星空",
    ]
    r = validate_shi(draft(lines, "七律"), spec_for_genre("七律", first_rhyme=False))
    assert r.ok


def test_wrong_line_count_fails():
    r = validate_shi(
        draft(["黄河入海流", "更上一层楼"], "五绝"),
        spec_for_genre("五绝"),
    )
    assert not r.ok
    assert any(i.code == "line_count" for i in r.issues)


def test_wrong_char_count_fails():
    r = validate_shi(
        draft(["黄河入海", "更上一层楼", "欲穷千里目", "更上一层楼"], "五绝"),
        spec_for_genre("五绝"),
    )
    assert any(i.code == "line_length" for i in r.issues)


def test_rhyme_mismatch_fails():
    d = draft(["白日依山尽", "黄河入海流", "欲穷千里目", "更上一层台"], "五绝")
    r = validate_shi(d, spec_for_genre("五绝", first_rhyme=False))
    assert any(i.code == "rhyme_mismatch" for i in r.issues)


def test_shuo_mei_mismatch_fails():
    r = validate_shi(
        draft(["万事可入眼", "功过难评说", "且有恶与好", "妄议心中没"]),
        spec_for_genre("五绝", first_rhyme=False),
    )
    assert any(i.code == "rhyme_mismatch" for i in r.issues)


def test_duplicate_rhyme_fails():
    r = validate_shi(
        draft(["黄河入海流", "更上一层楼", "欲穷千里目", "更上一层楼"]),
        spec_for_genre("五绝", first_rhyme=False),
    )
    assert any(i.code == "duplicate_rhyme" for i in r.issues)


def test_gu_ti_allows_rhyme_change():
    lines = [
        "行越山丛中",
        "旧台星棋见",
        "石阶通天听",
        "圆环立人言",
        "悠悠五千载",
        "但余黄沙鸣",
        "风中传口谕",
        "不知起所云",
    ]
    r = validate_shi(
        draft(lines, "古体"),
        spec_for_genre("古体", line_length=5, first_rhyme=False),
    )
    assert r.ok


def test_punctuation_ignored():
    d = draft(["黄河入海流，", "更上一层楼。", "欲穷千里目，", "更上泰山头。"], "五绝")
    r = validate_shi(d, spec_for_genre("五绝", first_rhyme=False))
    assert not any(i.code == "line_length" for i in r.issues)
