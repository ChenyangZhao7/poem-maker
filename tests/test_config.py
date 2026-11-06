from pathlib import Path

import pytest

from eh_poem_style.config import ConfigError, load_config


def test_load_config_resolves_env_key(tmp_path, monkeypatch):
    monkeypatch.setenv("MY_KEY", "secret")
    p = tmp_path / "config.toml"
    p.write_text(
        'default_profile = "deepseek"\n\n'
        '[models.deepseek]\nbase_url = "https://api.example/v1"\n'
        'api_key = "env:MY_KEY"\nmodel = "ds-v4.1"\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.default_profile == "deepseek"
    assert cfg.models["deepseek"].api_key == "secret"


def test_missing_profile_raises(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('default_profile = "nope"\n', encoding="utf-8")
    with pytest.raises(ConfigError):
        load_config(p)


def test_profile_extra_table(tmp_path):
    p = tmp_path / "config.toml"
    p.write_text(
        'default_profile = "x"\n\n'
        '[models.x]\nbase_url = "https://api.example/v1"\n'
        'api_key = "k"\nmodel = "m"\n\n'
        '[models.x.extra]\nthink = false\n',
        encoding="utf-8",
    )
    cfg = load_config(p)
    assert cfg.models["x"].extra == {"think": False}


def test_missing_env_key_raises(tmp_path, monkeypatch):
    monkeypatch.delenv("NOPE_KEY", raising=False)
    p = tmp_path / "config.toml"
    p.write_text(
        'default_profile = "x"\n\n'
        '[models.x]\nbase_url = "https://api.example/v1"\n'
        'api_key = "env:NOPE_KEY"\nmodel = "m"\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError):
        load_config(p)
