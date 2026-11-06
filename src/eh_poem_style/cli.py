from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

import yaml
from pypinyin import lazy_pinyin

from eh_poem_style.cipai import Cipai, load_cipai, parse_spectrum
from eh_poem_style.compare import compare
from eh_poem_style.config import Config, load_config
from eh_poem_style.corpus import (
    Poem,
    accept_run,
    import_seed,
    parse_seed_markdown,
)
from eh_poem_style.generate import generate
from eh_poem_style.llm import OllamaClient, OpenAICompatClient
from eh_poem_style.models import GenerateRequest, LLMClient, PoemDraft
from eh_poem_style.pingze import cjk
from eh_poem_style.prompt import parse_draft
from eh_poem_style.style import (
    analyze_corpus,
    build_style_card,
    load_style_card,
    review_style_card,
    write_style_card,
)
from eh_poem_style.validate.ci import validate_ci
from eh_poem_style.validate.shi import spec_for_genre, validate_shi
from eh_poem_style.xinyun import rhyme_groups as char_rhyme_groups

GENRES = ["古体", "五律", "七律", "五绝", "七绝", "词"]


def build_client(profile_name: str, config: Config) -> LLMClient:
    if profile_name not in config.models:
        raise ValueError(f"配置中没有模型档案：{profile_name}")
    profile = config.models[profile_name]
    if profile.backend == "ollama":
        return OllamaClient(profile)
    return OpenAICompatClient(profile)


def _load_seed() -> list[Poem]:
    path = Path("corpus/seed/seed.md")
    if not path.exists():
        raise FileNotFoundError(f"找不到种子文件：{path}")
    poems, _ = parse_seed_markdown(path.read_text(encoding="utf-8"))
    return poems


def _load_style() -> str:
    path = Path("style/style-card.md")
    if not path.exists():
        raise FileNotFoundError(f"找不到风格卡：{path}")
    return load_style_card(path)


def _find_cipai(name: str | None) -> Cipai:
    if not name:
        raise ValueError("体裁为词时必须提供 --cipai")
    candidate = Path(name)
    if candidate.suffix in {".yaml", ".yml"} and candidate.exists():
        return load_cipai(candidate)
    for path in sorted(Path("data/cipai").glob("*.yaml")):
        cipai = load_cipai(path)
        if cipai.name == name:
            return cipai
    raise FileNotFoundError(f"找不到词牌：{name}")


def _request(args) -> GenerateRequest:
    return GenerateRequest(
        prompt=args.prompt,
        genre=args.genre,
        cipai=args.cipai,
        profile=args.profile or "",
        line_length=args.line_length,
        first_rhyme=args.first_rhyme,
        rhyme_group=args.rhyme,
        max_attempts=args.max_attempts,
    )


def _print_result(result) -> int:
    print(f"《{result.draft.title}》")
    print("\n".join(result.draft.lines))
    print(f"\n尝试：{result.attempts} 次")
    if result.report.ok:
        print("校验：通过")
    else:
        print("校验：未通过")
        for issue in result.report.issues:
            print(f"- [{issue.level}] {issue.code}: {issue.message}")
    print(f"运行目录：{result.run_dir}")
    return 0 if result.report.ok else 1


def _cmd_generate(args) -> int:
    config = load_config(args.config)
    profile = args.profile or config.default_profile
    request = _request(args)
    request = GenerateRequest(**{**request.__dict__, "profile": profile})
    poems = _load_seed()
    stats = analyze_corpus(poems)
    cipai = _find_cipai(args.cipai) if args.genre == "词" else None
    result = generate(
        request,
        build_client(profile, config),
        _load_style(),
        poems,
        cipai,
        stats,
    )
    return _print_result(result)


def _cmd_compare(args) -> int:
    config = load_config(args.config)
    names = [name.strip() for name in args.profiles.split(",") if name.strip()]
    if not names:
        raise ValueError("--profiles 不能为空")
    request = _request(args)
    request = GenerateRequest(**{**request.__dict__, "profile": names[0]})
    poems = _load_seed()
    stats = analyze_corpus(poems)
    cipai = _find_cipai(args.cipai) if args.genre == "词" else None
    clients = {name: build_client(name, config) for name in names}
    path = compare(
        request,
        clients,
        _load_style(),
        poems,
        cipai,
        stats,
    )
    print(path)
    return 0


def _read_draft(path: Path, genre: str, cipai: str | None) -> PoemDraft:
    text = path.read_text(encoding="utf-8")
    if text.lstrip().startswith("{"):
        return parse_draft(text)
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    title = path.stem
    for line in text.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
            break
    return PoemDraft(title=title, genre=genre, cipai=cipai, lines=lines)


def _cmd_validate(args) -> int:
    draft = _read_draft(args.file, args.genre, args.cipai)
    if args.genre == "词":
        cipai = _find_cipai(args.cipai)
        if args.rhyme_groups:
            groups = [item.strip() for item in args.rhyme_groups.split(",") if item.strip()]
        else:
            groups = []
            for index, line in enumerate(cipai.lines):
                if not line.rhyme:
                    continue
                char = cjk(draft.lines[index])[-1] if index < len(draft.lines) else ""
                possible = char_rhyme_groups(char) if char else frozenset()
                groups.append(next(iter(possible)) if possible else "?")
        report = validate_ci(draft, cipai, groups)
    else:
        spec = spec_for_genre(
            args.genre,
            line_length=args.line_length,
            first_rhyme=args.first_rhyme,
            rhyme_group=args.rhyme,
        )
        report = validate_shi(draft, spec)

    if report.ok:
        print("校验：通过")
        return 0
    print("校验：未通过")
    for issue in report.issues:
        print(f"- [{issue.level}] {issue.code}: {issue.message}")
    return 1


def _cmd_import_seed(args) -> int:
    count, dupes = import_seed(args.path, args.dest)
    print(f"导入 {count} 首；重复：{dupes}")
    return 0


def _cmd_style_build(args) -> int:
    config = load_config(args.config)
    profile = args.profile or config.default_profile
    poems = _load_seed()
    stats = analyze_corpus(poems)
    card = build_style_card(stats, poems, llm=build_client(profile, config))
    path = Path("style/style-card.draft.md")
    write_style_card(path, card)
    print(path)
    return 0


def _cmd_style_review(args) -> int:
    config = load_config(args.config)
    profile = args.profile or config.default_profile
    draft_path = Path("style/style-card.draft.md")
    if not draft_path.exists():
        raise FileNotFoundError(f"找不到风格卡草稿：{draft_path}")
    card = review_style_card(
        load_style_card(draft_path),
        llm=build_client(profile, config),
    )
    path = Path("style/style-card.md")
    write_style_card(path, card)
    print(path)
    return 0


def _cmd_cipai_add(args) -> int:
    cipai = parse_spectrum(args.file.read_text(encoding="utf-8"))
    default_tone = args.rhyme_tone
    lines: list[dict] = []
    sections: dict[int, list[dict]] = {}
    for line in cipai.lines:
        tone = line.rhyme_tone
        if line.rhyme and tone is None:
            tone = default_tone
        if line.rhyme and tone is None:
            raise ValueError(
                f"{cipai.name} 有韵位未标平仄；请用 --rhyme-tone 指定"
            )
        item: dict = {"pattern": line.pattern, "rhyme": line.rhyme}
        if tone:
            item["rhyme_tone"] = tone
        sections.setdefault(line.section, []).append(item)
        lines.append(item)

    data = {
        "name": cipai.name,
        "variant": cipai.variant,
        "sections": [
            {"lines": sections[index]} for index in sorted(sections)
        ],
    }
    filename = "-".join(lazy_pinyin(cipai.name)) + ".yaml"
    out = Path("data/cipai") / filename
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    print(out)
    return 0


def _cmd_accept(args) -> int:
    out = accept_run(args.run_id, args.file)
    print(out)
    return 0


def _add_generation_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("--profile", default=None)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--genre", required=True, choices=GENRES)
    parser.add_argument("--cipai", default=None)
    parser.add_argument("--line-length", type=int, default=5)
    parser.add_argument("--rhyme", default=None)
    parser.add_argument(
        "--first-rhyme", dest="first_rhyme", action="store_true", default=True
    )
    parser.add_argument(
        "--no-first-rhyme", dest="first_rhyme", action="store_false"
    )
    parser.add_argument("--max-attempts", type=int, default=3)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="eh-poem",
        description="用个人风格生成中文诗词；诗查新韵，词查词牌谱。",
    )
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("import-seed", help="导入种子诗集")
    p.add_argument("path", type=Path)
    p.add_argument("--dest", type=Path, default=Path("corpus/seed/seed.md"))
    p.set_defaults(func=_cmd_import_seed)

    p = sub.add_parser("generate", help="生成一首诗或词")
    _add_generation_args(p)
    p.set_defaults(func=_cmd_generate)

    p = sub.add_parser("compare", help="用多个模型配置同题对比")
    _add_generation_args(p)
    p.add_argument("--profiles", required=True)
    p.set_defaults(func=_cmd_compare)

    p = sub.add_parser("validate", help="校验一个草稿")
    p.add_argument("file", type=Path)
    p.add_argument("--genre", required=True, choices=GENRES)
    p.add_argument("--cipai", default=None)
    p.add_argument("--line-length", type=int, default=5)
    p.add_argument("--rhyme", default=None)
    p.add_argument("--rhyme-groups", default=None)
    p.add_argument(
        "--first-rhyme", dest="first_rhyme", action="store_true", default=True
    )
    p.add_argument(
        "--no-first-rhyme", dest="first_rhyme", action="store_false"
    )
    p.set_defaults(func=_cmd_validate)

    style = sub.add_parser("style", help="生成/审查风格卡")
    style_sub = style.add_subparsers(dest="style_command")
    sb = style_sub.add_parser("build", help="生成风格卡草稿")
    sb.add_argument("--config", type=Path, default=Path("config.toml"))
    sb.add_argument("--profile", default=None)
    sb.set_defaults(func=_cmd_style_build)
    sr = style_sub.add_parser("review", help="人工审查风格卡")
    sr.add_argument("--config", type=Path, default=Path("config.toml"))
    sr.add_argument("--profile", default=None)
    sr.set_defaults(func=_cmd_style_review)

    cipai = sub.add_parser("cipai", help="管理词牌谱")
    cipai_sub = cipai.add_subparsers(dest="cipai_command")
    ca = cipai_sub.add_parser("add", help="从文本谱新增词牌")
    ca.add_argument("name")
    ca.add_argument("--file", type=Path, required=True)
    ca.add_argument("--rhyme-tone", choices=["平", "仄"], default=None)
    ca.set_defaults(func=_cmd_cipai_add)

    p = sub.add_parser("accept", help="接受一次生成并保存定稿")
    p.add_argument("run_id")
    p.add_argument("--file", type=Path, default=None)
    p.set_defaults(func=_cmd_accept)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        return int(exc.code or 0)
    func = getattr(args, "func", None)
    if func is None:
        parser.print_help()
        return 1
    try:
        return int(func(args) or 0)
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
