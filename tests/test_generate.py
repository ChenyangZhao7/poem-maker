from eh_poem_style.corpus import Poem
from eh_poem_style.generate import generate
from eh_poem_style.models import GenerateRequest


class FakeLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def complete(self, messages, **opts):
        self.calls.append(messages)
        return self.replies.pop(0)


def test_retries_with_error_feedback(tmp_path):
    bad = (
        '{"title":"t","genre":"七绝","cipai":null,'
        '"lines":["a","b","c","d"],"rhyme":[]}'
    )
    good = (
        '{"title":"t","genre":"五绝","cipai":null,'
        '"lines":["白日依山尽","黄河入海流","欲穷千里目","更上一层楼"],'
        '"rhyme":[]}'
    )
    fake = FakeLLM([bad, good])
    req = GenerateRequest(
        prompt="写一首", genre="五绝", line_length=5, first_rhyme=False
    )
    result = generate(req, fake, "", [], None, None, runs_dir=tmp_path)
    assert result.attempts == 2
    assert result.report.ok
    assert "校验未通过" in fake.calls[1][-1]["content"]


def test_rejects_exact_copied_line(tmp_path):
    copied = (
        '{"title":"t","genre":"七绝","cipai":null,'
        '"lines":["荒草高天斜风吹","一行白鹭上青天",'
        '"窗含西岭千秋雪","门泊东吴万里船"],"rhyme":[]}'
    )
    good = (
        '{"title":"t","genre":"七绝","cipai":null,'
        '"lines":["两个黄鹂鸣翠柳","一行白鹭上青天",'
        '"窗含西岭千秋雪","门泊东吴万里船"],"rhyme":[]}'
    )
    fake = FakeLLM([copied, good])
    examples = [Poem("seed", ("荒草高天斜风吹",), "诗", None, "")]
    req = GenerateRequest(prompt="写一首", genre="七绝", first_rhyme=False)
    result = generate(req, fake, "", examples, None, None, runs_dir=tmp_path)
    assert result.attempts == 2
    assert result.report.ok
    assert "校验未通过" in fake.calls[1][-1]["content"]


def test_run_files_are_written(tmp_path):
    good = (
        '{"title":"t","genre":"五绝","cipai":null,'
        '"lines":["白日依山尽","黄河入海流","欲穷千里目","更上一层楼"],'
        '"rhyme":[]}'
    )
    fake = FakeLLM([good])
    req = GenerateRequest(prompt="写一首", genre="五绝", first_rhyme=False)
    result = generate(req, fake, "", [], None, None, runs_dir=tmp_path)
    assert (result.run_dir / "request.json").exists()
    assert (result.run_dir / "draft.md").exists()
    assert (result.run_dir / "report.md").exists()
    assert (result.run_dir / "attempt-1.txt").exists()
