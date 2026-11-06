from pathlib import Path

import pytest

from eh_poem_style.cipai import (
    CipaiParseError,
    load_cipai,
    normalize_pattern,
    parse_spectrum,
)


def test_normalize_mixed_symbols():
    assert normalize_pattern("⊙平⊙仄仄平平（韵）") == ("中平中仄仄平平", True, None)


def test_normalize_delta_means_ping_rhyme():
    assert normalize_pattern("中平中仄△") == ("中平中仄", True, "平")


def test_normalize_triangle_means_ze_rhyme():
    assert normalize_pattern("中仄中平▲") == ("中仄中平", True, "仄")


def test_normalize_keyi_ping_ze():
    assert normalize_pattern("可平可仄平") == ("中平", False, None)


def test_invalid_symbol_reports_position():
    with pytest.raises(CipaiParseError) as e:
        normalize_pattern("中平X")
    assert e.value.col == 3


def test_load_rumengling():
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    assert c.name == "如梦令"
    assert c.line_count == 7
    assert c.lines[0].pattern == "中仄仄平平仄"
    assert c.lines[0].rhyme is True
    assert c.lines[0].rhyme_tone == "仄"
    assert c.lines[2].rhyme is False


def test_parse_sections():
    c = parse_spectrum("测试\n平仄（韵）\n---\n仄平（韵）")
    assert c.name == "测试"
    assert c.section_count == 2
    assert c.lines[0].section == 0
    assert c.lines[1].section == 1
