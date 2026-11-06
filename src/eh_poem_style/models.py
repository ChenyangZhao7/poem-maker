from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True)
class PoemDraft:
    title: str
    genre: str
    cipai: str | None
    lines: list[str]
    rhyme: list[str] = field(default_factory=list)
    notes: str = ""


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    code: str
    message: str
    line: int | None = None
    index: int | None = None


@dataclass(frozen=True)
class Report:
    issues: tuple[Issue, ...] = ()

    @property
    def ok(self) -> bool:
        return not any(i.level == "error" for i in self.issues)


@dataclass(frozen=True)
class GenerateRequest:
    prompt: str
    genre: str
    cipai: str | None = None
    profile: str = "deepseek"
    line_length: int = 5
    first_rhyme: bool = True
    rhyme_group: str | None = None
    max_attempts: int = 3


class LLMClient(Protocol):
    def complete(self, messages: list[dict], **opts) -> str:
        ...
