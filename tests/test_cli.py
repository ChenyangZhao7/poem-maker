from eh_poem_style.cli import main


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
