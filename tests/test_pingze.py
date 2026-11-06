from eh_poem_style.pingze import tone_of_char, tone_of_line


def test_line_tones_use_context():
    assert tone_of_line("晨日入深林口") == ("平", "仄", "仄", "平", "平", "仄")


def test_common_readings():
    assert tone_of_char("国") == "平"  # guó
    assert tone_of_char("月") == "仄"  # yuè
    assert tone_of_char("一") == "平"  # yī


def test_punctuation_ignored():
    assert tone_of_line("晨日，入深林。") == ("平", "仄", "仄", "平", "平")


def test_unknown_returns_none():
    assert tone_of_char("𠀀") is None


def test_empty_line():
    assert tone_of_line("") == ()
