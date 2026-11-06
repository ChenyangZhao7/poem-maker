from pathlib import Path

from eh_poem_style.corpus import (
    accept_run,
    detect_cipai,
    import_seed,
    parse_seed_markdown,
)


def test_parse_and_dedupe():
    text = """# 诗集

## 01 游巨石阵

荒草高天斜风吹
斑石浅壑矗无声

## 02 如梦令·观奥尔梅克

林间啼声惊起，
折径光阴倒计。

## 03 游巨石阵

荒草高天斜风吹
斑石浅壑矗无声
"""
    poems, dupes = parse_seed_markdown(text)
    assert len(poems) == 2
    assert dupes == ["03 游巨石阵"]
    assert poems[1].genre == "词"
    assert poems[1].cipai == "如梦令"


def test_crlf_and_bom():
    text = "\ufeff## 01 测试\r\n\r\n一句\r\n二句\r\n"
    poems, _ = parse_seed_markdown(text)
    assert poems[0].lines == ("一句", "二句")


def test_detect_cipai():
    assert detect_cipai("如梦令·观奥尔梅克") == "如梦令"
    assert detect_cipai("02 如梦令·观奥尔梅克") == "如梦令"
    assert detect_cipai("游巨石阵") is None


def test_import_seed_copies_and_parses(tmp_path):
    src = tmp_path / "seed.md"
    src.write_text(
        "## 01 测试\n\n一句\n二句\n", encoding="utf-8"
    )
    dst = tmp_path / "copied.md"
    count, dupes = import_seed(src, dst)
    assert count == 1
    assert dupes == []
    assert dst.read_text(encoding="utf-8") == src.read_text(encoding="utf-8")


def test_import_seed_same_path_does_not_raise(tmp_path):
    src = tmp_path / "seed.md"
    src.write_text("## 01 测试\n\n一句\n", encoding="utf-8")
    count, _ = import_seed(src, src)
    assert count == 1


def test_accept_writes_diff(tmp_path):
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "draft.md").write_text("白日依山尽\n黄河入海流\n", encoding="utf-8")
    edited = tmp_path / "edited.md"
    edited.write_text("白日依山尽\n黄河入海流\n更上一层楼\n", encoding="utf-8")
    out = accept_run(
        "r1",
        edited,
        runs_dir=tmp_path / "runs",
        poems_dir=tmp_path / "poems",
    )
    text = out.read_text(encoding="utf-8")
    assert "status: final" in text
    assert "更上一层楼" in text
    assert "---" in text
    assert "修改记录" in text


def test_accept_does_not_overwrite_existing(tmp_path):
    run = tmp_path / "runs" / "r3"
    run.mkdir(parents=True)
    (run / "draft.md").write_text("# 同题\n\n一句\n", encoding="utf-8")
    first = accept_run(
        "r3", runs_dir=tmp_path / "runs", poems_dir=tmp_path / "poems"
    )
    second = accept_run(
        "r3", runs_dir=tmp_path / "runs", poems_dir=tmp_path / "poems"
    )
    assert first != second
    assert first.exists() and second.exists()


def test_accept_without_edit_has_no_diff(tmp_path):
    run = tmp_path / "runs" / "r2"
    run.mkdir(parents=True)
    (run / "draft.md").write_text("一句\n二句\n", encoding="utf-8")
    out = accept_run(
        "r2",
        runs_dir=tmp_path / "runs",
        poems_dir=tmp_path / "poems",
    )
    text = out.read_text(encoding="utf-8")
    assert "一句" in text
    assert "无修改" in text
