"""EH-Poem-Style 快速 demo。

用途：用用户自己的 56 首作品做风格提示，分别调用 DeepSeek V4.1 与本地模型，
生成同一题目的诗/词，直接对比效果。不是最终架构，只是最快看到风格的一条竖切。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

from pypinyin import Style, pinyin

ROOT = Path(__file__).resolve().parent
SEED = ROOT / "corpus" / "seed" / "seed.md"
OUT = ROOT / "demo_output"

RHYME_GROUPS = {
    "a": "一麻", "ia": "一麻", "ua": "一麻",
    "o": "二波", "e": "二波", "uo": "二波",
    "ie": "三皆", "ve": "三皆",
    "ai": "四开", "uai": "四开",
    "ei": "五微", "ui": "五微", "uei": "五微",
    "ao": "六豪", "iao": "六豪",
    "ou": "七尤", "iu": "七尤", "iou": "七尤",
    "an": "八寒", "ian": "八寒", "uan": "八寒", "van": "八寒",
    "en": "九文", "in": "九文", "un": "九文", "vn": "九文",
    "ang": "十唐", "iang": "十唐", "uang": "十唐",
    "eng": "十一庚", "ing": "十一庚", "ong": "十一庚", "iong": "十一庚",
    "i": "十二齐", "v": "十二齐", "er": "十二齐",
    "u": "十四姑",
}

PROFILES = {
    "deepseek": {
        "label": "DeepSeek V4.1 Flash",
        "base_url": os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
        "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
        "model": os.environ.get("DEEPSEEK_MODEL", "deepseek-flash"),
        "timeout": 120,
    },
    "local": {
        "label": "本地模型",
        "base_url": os.environ.get("LOCAL_BASE_URL", "http://127.0.0.1:11434/v1"),
        "api_key": os.environ.get("LOCAL_API_KEY", "local"),
        "model": os.environ.get("LOCAL_MODEL", "qwen3.5:4b"),
        "timeout": 240,
    },
}


def parse_seed(text: str):
    text = text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"^##\s+\d+\s+(.+)$", text, flags=re.MULTILINE)
    poems, seen = [], set()
    for i in range(1, len(blocks), 2):
        title = blocks[i].strip()
        lines = tuple(
            line.strip()
            for line in blocks[i + 1].splitlines()
            if line.strip() and not line.lstrip().startswith(">")
        )
        if not lines or lines in seen:
            continue
        seen.add(lines)
        cipai = title.split("·", 1)[0].strip() if "·" in title else None
        poems.append({"title": title, "lines": lines, "cipai": cipai})
    return poems


def cjk(line: str) -> str:
    return "".join(ch for ch in line if "\u3400" <= ch <= "\u9fff")


def rhyme_group(char: str) -> str | None:
    finals = pinyin(char, style=Style.FINALS, heteronym=True)
    initials = pinyin(char, style=Style.INITIALS, heteronym=True)
    if not finals or not finals[0]:
        return None
    fin = finals[0][0].replace("ü", "v")
    ini = (initials[0][0] if initials and initials[0] else "") or ""
    if fin == "i" and ini in {"zh", "ch", "sh", "r", "z", "c", "s"}:
        return "十三支"
    return RHYME_GROUPS.get(fin)


def style_card(poems) -> str:
    chars = Counter()
    lengths = Counter()
    for p in poems:
        for line in p["lines"]:
            clean = cjk(line)
            lengths[len(clean)] += 1
            chars.update(clean)
    top = "、".join(ch for ch, _ in chars.most_common(40))
    common_lengths = "、".join(f"{n}言" for n, _ in lengths.most_common(3))
    return (
        f"- 常用字（按频次）：{top}\n"
        f"- 句长：以{common_lengths}为主，短句直陈，少用长调铺陈。\n"
        "- 意象：古迹与废墟、旅途、风沙、星月与夜、灯火与酒、历史人物。\n"
        "- 句法：五/七言短句为主，少用典故；结尾常从眼前景物转到自省、怀古或感叹。\n"
        "- 情感：苍凉、怀古、理想未酬，偶尔自嘲；不堆砌华丽辞藻。\n"
        "- 用韵：中华新韵，偏爱 an/ang/eng/ou 一类开口韵。\n"
        "- 忌用：网络语、过于浓艳的形容词、生僻典故。"
    )


def pick_examples(poems, limit=None):
    if limit is None:
        return list(poems)
    wanted = [
        "游巨石阵", "夜观花树", "入京", "观潮", "忆齐",
        "相见欢·猜", "菩萨蛮·元日", "游开封", "静夜思", "午间吃饭",
    ]
    by_title = {p["title"]: p for p in poems}
    picked = []
    for name in wanted:
        for title, poem in by_title.items():
            if name in title:
                picked.append(poem)
                break
    return picked[:limit]


def format_examples(examples) -> str:
    return "\n\n".join(
        f"《{p['title']}》\n" + "\n".join(p["lines"]) for p in examples
    )


def build_messages(card: str, examples, task: str):
    system = (
        "你是一位中文旧体诗词写作者。请严格模仿下面这位作者的个人风格，"
        "不要模仿任何古代名家，也不要解释你在做什么。\n\n"
        f"【风格卡】\n{card}\n\n"
        f"【作者全部作品】\n{format_examples(examples)}\n\n"
        "学习用词、意象、句法、情感和转折方式；不要整句照抄原作，"
        "与题目无关的原句不要复用。\n\n"
        "【输出要求】只输出一个 JSON 对象，不要 Markdown 代码块，不要前后说明。"
        '字段：{"title": "题目", "genre": "七绝或如梦令", '
        '"lines": ["第一句", "第二句", "..."], "rhyme": ["韵脚字"]}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": task},
    ]


def chat(profile, messages, json_mode=False):
    if not profile["api_key"]:
        raise RuntimeError(f"{profile['label']} 没有 API Key")
    payload = {
        "model": profile["model"],
        "messages": messages,
        "temperature": 0.9,
        "max_tokens": 3000,
        "stream": False,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    def post(current_payload):
        req = urllib.request.Request(
            profile["base_url"].rstrip("/") + "/chat/completions",
            data=json.dumps(current_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {profile['api_key']}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=profile["timeout"]) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        data = post(payload)
    except urllib.error.HTTPError as e:
        # 有些本地 OpenAI 兼容服务不支持 response_format，退回普通模式
        if json_mode and e.code == 400:
            payload.pop("response_format", None)
            data = post(payload)
        else:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"HTTP {e.code}: {detail}") from e
    msg = data["choices"][0]["message"]
    return (msg.get("content") or msg.get("reasoning_content") or "").strip()


def parse_reply(text: str):
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start : end + 1]
    return json.loads(text)


def check_shi(lines):
    lines = [cjk(x) for x in lines]
    problems = []
    if len(lines) != 4:
        problems.append(f"句数 {len(lines)}，应为 4")
    for i, line in enumerate(lines, 1):
        if len(line) != 7:
            problems.append(f"第 {i} 句 {len(line)} 字，应为 7")
    if len(lines) >= 4 and len(lines[1]) and len(lines[3]):
        g2, g4 = rhyme_group(lines[1][-1]), rhyme_group(lines[3][-1])
        if g2 != g4:
            problems.append(f"韵脚 {lines[1][-1]}({g2}) / {lines[3][-1]}({g4}) 不同部")
    return problems


def tones_of(line: str):
    """按整句上下文取最常用读音，再转成现代平仄。1/2 声为平，3/4 声为仄。"""
    result = []
    for item in pinyin(cjk(line), style=Style.TONE3, heteronym=False):
        value = item[0] if item else ""
        if value and value[-1] in "12":
            result.append("平")
        elif value and value[-1] in "34":
            result.append("仄")
        else:
            result.append(None)
    return result


def check_ci(lines):
    want = [6, 6, 5, 6, 2, 2, 6]
    patterns = ["中仄仄平平仄", "中仄仄平平仄", "中仄仄平平", "中仄仄平平仄", "平仄", "平仄", "中仄仄平平仄"]
    rhyme_lines = [0, 1, 3, 4, 5, 6]
    lines = [cjk(x) for x in lines]
    problems = []
    if len(lines) != len(want):
        return [f"句数 {len(lines)}，应为 {len(want)}"]
    for i, (line, n, pattern) in enumerate(zip(lines, want, patterns), 1):
        if len(line) != n:
            problems.append(f"第 {i} 句 {len(line)} 字，应为 {n}")
            continue
        actual_tones = tones_of(line)
        for j, (ch, expected) in enumerate(zip(line, pattern), 1):
            if expected == "中":
                continue
            actual = actual_tones[j - 1] if j - 1 < len(actual_tones) else None
            if actual != expected:
                problems.append(f"第 {i} 句第 {j} 字「{ch}」应{expected}实{actual or '未知'}")
    groups = []
    for idx in rhyme_lines:
        if idx < len(lines) and lines[idx]:
            groups.append(rhyme_group(lines[idx][-1]))
    if len(set(groups)) > 1:
        problems.append(f"韵脚不同部：{groups}")
    for idx in rhyme_lines:
        if idx < len(lines) and lines[idx]:
            t = tones_of(lines[idx])[-1] if tones_of(lines[idx]) else None
            if t != "仄":
                problems.append(f"第 {idx + 1} 句韵脚「{lines[idx][-1]}」应仄实{t or '未知'}")
    return problems


def review_style(card: str) -> str:
    """人工审查 + 多轮修改。回车接受，e 用记事本编辑，r 让模型按反馈改。"""
    draft = OUT / "style-card.editing.md"
    while True:
        print("\n===== 风格卡草稿 =====")
        print(card)
        try:
            choice = input("\n回车接受 / e 用记事本编辑 / r 让模型改 / q 放弃：").strip().lower()
        except EOFError:
            print("\n（非交互环境，保留草稿）")
            return card
        if choice in {"", "a"}:
            path = ROOT / "style" / "style-card.md"
            path.parent.mkdir(exist_ok=True)
            path.write_text(card, encoding="utf-8")
            print(f"已保存：{path}")
            return card
        if choice == "q":
            return card
        if choice == "e":
            draft.write_text(card, encoding="utf-8")
            subprocess.run(["notepad", str(draft)], check=False)
            card = draft.read_text(encoding="utf-8")
            continue
        if choice == "r":
            feedback = input("想改哪里？").strip()
            if not feedback:
                continue
            messages = [
                {
                    "role": "system",
                    "content": (
                        "你在帮用户修改一份中文诗词风格卡。保留原有结构和事实，"
                        "只按用户反馈增删改，不解释，直接输出修改后的完整风格卡。"
                    ),
                },
                {"role": "user", "content": f"当前风格卡：\n{card}\n\n修改意见：{feedback}"},
            ]
            try:
                card = chat(PROFILES["deepseek"], messages).strip()
            except Exception as e:
                print(f"修改失败：{e}")


TASKS = [
    {
        "name": "qijue",
        "kind": "诗",
        "task": (
            "写一首七绝，主题：夜游多瑙河，灯影落在静水上，人在异乡。\n"
            "要求：四句，每句七字；第 2、4 句押中华新韵同一韵部，第 1 句可押可不押；"
            "不要求平仄；语言克制，不要堆砌辞藻。"
        ),
    },
    {
        "name": "rumengling",
        "kind": "词",
        "task": (
            "写一首《如梦令》，主题：清晨林间忽然惊起的鸟。\n"
            "每句字数必须是：6、6、5、6、2、2、6。\n"
            "押仄声韵，用中华新韵同一韵部（十四部）；韵脚字从这些字里选：有、酒、柳、后、走、久、手、首、口、守、瘦、透、漏、候、旧、袖、秀、昼、宙、兽、授、陋、豆、斗；一韵到底。\n"
            "平仄按现代普通话最常用读音判断，不要为合谱改用生僻读音。\n"
            "不要分析，不要解释，直接给最终 JSON。"
        ),
    },
]


def check_copy(lines, seed_lines):
    seed = {cjk(x) for x in seed_lines}
    problems = []
    for i, line in enumerate(lines, 1):
        clean = cjk(line)
        if clean and clean in seed:
            problems.append(f"第 {i} 句整句照抄原作：{clean}")
    return problems


def generate(profile, messages, kind, seed_lines=(), max_attempts=3):
    current = list(messages)
    last_raw, last_data, last_problems = "", None, []
    for attempt in range(1, max_attempts + 1):
        raw = chat(profile, current, json_mode=True)
        try:
            data = parse_reply(raw)
        except Exception as e:
            last_raw, last_data, last_problems = raw, None, [f"JSON 解析失败：{e}"]
        else:
            lines = data.get("lines", [])
            problems = check_shi(lines) if kind == "诗" else check_ci(lines)
            problems += check_copy(lines, seed_lines)
            last_raw, last_data, last_problems = raw, data, problems
            if not problems:
                return raw, data, problems, attempt
        if attempt < max_attempts:
            current = current + [
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": "上一版校验未通过：" + "；".join(last_problems)
                    + "。只改错处，保留已合规部分，仍只输出 JSON。",
                },
            ]
    return last_raw, last_data, last_problems, max_attempts


def main():
    parser = argparse.ArgumentParser(description="EH-Poem-Style 快速 demo")
    parser.add_argument("--review-style", action="store_true", help="生成风格卡后进入人工审查/多轮修改")
    parser.add_argument("--style-file", type=Path, help="直接使用手写或已审查的风格卡")
    parser.add_argument("--max-examples", type=int, default=0, help="示例上限；0 表示全部（默认）")
    args = parser.parse_args()

    if not SEED.exists():
        sys.exit(f"找不到种子文件：{SEED}")
    poems = parse_seed(SEED.read_text(encoding="utf-8"))
    seed_lines = [line for p in poems for line in p["lines"]]
    examples = pick_examples(poems, args.max_examples or None)
    OUT.mkdir(exist_ok=True)

    if args.style_file:
        card = args.style_file.read_text(encoding="utf-8")
    else:
        card = style_card(poems)
    (OUT / "style-card.draft.md").write_text(card, encoding="utf-8")
    if args.review_style:
        card = review_style(card)
        (OUT / "style-card.draft.md").write_text(card, encoding="utf-8")

    (OUT / "examples.txt").write_text(format_examples(examples), encoding="utf-8")

    print(f"种子：{len(poems)} 首")
    print(f"示例：{len(examples)} 首（{'全部' if len(examples) == len(poems) else '上限 ' + str(args.max_examples)}）\n")

    for task in TASKS:
        messages = build_messages(card, examples, task["task"])
        for key, profile in PROFILES.items():
            print(f"\n===== {profile['label']} / {profile['model']} / {task['name']} =====")
            try:
                raw, data, problems, attempts = generate(profile, messages, task["kind"], seed_lines)
                (OUT / f"{key}-{task['name']}.raw.txt").write_text(raw, encoding="utf-8")
                if data is None:
                    text = f"生成失败（{attempts} 次）：" + "；".join(problems)
                else:
                    lines = data.get("lines", [])
                    verdict = "通过" if not problems else "；".join(problems)
                    text = (
                        f"《{data.get('title', '')}》\n"
                        + "\n".join(lines)
                        + f"\n\n韵脚：{data.get('rhyme', [])}"
                        + f"\n校验：{verdict}"
                        + f"\n尝试：{attempts} 次"
                    )
                (OUT / f"{key}-{task['name']}.txt").write_text(text, encoding="utf-8")
                print(text)
            except Exception as e:
                print(f"失败：{e}")


if __name__ == "__main__":
    main()
