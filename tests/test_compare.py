from eh_poem_style.compare import compare
from eh_poem_style.models import GenerateRequest


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def complete(self, messages, **opts):
        return self.text


def test_compare_writes_two_sections(tmp_path):
    good = (
        '{"title":"t","genre":"五绝","cipai":null,'
        '"lines":["白日依山尽","黄河入海流","欲穷千里目","更上一层楼"],'
        '"rhyme":[]}'
    )
    req = GenerateRequest(
        prompt="写一首", genre="五绝", line_length=5, first_rhyme=False
    )
    out = compare(
        req,
        {"deepseek": FakeLLM(good), "local": FakeLLM(good)},
        "",
        [],
        None,
        None,
        runs_dir=tmp_path,
    )
    text = out.read_text(encoding="utf-8")
    assert "deepseek" in text and "local" in text
    assert "白日依山尽" in text
