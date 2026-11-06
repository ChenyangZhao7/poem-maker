from eh_poem_style.cli import main


class FakeLLM:
    def __init__(self, text):
        self.text = text

    def complete(self, messages, **opts):
        return self.text


def test_help_lists_commands(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    for cmd in [
        "import-seed",
        "style",
        "generate",
        "compare",
        "validate",
        "cipai",
        "accept",
    ]:
        assert cmd in out


def test_unknown_command_returns_nonzero(capsys):
    assert main(["nope"]) != 0


def test_generate_end_to_end(tmp_path, monkeypatch, capsys):
    (tmp_path / "corpus" / "seed").mkdir(parents=True)
    (tmp_path / "corpus" / "seed" / "seed.md").write_text(
        "## 01 测试\n\n荒草高天斜风吹\n", encoding="utf-8"
    )
    (tmp_path / "style").mkdir()
    (tmp_path / "style" / "style-card.md").write_text(
        "风格卡", encoding="utf-8"
    )
    (tmp_path / "config.toml").write_text(
        'default_profile = "fake"\n\n'
        '[models.fake]\nbase_url = "https://api.example/v1"\n'
        'api_key = "k"\nmodel = "m"\n',
        encoding="utf-8",
    )
    good = (
        '{"title":"t","genre":"五绝","cipai":null,'
        '"lines":["白日依山尽","黄河入海流","欲穷千里目","更上一层楼"],'
        '"rhyme":[]}'
    )
    monkeypatch.setattr(
        "eh_poem_style.cli.build_client", lambda name, config: FakeLLM(good)
    )
    monkeypatch.chdir(tmp_path)
    code = main(
        [
            "generate",
            "--genre",
            "五绝",
            "--prompt",
            "写一首",
            "--profile",
            "fake",
            "--no-first-rhyme",
        ]
    )
    assert code == 0
    assert "白日依山尽" in capsys.readouterr().out
