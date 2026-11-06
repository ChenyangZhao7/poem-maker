from __future__ import annotations

import argparse
import sys
from typing import Sequence


def _not_implemented(args: argparse.Namespace) -> int:
    print(f"{args.command}: not implemented", file=sys.stderr)
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eh-poem",
        description="用个人风格生成中文诗词；诗查新韵，词查词牌谱。",
    )
    sub = parser.add_subparsers(dest="command")

    for name, help_text in (
        ("import-seed", "导入种子诗集"),
        ("style", "生成/审查风格卡"),
        ("generate", "生成一首诗或词"),
        ("compare", "用多个模型配置同题对比"),
        ("validate", "校验一个草稿"),
        ("cipai", "管理词牌谱"),
        ("accept", "接受一次生成并保存定稿"),
    ):
        cmd = sub.add_parser(name, help=help_text)
        cmd.set_defaults(func=_not_implemented)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:  # argparse uses SystemExit for --help / errors
        return int(exc.code or 0)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    return int(func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
