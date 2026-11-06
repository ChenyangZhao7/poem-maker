from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

_TITLE_RE = re.compile(r"^##\s+(\d+)\s+(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class Poem:
    title: str
    lines: tuple[str, ...]
    genre: str
    cipai: str | None
    raw: str


def detect_cipai(title: str) -> str | None:
    if "·" not in title:
        return None
    left = title.split("·", 1)[0].strip()
    left = re.sub(r"^\d+\s+", "", left).strip()
    return left or None


def parse_seed_markdown(text: str) -> tuple[list[Poem], list[str]]:
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    matches = list(_TITLE_RE.finditer(text))
    poems: list[Poem] = []
    dupes: list[str] = []
    seen: set[tuple[str, ...]] = set()

    for index, match in enumerate(matches):
        number = match.group(1)
        raw_title = match.group(2).strip()
        full_title = f"{number} {raw_title}"
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[match.end() : end]
        lines = tuple(
            line.strip()
            for line in body.splitlines()
            if line.strip() and not line.lstrip().startswith(">")
        )
        if not lines:
            continue
        key = tuple(lines)
        if key in seen:
            dupes.append(full_title)
            continue
        seen.add(key)
        cipai = detect_cipai(raw_title)
        poems.append(
            Poem(
                title=full_title,
                lines=lines,
                genre="词" if cipai else "诗",
                cipai=cipai,
                raw="\n".join(lines),
            )
        )
    return poems, dupes


def import_seed(src: Path, dst: Path) -> tuple[int, list[str]]:
    if src.resolve() != dst.resolve():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    poems, dupes = parse_seed_markdown(dst.read_text(encoding="utf-8"))
    return len(poems), dupes
