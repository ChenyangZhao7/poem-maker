from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(Exception):
    """配置缺失或无效。"""


@dataclass(frozen=True)
class ModelProfile:
    name: str
    base_url: str
    api_key: str
    model: str
    temperature: float = 0.8
    max_tokens: int = 4096
    timeout: float = 60.0
    backend: str = "openai"
    extra: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    default_profile: str
    models: dict[str, ModelProfile]


def _resolve_api_key(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError("api_key 不能为空")
    if value.startswith("env:"):
        env_name = value[4:].strip()
        if not env_name:
            raise ConfigError("api_key 的 env: 后缺少环境变量名")
        resolved = os.environ.get(env_name)
        if not resolved:
            raise ConfigError(f"环境变量 {env_name} 未设置或为空")
        return resolved
    return value


def _build_profile(name: str, raw: object) -> ModelProfile:
    if not isinstance(raw, dict):
        raise ConfigError(f"models.{name} 必须是表")
    for key in ("base_url", "api_key", "model"):
        if key not in raw:
            raise ConfigError(f"models.{name} 缺少 {key}")
    extra = raw.get("extra", {})
    if not isinstance(extra, dict):
        raise ConfigError(f"models.{name}.extra 必须是表")
    return ModelProfile(
        name=name,
        base_url=str(raw["base_url"]).rstrip("/"),
        api_key=_resolve_api_key(raw["api_key"]),
        model=str(raw["model"]),
        temperature=float(raw.get("temperature", 0.8)),
        max_tokens=int(raw.get("max_tokens", 4096)),
        timeout=float(raw.get("timeout", 60.0)),
        backend=str(raw.get("backend", "openai")),
        extra=dict(extra),
    )


def load_config(path: Path | None = None) -> Config:
    config_path = path or (Path.cwd() / "config.toml")
    if not config_path.exists():
        raise ConfigError(f"找不到配置文件：{config_path}")
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"配置文件格式错误：{exc}") from exc

    default_profile = data.get("default_profile")
    if not isinstance(default_profile, str) or not default_profile:
        raise ConfigError("缺少 default_profile")

    raw_models = data.get("models", {})
    if not isinstance(raw_models, dict) or not raw_models:
        raise ConfigError("缺少 [models.*] 配置")
    models = {name: _build_profile(name, raw) for name, raw in raw_models.items()}
    if default_profile not in models:
        raise ConfigError(f"default_profile={default_profile!r} 不在 models 中")
    return Config(default_profile=default_profile, models=models)
