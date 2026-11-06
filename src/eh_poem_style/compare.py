from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Mapping, Sequence

from eh_poem_style.cipai import Cipai
from eh_poem_style.corpus import Poem
from eh_poem_style.generate import generate
from eh_poem_style.models import GenerateRequest, LLMClient
from eh_poem_style.style import StyleStats


def compare(
    request: GenerateRequest,
    clients: Mapping[str, LLMClient],
    style_card: str,
    examples: Sequence[Poem],
    cipai: Cipai | None,
    stats: StyleStats | None,
    runs_dir: Path = Path("runs"),
) -> Path:
    out_dir = runs_dir / f"{datetime.now():%Y%m%d-%H%M%S}-compare"
    out_dir.mkdir(parents=True, exist_ok=True)
    sections: list[str] = []

    for name, client in clients.items():
        started = time.perf_counter()
        try:
            result = generate(
                request,
                client,
                style_card,
                examples,
                cipai,
                stats,
                runs_dir=out_dir / name,
            )
            elapsed = time.perf_counter() - started
            body = "\n".join(result.draft.lines)
            if result.report.ok:
                verdict = "通过"
            else:
                verdict = "\n".join(
                    f"- [{issue.level}] {issue.code}: {issue.message}"
                    for issue in result.report.issues
                )
            sections.append(
                f"## {name}\n\n《{result.draft.title}》\n\n{body}\n\n"
                f"尝试：{result.attempts} 次；耗时：{elapsed:.1f}s\n\n"
                f"校验：\n{verdict}"
            )
        except Exception as exc:  # one profile failing must not stop the others
            elapsed = time.perf_counter() - started
            sections.append(f"## {name}\n\n失败（{elapsed:.1f}s）：{exc}")

    path = out_dir / "compare.md"
    path.write_text(
        "# 模型对比\n\n" + "\n\n---\n\n".join(sections) + "\n",
        encoding="utf-8",
    )
    return path
