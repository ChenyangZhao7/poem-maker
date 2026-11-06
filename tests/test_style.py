from eh_poem_style.corpus import Poem
from eh_poem_style.style import (
    analyze_corpus,
    build_style_card,
    load_fewshot,
    review_style_card,
)


def test_stats_counts():
    poems = [
        Poem("a", ("荒草高天斜风吹", "斑石浅壑矗无声"), "诗", None, ""),
        Poem("b", ("林间啼声惊起", "折径光阴倒计"), "词", "如梦令", ""),
    ]
    stats = analyze_corpus(poems)
    assert stats.poem_count == 2
    assert stats.ci_count == 1
    assert stats.line_lengths[7] == 2


def test_card_includes_all_examples_by_default():
    poems = [Poem(f"t{i}", ("荒草高天斜风吹",), "诗", None, "") for i in range(12)]
    card = build_style_card(analyze_corpus(poems), poems)
    for section in ["常用字", "意象", "句法", "情感", "用韵", "忌用", "示例"]:
        assert section in card
    assert card.count("《t") == 12


def test_example_count_can_limit():
    poems = [Poem(f"t{i}", ("荒草高天斜风吹",), "诗", None, "") for i in range(12)]
    card = build_style_card(analyze_corpus(poems), poems, example_count=3)
    assert card.count("《t") == 3


def test_card_uses_llm_text():
    class Fake:
        def complete(self, messages, **opts):
            return "## 常用字\n荒草、残垣\n"

    card = build_style_card(analyze_corpus([]), [], llm=Fake())
    assert "荒草" in card


def test_review_accepts_on_enter():
    assert review_style_card("草稿", input_fn=lambda _: "") == "草稿"


def test_review_quit_returns_none():
    assert review_style_card("草稿", input_fn=lambda _: "q") is None


def test_review_uses_feedback():
    class Fake:
        def complete(self, messages, **opts):
            return "改后的卡"

    answers = iter(["r", "多写荒草", ""])
    card = review_style_card("草稿", llm=Fake(), input_fn=lambda _: next(answers))
    assert card == "改后的卡"


def test_load_fewshot_selects_in_file_order(tmp_path):
    poems = [
        Poem("01 甲", ("一句",), "诗", None, ""),
        Poem("02 乙", ("二句",), "诗", None, ""),
        Poem("03 丙", ("三句",), "诗", None, ""),
    ]
    path = tmp_path / "fewshot.txt"
    path.write_text("# 精选\n03 丙\n01 甲\n", encoding="utf-8")
    assert [p.title for p in load_fewshot(poems, path)] == ["03 丙", "01 甲"]


def test_load_fewshot_missing_returns_all(tmp_path):
    poems = [Poem("01 甲", ("一句",), "诗", None, "")]
    assert load_fewshot(poems, tmp_path / "nope.txt") == poems
