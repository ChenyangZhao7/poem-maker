# EH-Poem-Style 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立一个本地中文诗词生成工具：用用户 56 首作品做风格样本，诗按中华新韵只查押韵与句数/字数，词按词牌谱严格校验，并支持 DeepSeek V4.1 与本地模型同题对比。

**Architecture:** Python 3.11+ 命令行工具。数据层（中华新韵、现代平仄、词牌谱）与校验器是"厚资产"，不依赖模型；模型只负责在硬约束内遣词造句。生成流程为：算硬约束 → 组装提示词 → 调用 OpenAI 兼容接口 → 解析 JSON → 校验 → 带错误重试 → 落盘。

**Tech Stack:** Python 3.11+、`httpx`（HTTP）、`pypinyin`（新韵）、`PyYAML`（词牌谱）、`tomllib`（配置）、`pytest`（测试）、`argparse`（CLI）。

**Spec:** `docs/superpowers/specs/2026-11-06-eh-poem-style-design.md`

## Global Constraints

- 平台：Windows，本地运行；不假设本地 GPU。
- 诗：只用**中华新韵**查押韵；声调不限；保留句数/字数；**不校验平仄、粘对、孤平、三平调、对仗**。
- 词：按词牌谱逐字校验**平仄、句读、韵位、韵部（中华新韵）**，不合判错误。
- 诗、词都不引入平水韵/词林正韵，不区分入声；一律按现代普通话读音。
- 词的平仄按**整句上下文的最常用读音**判定（pypinyin 默认读音），不为了合谱改用生僻读音；最常用读音不合谱判错误。
- 词牌多体时默认取最常用正体；用户语料中出现过的体优先。
- v1 不训练/LoRA；不写死任何模型厂商；API Key 不进仓库。
- 用户以中文交流；提示词、报告、错误信息用中文。
- 生成结果与人工修改必须落盘；`runs/` 保存每次尝试，`corpus/poems/` 保存定稿。
- 词的一个 `lines` 元素 = 词牌谱的一行；行内标点保留但校验时忽略，不计入字数。
- 未知字、简繁消歧失败、多音字无法自洽：判**错误**并列出候选，不静默跳过。

## Review Focus

1. **标点、空白、代码围栏**：生成文本常带 `，。`、换行、```json 围栏；校验前必须剥离标点/空白，不能把标点计入字数或让解析崩溃。
2. **韵脚多音字**：整首/整个韵段求一组自洽读音；不唯一时报错并列出候选，不静默取第一个。
3. **非 JSON 响应**：模型可能返回解释文字、缺字段、JSON 前后带话；必须提取或给出可读错误并重试，不能抛栈。
4. **词牌谱混写**：`⊙`、`中`、`可平可仄`、`△/▲`、`（韵）`、`（换韵）` 混用；必须归一化，失败给出行列定位。
5. **拼音/新韵查不到的字**：包括生僻字、轻声或无法判定平仄的字；判错误，不跳过。多音字按整句最常用读音，不为了合谱取生僻读音。

---

## 文件结构

```
pyproject.toml
config.example.toml
.gitignore
README.md
data/
  cipai/
    rumengling.yaml
    jiangchengzi-35.yaml
    xiangjianhuan.yaml
    pusalman.yaml
    nanxiangzi-27.yaml
    yiwangsun.yaml
    yugezi.yaml
    yiqine.yaml
corpus/
  seed/seed.md               # 用户 56 首（从 D:\Desktop\诗集.md 复制）
  poems/YYYY/MM/*.md         # 定稿
style/
  style-card.md
runs/                        # 每次生成
src/eh_poem_style/
  __init__.py
  __main__.py
  cli.py
  config.py
  models.py
  xinyun.py
  pingze.py
  cipai.py
  corpus.py
  style.py
  llm.py
  prompt.py
  generate.py
  compare.py
  validate/
    __init__.py
    report.py
    shi.py
    ci.py
tests/
  fixtures/
    seed_small.md
    poems.py
  test_config.py
  test_cli.py
  test_xinyun.py
  test_pingze.py
  test_cipai.py
  test_validate_shi.py
  test_validate_ci.py
  test_corpus.py
  test_style.py
  test_llm.py
  test_prompt.py
  test_generate.py
  test_compare.py
```

---

### Task 1: 项目骨架、配置与 CLI 入口

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `README.md`
- Create: `config.example.toml`
- Create: `src/eh_poem_style/__init__.py`
- Create: `src/eh_poem_style/__main__.py`
- Create: `src/eh_poem_style/config.py`
- Create: `src/eh_poem_style/models.py`
- Create: `src/eh_poem_style/cli.py`
- Test: `tests/test_config.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `ModelProfile(name, base_url, api_key, model, temperature=0.8, max_tokens=2048, timeout=60.0)` — frozen dataclass.
  - `Config(default_profile: str, models: dict[str, ModelProfile])` — frozen dataclass.
  - `load_config(path: Path | None = None) -> Config`：读取 `config.toml`；`api_key` 支持 `env:NAME`；缺失或空值抛 `ConfigError`。
  - `main(argv: list[str] | None = None) -> int`。
  - `models.py` 同时定义 `PoemDraft`、`Issue`、`Report`、`GenerateRequest`、`LLMClient`（后续任务使用）。

- [ ] **Step 1: 写失败测试（配置）**

`tests/test_config.py`：

```python
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
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_config.py -v`

Expected: FAIL，`ModuleNotFoundError: No module named 'eh_poem_style'` 或 `ConfigError` 未定义。

- [ ] **Step 3: 实现骨架与配置**

`pyproject.toml` 关键值：

```toml
[project]
name = "eh-poem-style"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["httpx>=0.27", "pypinyin>=0.53", "PyYAML>=6.0"]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[project.scripts]
eh-poem = "eh_poem_style.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

`config.example.toml`：

```toml
default_profile = "deepseek"

[models.deepseek]
base_url = "https://api.deepseek.com/v1"
api_key = "env:DEEPSEEK_API_KEY"
model = "deepseek-chat"   # 按账号实际模型名修改（DS V4.1）
temperature = 0.8
max_tokens = 2048
timeout = 60

[models.local]
base_url = "http://127.0.0.1:11434/v1"
api_key = "local"
model = "your-local-model"
temperature = 0.8
max_tokens = 2048
timeout = 120
```

`models.py`：

```python
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
    def complete(self, messages: list[dict], **opts) -> str: ...
```

`load_config` 用 `tomllib`；`env:NAME` 解析为 `os.environ[NAME]`，缺失抛 `ConfigError`。默认路径为仓库根目录的 `config.toml`（相对 `Path.cwd()`）。

`cli.py` 先用 `argparse` 建子命令：`import-seed`、`style`、`generate`、`compare`、`validate`、`cipai`、`accept`；未实现时打印 `not implemented` 并返回 `1`；`--help` 返回 `0`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_config.py -v`

Expected: PASS。

- [ ] **Step 5: 写 CLI 帮助测试**

```python
def test_help_lists_commands(capsys):
    assert main(["--help"]) == 0
    out = capsys.readouterr().out
    for cmd in ["import-seed", "style", "generate", "compare", "validate", "cipai", "accept"]:
        assert cmd in out
```

- [ ] **Step 6: 运行测试**

Run: `python -m pytest tests/test_cli.py -v`

Expected: PASS。

- [ ] **Step 7: 初始化仓库并提交**

```powershell
git init
git add pyproject.toml .gitignore README.md config.example.toml src tests
git commit -m "chore: scaffold package, config, and CLI"
```

`.gitignore` 至少包含：`config.toml`、`runs/`、`__pycache__/`、`.pytest_cache/`、`*.egg-info/`、`.venv/`。

---

### Task 2: 中华新韵

**Files:**
- Create: `src/eh_poem_style/xinyun.py`
- Test: `tests/test_xinyun.py`

**Interfaces:**
- Produces:
  - `RHYME_GROUPS: dict[str, tuple[str, ...]]`：韵母 → 部名。
  - `rhyme_groups(char: str) -> frozenset[str]`：一个字的全部可能韵部（多音字返回多个）。
  - `RhymeResolution(group: str | None, notes: tuple[str, ...] = ())` — frozen dataclass。
  - `resolve_rhyme(chars: Sequence[str], preferred: str | None = None) -> RhymeResolution`：求一组自洽韵部；无解返回 `group=None`。多解时先取 `preferred`；否则对每个候选部求"各字读音序号之和"（0=最常用），取最小；最小和并列也返回 `group=None` 并写 notes（避免用生僻读音凑韵）。
  - `candidates(group: str, chars: Iterable[str]) -> list[str]`：从给定字集里筛出属于该部的字。

- [ ] **Step 1: 写失败测试**

```python
from eh_poem_style.xinyun import resolve_rhyme, rhyme_groups

def test_guang_huang_same_group():
    assert "十唐" in rhyme_groups("光")
    assert resolve_rhyme(["光", "黄"]).group == "十唐"

def test_han_dan_same_group():
    assert resolve_rhyme(["寒", "淡"]).group == "八寒"

def test_deng_sheng_same_group():
    assert resolve_rhyme(["灯", "生"]).group == "十一庚"

def test_qi_xi_di_same_group():
    assert resolve_rhyme(["齐", "袭", "敌"]).group == "十二齐"

def test_shuo_mei_no_common_group():
    assert resolve_rhyme(["说", "没"]).group is None

def test_zhi_is_zhisan_zhi():
    assert rhyme_groups("知") == frozenset({"十三支"})
    assert "十二齐" not in rhyme_groups("知")

def test_er_and_yu_are_qier():
    assert "十二齐" in rhyme_groups("儿")
    assert "十二齐" in rhyme_groups("鱼")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_xinyun.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现新韵归部**

用 `pypinyin.pinyin(char, style=Style.FINALS, heteronym=True)` 取韵母，`Style.INITIALS` 取声母；把 `ü` 与 `v` 统一为 `v`。归部表：

```python
RHYME_GROUPS = {
    "a": ("一麻",), "ia": ("一麻",), "ua": ("一麻",),
    "o": ("二波",), "e": ("二波",), "uo": ("二波",),
    "ie": ("三皆",), "ve": ("三皆",),
    "ai": ("四开",), "uai": ("四开",),
    "ei": ("五微",), "ui": ("五微",), "uei": ("五微",),
    "ao": ("六豪",), "iao": ("六豪",),
    "ou": ("七尤",), "iu": ("七尤",), "iou": ("七尤",),
    "an": ("八寒",), "ian": ("八寒",), "uan": ("八寒",), "van": ("八寒",),
    "en": ("九文",), "in": ("九文",), "un": ("九文",), "vn": ("九文",),
    "ang": ("十唐",), "iang": ("十唐",), "uang": ("十唐",),
    "eng": ("十一庚",), "ing": ("十一庚",), "ong": ("十一庚",), "iong": ("十一庚",),
    "i": ("十二齐",), "v": ("十二齐",), "er": ("十二齐",),
    "u": ("十四姑",),
}
```

`i` 的例外：声母属于 `zh ch sh r z c s` 时归**十三支**。`candidates` 对 `chars` 逐个调用 `rhyme_groups` 并筛 `group`。

`rhyme_groups` 必须保留 pypinyin 的 heteronym 顺序（常用在前）；`resolve_rhyme` 用这个顺序算"读音序号和"，避免 `说/没` 这类用两个生僻读音凑出韵的情况。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_xinyun.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/eh_poem_style/xinyun.py tests/test_xinyun.py
git commit -m "feat: add Zhonghua Xinyun rhyme grouping"
```

---

### Task 3: 现代平仄层（pypinyin）

**Files:**
- Create: `src/eh_poem_style/pingze.py`
- Test: `tests/test_pingze.py`

**Interfaces:**
- Produces:
  - `tone_of_line(line: str) -> tuple[str | None, ...]`：按整句上下文取最常用读音；1/2 声为 `"平"`，3/4 声为 `"仄"`，轻声或未知为 `None`；标点被忽略。
  - `tone_of_char(char: str) -> str | None`：单字默认读音的平仄，`tone_of_line(char)[0]`。
  - `is_tone(char: str, expected: Literal["平", "仄"], context: str | None = None) -> bool`。
  - `PingzeError`：整句完全无法取音时抛出。

- [ ] **Step 1: 写失败测试**

```python
import pytest
from eh_poem_style.pingze import tone_of_char, tone_of_line

def test_line_tones_use_context():
    assert tone_of_line("晨日入深林口") == ("平", "仄", "仄", "平", "平", "仄")

def test_common_readings():
    assert tone_of_char("国") == "平"   # guó
    assert tone_of_char("月") == "仄"   # yuè
    assert tone_of_char("一") == "平"   # yī

def test_punctuation_ignored():
    assert tone_of_line("晨日，入深林。") == ("平", "仄", "仄", "平", "平")

def test_unknown_returns_none():
    assert tone_of_char("𠀀") is None
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_pingze.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- `tone_of_line` 先用与校验器相同的 `cjk()` 剥掉非汉字，再调用 `pypinyin.pinyin(text, style=Style.TONE3, heteronym=False)`。
- 每个音节取末尾数字：`1/2` → `"平"`，`3/4` → `"仄"`，`5`/无数字 → `None`。
- `tone_of_char` 用 `heteronym=True` 取第一个（最常用）读音；仍无读音返回 `None`。
- 不做入声、不查古音；这是"现代新韵"的明确取舍。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_pingze.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/eh_poem_style/pingze.py tests/test_pingze.py
git commit -m "feat: add modern tone lookup for ci validation"
```

---

### Task 4: 词牌谱 DSL 与四个预置词牌

**Files:**
- Create: `src/eh_poem_style/cipai.py`
- Create: `data/cipai/rumengling.yaml`
- Create: `data/cipai/jiangchengzi-35.yaml`
- Create: `data/cipai/xiangjianhuan.yaml`
- Create: `data/cipai/pusalman.yaml`
- Test: `tests/test_cipai.py`

**Interfaces:**
- Produces:
  - `CipaiParseError(line_no: int, col: int, message: str)`。
  - `CipaiLine(pattern: str, rhyme: bool, rhyme_tone: Literal["平", "仄"] | None, section: int)` — frozen dataclass；`pattern` 只含 `平/仄/中`。
  - `Cipai(name: str, variant: str, lines: tuple[CipaiLine, ...])` — frozen dataclass；属性 `line_count`、`section_count`。
  - `normalize_pattern(text: str) -> tuple[str, bool, str | None]`：返回 `(pattern, rhyme, rhyme_tone)`。
  - `parse_spectrum(text: str) -> Cipai`。
  - `load_cipai(path: Path) -> Cipai`。

- [ ] **Step 1: 写失败测试（符号归一化与错误定位）**

```python
import pytest
from eh_poem_style.cipai import CipaiParseError, normalize_pattern, parse_spectrum

def test_normalize_mixed_symbols():
    assert normalize_pattern("⊙平⊙仄仄平平（韵）") == ("中平中仄仄平平", True, None)

def test_normalize_delta_means_ping_rhyme():
    assert normalize_pattern("中平中仄△") == ("中平中仄", True, "平")

def test_normalize_triangle_means_ze_rhyme():
    assert normalize_pattern("中仄中平▲") == ("中仄中平", True, "仄")

def test_invalid_symbol_reports_position():
    with pytest.raises(CipaiParseError) as e:
        normalize_pattern("中平X")
    assert e.value.col == 3
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_cipai.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 DSL**

`normalize_pattern`：

- 去掉空白、`，`、`。`、`、`、`；`、`：`。
- `（韵）`、`(韵)`、`（平韵）`、`（仄韵）`、`（换韵）` 作为标记；`△` → 平韵，`▲` → 仄韵。
- `⊙`、`中`、`可平可仄` → `中`；`○` → `平`；`●` → `仄`。
- 其它字符视为非法，抛 `CipaiParseError(line_no=1, col=1-based位置, message=...)`。

`parse_spectrum`：第一行非空为 `name`；其余行按 `---` 或空行分段；每段为 `section`；每行调用 `normalize_pattern`。没有 rhyme 标记的行 `rhyme=False`。

- [ ] **Step 4: 写 YAML 数据**

`data/cipai/rumengling.yaml`：

```yaml
name: 如梦令
variant: 正体
sections:
  - lines:
      - {pattern: "中仄仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄仄平平", rhyme: false}
      - {pattern: "中仄仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄仄平平仄", rhyme: true, rhyme_tone: 仄}
```

`data/cipai/jiangchengzi-35.yaml`：

```yaml
name: 江城子
variant: 单调三十五字
sections:
  - lines:
      - {pattern: "中平中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中中中中", rhyme: false}
      - {pattern: "中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄中平平仄仄", rhyme: false}
      - {pattern: "平仄仄", rhyme: false}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
```

`data/cipai/xiangjianhuan.yaml`：

```yaml
name: 相见欢
variant: 正体
sections:
  - lines:
      - {pattern: "中平中仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄中平平仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中中仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄中平平仄仄平平", rhyme: true, rhyme_tone: 平}
```

`data/cipai/pusalman.yaml`：

```yaml
name: 菩萨蛮
variant: 正体
sections:
  - lines:
      - {pattern: "中平中仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平中仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中平平仄平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中平平仄仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中平平仄平", rhyme: true, rhyme_tone: 平}
```

- [ ] **Step 5: 写加载测试**

```python
def test_load_rumengling():
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    assert c.name == "如梦令"
    assert c.line_count == 7
    assert [l.pattern for l in c.lines][0] == "中仄仄平平仄"

def test_parse_sections():
    c = parse_spectrum("测试\n平仄（韵）\n---\n仄平（韵）")
    assert c.section_count == 2
```

- [ ] **Step 6: 运行测试，确认通过**

Run: `python -m pytest tests/test_cipai.py -v`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add src/eh_poem_style/cipai.py data/cipai tests/test_cipai.py
git commit -m "feat: add cipai DSL and four presets"
```

---

### Task 5: 诗校验器

**Files:**
- Create: `src/eh_poem_style/validate/__init__.py`
- Create: `src/eh_poem_style/validate/report.py`
- Create: `src/eh_poem_style/validate/shi.py`
- Test: `tests/test_validate_shi.py`
- Test fixture: `tests/fixtures/poems.py`

**Interfaces:**
- Consumes: `PoemDraft`、`Issue`、`Report`（Task 1），`xinyun`（Task 2）。
- Produces:
  - `ShiSpec(genre: str, line_length: int, line_count: int | None, first_rhyme: bool, rhyme_group: str | None = None)` — frozen dataclass。
  - `spec_for_genre(genre: str, line_length: int = 5, first_rhyme: bool = True, rhyme_group: str | None = None) -> ShiSpec`。
  - `strip_punctuation(line: str) -> str`：只保留 CJK 字符。
  - `validate_shi(draft: PoemDraft, spec: ShiSpec) -> Report`。

- [ ] **Step 1: 写失败测试**

```python
from eh_poem_style.models import PoemDraft
from eh_poem_style.validate.shi import ShiSpec, spec_for_genre, validate_shi

def draft(lines, genre="七绝"):
    return PoemDraft(title="t", genre=genre, cipai=None, lines=lines)

def test_wu_jue_passes():
    d = draft(["白日依山尽", "黄河入海流", "欲穷千里目", "更上一层楼"], "五绝")
    r = validate_shi(d, spec_for_genre("五绝", first_rhyme=False))
    assert r.ok

def test_user_qi_lu_passes():
    lines = ["荒草高天斜风吹", "斑石浅壑矗无声", "耳畔忽闻琵琶行", "悲顿心起愁难平",
             "烦杂琐事细细数", "妄学石林历永恒", "败军小卒几顺命", "乍有抬眼望星空"]
    r = validate_shi(draft(lines, "七律"), spec_for_genre("七律", first_rhyme=False))
    assert r.ok

def test_wrong_line_count_fails():
    r = validate_shi(draft(["黄河入海流", "更上一层楼"], "五绝"), spec_for_genre("五绝"))
    assert not r.ok
    assert any(i.code == "line_count" for i in r.issues)

def test_wrong_char_count_fails():
    r = validate_shi(draft(["黄河入海", "更上一层楼", "欲穷千里目", "更上一层楼"], "五绝"), spec_for_genre("五绝"))
    assert any(i.code == "line_length" for i in r.issues)

def test_rhyme_mismatch_fails():
    d = draft(["白日依山尽", "黄河入海流", "欲穷千里目", "更上一层台"], "五绝")
    r = validate_shi(d, spec_for_genre("五绝", first_rhyme=False))
    assert any(i.code == "rhyme_mismatch" for i in r.issues)

def test_shuo_mei_mismatch_fails():
    r = validate_shi(draft(["万事可入眼", "功过难评说", "且有恶与好", "妄议心中没"]), spec_for_genre("五绝", first_rhyme=False))
    assert any(i.code == "rhyme_mismatch" for i in r.issues)

def test_duplicate_rhyme_fails():
    r = validate_shi(draft(["黄河入海流", "更上一层楼", "欲穷千里目", "更上一层楼"]), spec_for_genre("五绝", first_rhyme=False))
    assert any(i.code == "duplicate_rhyme" for i in r.issues)

def test_punctuation_ignored():
    d = draft(["黄河入海流，", "更上一层楼。", "欲穷千里目，", "更上泰山头。"], "五绝")
    r = validate_shi(d, spec_for_genre("五绝", first_rhyme=False))
    assert not any(i.code == "line_length" for i in r.issues)
```

`spec_for_genre` 对五律/七律/五绝/七绝忽略传入的 `line_length`，按体裁取 5 或 7；`line_length` 只对古体生效。

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_validate_shi.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- `spec_for_genre` 映射：`五律(5,8)`、`七律(7,8)`、`五绝(5,4)`、`七绝(7,4)`、`古体(line_length, None)`；未知体裁抛 `ValueError`。
- `strip_punctuation`：`"".join(ch for ch in line if "\u3400" <= ch <= "\u9fff")`。
- 校验顺序：行数 → 每行字数 → 韵脚。
- 韵脚行：0-based 下标 `1,3,5,7...`；`first_rhyme=True` 时加下标 `0`。
- 取每行去标点后的最后一个字；`resolve_rhyme(rhyme_chars, preferred=spec.rhyme_group)`；`group is None` → `rhyme_mismatch`；有 note 时加 `warning`（code `polyphony`）。
- 若 `spec.rhyme_group` 给定且解析结果不等于它 → `rhyme_mismatch`。
- 韵脚字重复 → `duplicate_rhyme`（按字面重复判断，不去重音）。
- 报告 issue 的 `line` 用 1-based 行号。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_validate_shi.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/eh_poem_style/validate tests/test_validate_shi.py tests/fixtures/poems.py
git commit -m "feat: validate shi by line structure and Xinyun rhyme"
```

---

### Task 6: 词校验器

**Files:**
- Create: `src/eh_poem_style/validate/ci.py`
- Test: `tests/test_validate_ci.py`

**Interfaces:**
- Consumes: `PoemDraft`、`Report`（Task 1），`Cipai`（Task 4），`pingze`（Task 3），`xinyun`（Task 2）。
- Produces:
  - `validate_ci(draft: PoemDraft, cipai: Cipai, rhyme_groups: Sequence[str]) -> Report`。
  - `rhyme_groups` 与 `cipai.lines` 中 `rhyme=True` 的行按顺序一一对应；长度不符抛 `ValueError`。

- [ ] **Step 1: 写失败测试**

```python
from pathlib import Path
from eh_poem_style.cipai import load_cipai
from eh_poem_style.models import PoemDraft
from eh_poem_style.validate.ci import validate_ci

def ci_draft(lines, name="如梦令"):
    return PoemDraft(title="t", genre="词", cipai=name, lines=lines)

def test_rumengling_known_work_passes():
    lines = ["昨夜雨疏风骤", "浓睡不消残酒", "试问卷帘人", "却道海棠依旧", "知否", "知否", "应是绿肥红瘦"]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["七尤"] * 7)
    assert r.ok

def test_wrong_char_count_fails():
    lines = ["昨夜雨疏风", "浓睡不消残酒", "试问卷帘人", "却道海棠依旧", "知否", "知否", "应是绿肥红瘦"]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["七尤"] * 7)
    assert any(i.code == "line_length" for i in r.issues)

def test_wrong_rhyme_group_fails():
    lines = ["昨夜雨疏风骤", "浓睡不消残酒", "试问卷帘人", "却道海棠依旧", "知否", "知否", "应是绿肥红瘦"]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["一麻"] * 7)
    assert any(i.code == "rhyme_mismatch" for i in r.issues)

def test_wrong_tone_fails():
    # 第一行第 5 字应为平，换成“雨”（现代三声，仄）
    lines = ["昨夜雨疏雨骤", "浓睡不消残酒", "试问卷帘人", "却道海棠依旧", "知否", "知否", "应是绿肥红瘦"]
    c = load_cipai(Path("data/cipai/rumengling.yaml"))
    r = validate_ci(ci_draft(lines), c, ["七尤"] * 7)
    assert any(i.code == "tone_mismatch" for i in r.issues)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_validate_ci.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- 先按 `cipai.lines` 的行数、每行 `pattern` 长度检查 `draft.lines`；行数/字数错误后仍继续检查能检查的部分。
- 每行去标点后用 `pingze.tone_of_line(line)` 一次取整句平仄；逐字比对：`中` 跳过；`平/仄` 不符 → `tone_mismatch`；`None` → `unknown_char`。
- 韵脚：按顺序取 `rhyme_groups[i]`；该行末字的 `xinyun.rhyme_groups` 必须包含它；否则 `rhyme_mismatch`；查不到 → `unknown_char`。
- 多音字：`tone_of_line` 已按整句最常用读音取音；若同一字在该句中有多个读音，报告里标注"按常用读音 X"。
- 报告 `line` 用 1-based，`index` 用行内 1-based 字位。

- [ ] **Step 4: 增加换韵测试（相见欢）**

```python
def test_xiangjianhuan_switch_rhyme_passes():
    lines = ["无言独上西楼", "月如钩", "寂寞梧桐深院锁清秋", "剪不断", "理还乱", "是离愁", "别是一般滋味在心头"]
    c = load_cipai(Path("data/cipai/xiangjianhuan.yaml"))
    plan = ["七尤", "七尤", "七尤", "八寒", "八寒", "七尤", "七尤"]
    assert validate_ci(ci_draft(lines, "相见欢"), c, plan).ok
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_validate_ci.py -v`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/eh_poem_style/validate/ci.py tests/test_validate_ci.py
git commit -m "feat: validate ci against cipai patterns and modern tones"
```

---

### Task 7: 种子语料解析与导入

**Files:**
- Create: `src/eh_poem_style/corpus.py`
- Create: `corpus/seed/seed.md`（从 `D:\Desktop\诗集.md` 复制）
- Test: `tests/test_corpus.py`
- Test fixture: `tests/fixtures/seed_small.md`

**Interfaces:**
- Consumes: `PoemDraft`（Task 1）。
- Produces:
  - `Poem(title: str, lines: tuple[str, ...], genre: str, cipai: str | None, raw: str)` — frozen dataclass。
  - `parse_seed_markdown(text: str) -> tuple[list[Poem], list[str]]`：返回去重后的作品与重复标题列表。
  - `detect_cipai(title: str) -> str | None`：`词牌·题目` 返回词牌，否则 `None`。
  - `import_seed(src: Path, dst: Path) -> tuple[int, list[str]]`。

- [ ] **Step 1: 写失败测试**

```python
from eh_poem_style.corpus import parse_seed_markdown

def test_parse_and_dedupe():
    text = """# 诗集

## 01 游巨石阵

荒草高天斜风吹
斑石浅壑矗无声

## 02 如梦令·观奥尔梅克

林间啼声惊起，
折径光阴倒计。

## 03 游巨石阵

荒草高天斜风吹
斑石浅壑矗无声
"""
    poems, dupes = parse_seed_markdown(text)
    assert len(poems) == 2
    assert dupes == ["03 游巨石阵"]
    assert poems[1].genre == "词"
    assert poems[1].cipai == "如梦令"

def test_crlf_and_bom():
    text = "\ufeff## 01 测试\r\n\r\n一句\r\n二句\r\n"
    poems, _ = parse_seed_markdown(text)
    assert poems[0].lines == ("一句", "二句")
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_corpus.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- 用 `text.lstrip("\ufeff").replace("\r\n", "\n").replace("\r", "\n")` 规范化。
- 用正则 `^##\s+(\d+)\s+(.+)$` 切分；标题行前的内容忽略。
- 正文行 `strip()`；跳过空行；保留标点（后续校验剥离）。
- `detect_cipai` 用中文间隔号 `·` 切分，左侧去空白；左侧非空即视为词牌并令 `genre="词"`（用户 11 首词的标题都符合这一形态）。不要依赖 `data/cipai/` 白名单，否则尚未预置的词牌会被误判成诗。
- 去重键：`tuple(lines)`；保留首次出现的标题。
- `import_seed` 复制源文件到 `dst`（`corpus/seed/seed.md`），再解析，打印数量；若 `src.resolve() == dst.resolve()` 则跳过复制。

- [ ] **Step 4: 导入真实语料**

```powershell
New-Item -ItemType Directory -Force corpus/seed | Out-Null
Copy-Item "D:\Desktop\诗集.md" "corpus/seed/seed.md" -Force
python -c "from pathlib import Path; from eh_poem_style.corpus import parse_seed_markdown; poems, dupes = parse_seed_markdown(Path('corpus/seed/seed.md').read_text(encoding='utf-8')); print(len(poems), dupes)"
```

Expected：打印 `56 [...]`，重复列表含 `21 游呼啸山庄（重复）`。

- [ ] **Step 5: 运行测试，确认通过**

Run: `python -m pytest tests/test_corpus.py -v`

Expected: PASS。

- [ ] **Step 6: 提交**

```powershell
git add src/eh_poem_style/corpus.py corpus/seed/seed.md tests/test_corpus.py tests/fixtures/seed_small.md
git commit -m "feat: import and dedupe seed poems"
```

---

### Task 8: 风格统计与风格卡

**Files:**
- Create: `src/eh_poem_style/style.py`
- Create: `style/style-card.md`（生成物，提交一份初版）
- Test: `tests/test_style.py`

**Interfaces:**
- Consumes: `Poem`（Task 7），`xinyun`（Task 2），`pingze`（Task 3），`LLMClient`（Task 1，可空）。
- Produces:
  - `DEFAULT_EXAMPLE_COUNT: int | None = None`（`None` = 全部 56 首）。
  - `StyleStats(poem_count, ci_count, char_freq, line_lengths, shi_rhyme_groups, ci_rhyme_groups, top_ngrams)` — frozen dataclass。
  - `analyze_corpus(poems: Sequence[Poem]) -> StyleStats`。
  - `build_style_card(stats: StyleStats, poems: Sequence[Poem], llm: LLMClient | None = None, example_count: int | None = DEFAULT_EXAMPLE_COUNT) -> str`。
  - `review_style_card(draft: str, llm: LLMClient | None = None, input_fn=input, editor: Callable[[str], str] | None = None) -> str`：回车接受、`e` 编辑、`r` 多轮修改、`q` 放弃。
  - `write_style_card(path: Path, text: str) -> None`。
  - `load_style_card(path: Path) -> str`。

- [ ] **Step 1: 写失败测试**

```python
from eh_poem_style.corpus import Poem
from eh_poem_style.style import analyze_corpus, build_style_card, review_style_card

def test_stats_counts():
    poems = [
        Poem("a", ("荒草高天斜风吹", "斑石浅壑矗无声"), "诗", None, ""),
        Poem("b", ("林间啼声惊起", "折径光阴倒计"), "词", "如梦令", ""),
    ]
    stats = analyze_corpus(poems)
    assert stats.poem_count == 2
    assert stats.ci_count == 1
    assert stats.line_lengths[7] == 2

def test_card_includes_all_examples_by_default():
    poems = [Poem(f"t{i}", ("荒草高天斜风吹",), "诗", None, "") for i in range(12)]
    card = build_style_card(analyze_corpus(poems), poems)
    for section in ["常用字", "意象", "句法", "情感", "用韵", "忌用", "示例"]:
        assert section in card
    assert card.count("《t") == 12

def test_example_count_can_limit():
    poems = [Poem(f"t{i}", ("荒草高天斜风吹",), "诗", None, "") for i in range(12)]
    card = build_style_card(analyze_corpus(poems), poems, example_count=3)
    assert card.count("《t") == 3

def test_card_uses_llm_text():
    class Fake:
        def complete(self, messages, **opts):
            return "## 常用字\n荒草、残垣\n"
    card = build_style_card(analyze_corpus([]), [], llm=Fake())
    assert "荒草" in card

def test_review_accepts_on_enter():
    assert review_style_card("草稿", input_fn=lambda _: "") == "草稿"

def test_review_uses_feedback():
    class Fake:
        def complete(self, messages, **opts):
            return "改后的卡"
    answers = iter(["r", "多写荒草", ""])
    card = review_style_card("草稿", llm=Fake(), input_fn=lambda _: next(answers))
    assert card == "改后的卡"
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_style.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- 统计：CJK 字频；行长分布；诗、词的韵脚都用 `xinyun.resolve_rhyme` 归部；2-gram 频次（去停用词表：的、了、不、人、一、是、在、有、我、他、这、那、中、上、下、来、去、时、日、天、云、山、水 等只作过滤，不删意象词）。
- `build_style_card` 输出 Markdown，固定小节：常用字、高频词组、意象域、句法偏好、情感基调、用韵习惯、忌用词、代表示例（默认全部 56 首；`example_count` 可限制）。
- 有 `llm` 时，把统计与全部作品（或限制后的示例）发给模型，要求"只输出风格卡正文，不评论"；模型失败则退回纯统计版。
- `review_style_card` 循环：打印草稿 → 回车接受 / `e` 调 `editor` / `r` 读修改意见让模型重写 / `q` 放弃。`editor` 默认写临时文件并调用 `notepad`。
- `style build` 写 `style/style-card.draft.md`；`style review` 确认后才写 `style/style-card.md`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_style.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/eh_poem_style/style.py style/style-card.md tests/test_style.py
git commit -m "feat: analyze corpus and build style card"
```

---

### Task 9: 模型适配、提示词与响应解析

**Files:**
- Create: `src/eh_poem_style/llm.py`
- Create: `src/eh_poem_style/prompt.py`
- Test: `tests/test_llm.py`
- Test: `tests/test_prompt.py`

**Interfaces:**
- Consumes: `ModelProfile`、`PoemDraft`、`LLMClient`（Task 1），`Poem`（Task 7），`Cipai`（Task 4）。
- Produces:
  - `OpenAICompatClient(profile: ModelProfile, transport: httpx.BaseTransport | None = None)`：POST `{base_url}/chat/completions`，Bearer key；非 2xx 抛 `LLMError`。`transport` 仅用于测试。
  - `DraftParseError(message: str)`。
  - `parse_draft(text: str) -> PoemDraft`：支持纯 JSON、```json 围栏、前后夹话。
  - `PromptContext(style_card: str, examples: Sequence[Poem], spec: ShiSpec | None, cipai: Cipai | None, rhyme_groups: Sequence[str], candidate_chars: Sequence[str])` — frozen dataclass。
  - `build_messages(request: GenerateRequest, ctx: PromptContext) -> list[dict]`。

- [ ] **Step 1: 写失败测试（解析）**

```python
import pytest
from eh_poem_style.prompt import DraftParseError, parse_draft

def test_parse_code_fence():
    text = '好的，结果如下：\n```json\n{"title":"t","genre":"七绝","cipai":null,"lines":["a","b"],"rhyme":["b"]}\n```\n'
    d = parse_draft(text)
    assert d.lines == ["a", "b"]

def test_parse_missing_field_raises():
    with pytest.raises(DraftParseError):
        parse_draft('{"title":"t"}')
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_prompt.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现解析**

- 先尝试 `json.loads(text)`。
- 失败则提取第一个 ```` ```json ```` 到最后一个 ```` ``` ````；再失败则取第一个 `{` 到最后一个 `}`。
- 校验字段：`title` 字符串、`genre` 字符串、`lines` 非空字符串列表；`cipai` 可为 `null`；`rhyme` 默认空列表。
- 所有失败抛 `DraftParseError`，消息包含"未找到 JSON 对象"或缺失字段名。

- [ ] **Step 4: 写失败测试（HTTP 与提示词）**

```python
import httpx
from eh_poem_style.config import ModelProfile
from eh_poem_style.llm import OpenAICompatClient

def test_client_posts_chat_completions(monkeypatch):
    seen = {}
    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})
    transport = httpx.MockTransport(handler)
    client = OpenAICompatClient(ModelProfile("x", "https://api.example/v1", "k", "m"), transport=transport)
    assert client.complete([{"role": "user", "content": "hi"}]) == "ok"
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer k"
```

- [ ] **Step 5: 实现 LLM 客户端与提示词**

- `OpenAICompatClient.__init__(profile, transport=None)`；用 `httpx.Client(transport=transport, timeout=profile.timeout)`。
- `complete` 返回 `data["choices"][0]["message"]["content"]`；缺失抛 `LLMError`。
- `build_messages` 系统提示词固定包含：角色（中文诗词助手）、必须输出 JSON、字段 schema、不得解释、韵脚必须在给定候选内、词必须逐字合谱。
- 用户消息包含：白话内容、体裁、词牌与谱（若词）、韵部与候选韵字、风格卡、全部作品（或 `--max-examples` 限制后的示例）。
- 提示词中明确：诗不要求平仄；词必须严格。

- [ ] **Step 6: 运行测试，确认通过**

Run: `python -m pytest tests/test_llm.py tests/test_prompt.py -v`

Expected: PASS。

- [ ] **Step 7: 提交**

```powershell
git add src/eh_poem_style/llm.py src/eh_poem_style/prompt.py tests/test_llm.py tests/test_prompt.py
git commit -m "feat: add OpenAI-compatible client and prompt builder"
```

---

### Task 10: 生成循环与运行落盘

**Files:**
- Create: `src/eh_poem_style/generate.py`
- Test: `tests/test_generate.py`

**Interfaces:**
- Consumes: `GenerateRequest`（Task 1），`PoemDraft`/`Report`（Task 1），Tasks 2–9。
- Produces:
  - `GenerationResult(draft, report, attempts, run_dir)` — dataclass。
  - `check_copy(lines: Sequence[str], seed_lines: Sequence[str]) -> tuple[Issue, ...]`：整句与种子完全相同 → `copy_line` 错误。
  - `Constraints(shi_spec: ShiSpec | None, rhyme_groups: tuple[str, ...], candidate_chars: tuple[str, ...])` — frozen dataclass。
  - `prepare_constraints(request, cipai, stats, chars) -> Constraints`：诗构造 `ShiSpec` 并选定一个韵部；词按每个韵位选定韵部。
  - `generate(request, client, style_card, examples, cipai, stats, runs_dir=Path("runs")) -> GenerationResult`。

- [ ] **Step 1: 写失败测试（重试）**

```python
from eh_poem_style.generate import GenerateRequest, generate

class FakeLLM:
    def __init__(self, replies): self.replies = list(replies); self.calls = []
    def complete(self, messages, **opts):
        self.calls.append(messages)
        return self.replies.pop(0)

def test_retries_with_error_feedback(tmp_path):
    bad = '{"title":"t","genre":"七绝","cipai":null,"lines":["a","b","c","d"],"rhyme":[]}'
    good = '{"title":"t","genre":"五绝","cipai":null,"lines":["白日依山尽","黄河入海流","欲穷千里目","更上一层楼"],"rhyme":[]}'
    fake = FakeLLM([bad, good])
    req = GenerateRequest(prompt="写一首", genre="五绝", line_length=5, first_rhyme=False)
    result = generate(req, fake, "", [], None, None, runs_dir=tmp_path)
    assert result.attempts == 2
    assert result.report.ok
    assert "校验未通过" in fake.calls[1][-1]["content"]

def test_rejects_exact_copied_line(tmp_path):
    copied = '{"title":"t","genre":"七绝","cipai":null,"lines":["荒草高天斜风吹","一行白鹭上青天","窗含西岭千秋雪","门泊东吴万里船"],"rhyme":[]}'
    good = '{"title":"t","genre":"七绝","cipai":null,"lines":["两个黄鹂鸣翠柳","一行白鹭上青天","窗含西岭千秋雪","门泊东吴万里船"],"rhyme":[]}'
    fake = FakeLLM([copied, good])
    examples = [Poem("seed", ("荒草高天斜风吹",), "诗", None, "")]
    req = GenerateRequest(prompt="写一首", genre="七绝", first_rhyme=False)
    result = generate(req, fake, "", examples, None, None, runs_dir=tmp_path)
    assert result.attempts == 2
    assert result.report.ok
    assert "校验未通过" in fake.calls[1][-1]["content"]
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_generate.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现**

- 每次尝试：`parse_draft` → `validate_shi` 或 `validate_ci` → `check_copy`（与 `examples` 的整句比对）；解析失败也转成 `Report` 的 `parse_error` issue。
- 失败且未达上限：向 `messages` 追加 assistant 原文与 user 消息："上一版校验未通过，错误如下：… 只改错处，保留已合规部分，仍只输出 JSON。"
- 每次尝试写 `runs/<YYYYMMDD-HHMMSS>-<slug>/attempt-N.txt` 与 `attempt-N.json`；最终写 `request.json`、`report.md`、`draft.md`。
- `prepare_constraints`：`stats` 可为 `None`（测试/首次运行）。诗按 `stats.shi_rhyme_groups` 选韵部，无偏好时默认第十部（唐）；词按 `cipai` 每个韵位的 `rhyme_tone` 从 `stats.ci_rhyme_groups` 选部，无偏好时用默认（平→第十部，仄→第三部）。候选字用 `xinyun.candidates`，字集来自 `examples` 与种子语料；诗、词共用同一套新韵。
- 同一首内换韵：相邻同音调韵位尽量同部；`rhyme_tone` 变化时换部。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_generate.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/eh_poem_style/generate.py tests/test_generate.py
git commit -m "feat: generate with validation retry and run persistence"
```

---

### Task 11: 定稿、diff 与人工修改留痕

**Files:**
- Modify: `src/eh_poem_style/corpus.py`
- Test: `tests/test_corpus.py`

**Interfaces:**
- Consumes: `runs/<id>/draft.md`、`PoemDraft`。
- Produces:
  - `accept_run(run_id: str, edited_path: Path | None = None, runs_dir=Path("runs"), poems_dir=Path("corpus/poems")) -> Path`。
  - 返回值：写入的定稿路径。
  - 定稿 Markdown 含 YAML frontmatter：`title`、`date`、`genre`、`cipai`、`status: final`、`source: generated`。

- [ ] **Step 1: 写失败测试**

```python
def test_accept_writes_diff(tmp_path):
    run = tmp_path / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "draft.md").write_text("白日依山尽\n黄河入海流\n", encoding="utf-8")
    edited = tmp_path / "edited.md"
    edited.write_text("白日依山尽\n黄河入海流\n更上一层楼\n", encoding="utf-8")
    out = accept_run("r1", edited, runs_dir=tmp_path / "runs", poems_dir=tmp_path / "poems")
    text = out.read_text(encoding="utf-8")
    assert "status: final" in text
    assert "更上一层楼" in text
    assert "---" in text  # diff 分隔
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_corpus.py::test_accept_writes_diff -v`

Expected: FAIL，函数不存在。

- [ ] **Step 3: 实现**

- 用 `difflib.unified_diff` 生成原文→改后文 diff。
- 定稿正文写改后文；frontmatter 后附 `## 修改记录` 与 fenced diff。
- 无 `edited_path` 时只保存 draft，diff 为空。
- 文件名：`<date>-<slug>.md`；slug 取标题的 CJK/拉丁字母，空格转 `-`。

- [ ] **Step 4: 运行测试，确认通过**

Run: `python -m pytest tests/test_corpus.py -v`

Expected: PASS。

- [ ] **Step 5: 提交**

```powershell
git add src/eh_poem_style/corpus.py tests/test_corpus.py
git commit -m "feat: accept edited drafts and store diffs"
```

---

### Task 12: 对比命令、剩余词牌与 CLI 串联

**Files:**
- Create: `src/eh_poem_style/compare.py`
- Create: `data/cipai/nanxiangzi-27.yaml`
- Create: `data/cipai/yiwangsun.yaml`
- Create: `data/cipai/yugezi.yaml`
- Create: `data/cipai/yiqine.yaml`
- Modify: `src/eh_poem_style/cli.py`
- Test: `tests/test_compare.py`
- Test: `tests/test_cli.py`

**Interfaces:**
- Produces:
  - `compare(request, clients: dict[str, LLMClient], style_card, examples, cipai, stats, runs_dir=Path("runs")) -> Path`：返回 `compare.md` 路径。
  - CLI：`generate`、`compare`、`validate`、`style build`、`import-seed`、`cipai add`、`accept` 全部接通。

- [ ] **Step 1: 写失败测试（对比）**

```python
class FakeLLM:
    def __init__(self, text): self.text = text
    def complete(self, messages, **opts): return self.text

def test_compare_writes_two_sections(tmp_path):
    good = '{"title":"t","genre":"五绝","cipai":null,"lines":["白日依山尽","黄河入海流","欲穷千里目","更上一层楼"],"rhyme":[]}'
    req = GenerateRequest(prompt="写一首", genre="五绝", line_length=5, first_rhyme=False)
    out = compare(req, {"deepseek": FakeLLM(good), "local": FakeLLM(good)}, "", [], None, None, runs_dir=tmp_path)
    text = out.read_text(encoding="utf-8")
    assert "deepseek" in text and "local" in text
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `python -m pytest tests/test_compare.py -v`

Expected: FAIL，模块不存在。

- [ ] **Step 3: 实现 compare**

- 对每个 profile 调用 `generate`，记录结果/报告/尝试次数。
- 写 `compare.md`：每个 profile 一节，含诗歌正文、校验报告、耗时。
- 某个 profile 失败不中断其它 profile；在对应节写错误。

- [ ] **Step 4: 补剩余四个词牌 YAML**

`nanxiangzi-27.yaml`：

```yaml
name: 南乡子
variant: 单调二十七字
sections:
  - lines:
      - {pattern: "中仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中平中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄中平平仄仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中仄中平平仄仄", rhyme: true, rhyme_tone: 仄}
```

`yiwangsun.yaml`：

```yaml
name: 忆王孙
variant: 正体
sections:
  - lines:
      - {pattern: "中平中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄平平中仄平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄平平中仄平", rhyme: true, rhyme_tone: 平}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中仄平平中仄平", rhyme: true, rhyme_tone: 平}
```

`yugezi.yaml`：

```yaml
name: 渔歌子
variant: 正体
sections:
  - lines:
      - {pattern: "中仄平平仄仄平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中平中仄仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中中仄", rhyme: false}
      - {pattern: "仄平平", rhyme: true, rhyme_tone: 平}
      - {pattern: "中平中仄仄平平", rhyme: true, rhyme_tone: 平}
```

`yiqine.yaml`：

```yaml
name: 忆秦娥
variant: 正体
sections:
  - lines:
      - {pattern: "平中仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平中仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平中仄", rhyme: false}
      - {pattern: "仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平中仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平中仄平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "平平仄", rhyme: true, rhyme_tone: 仄}
      - {pattern: "中平中仄", rhyme: false}
      - {pattern: "仄平平仄", rhyme: true, rhyme_tone: 仄}
```

- [ ] **Step 5: 接通 CLI**

- `generate`：读配置、加载风格卡与种子、加载词牌、构建 client、调用 `generate`、打印诗与报告。
- `compare`：`--profiles deepseek,local`。
- `validate`：从文件读 `PoemDraft`（简单 JSON 或 `---` frontmatter），调用校验器。
- `style build`：`analyze_corpus` + `build_style_card` + 写 `style/style-card.draft.md`；`style review`：`review_style_card` 确认后写 `style/style-card.md`。
- `cipai add NAME --file PATH [--rhyme-tone 平|仄]`：`parse_spectrum` 后写 `data/cipai/<name>.yaml`。若某些 `（韵）` 行没有平仄标记，用 `--rhyme-tone` 补齐；仍无法判断则报错，不猜。
- `accept RUN_ID [--file PATH]`。

- [ ] **Step 6: 写 CLI 端到端测试（假模型）**

在 `cli.py` 暴露 `build_client(profile_name: str, config: Config) -> LLMClient`，测试里 monkeypatch 它返回 `FakeLLM`。测试目标：`main(["generate", "--genre", "五绝", "--prompt", "写一首", "--profile", "fake"])` 返回 `0`，输出含"白日依山尽"。

- [ ] **Step 7: 运行测试，确认通过**

Run: `python -m pytest tests/test_compare.py tests/test_cli.py -v`

Expected: PASS。

- [ ] **Step 8: 提交**

```powershell
git add src/eh_poem_style/compare.py src/eh_poem_style/cli.py data/cipai tests
git commit -m "feat: compare profiles and wire CLI"
```

---

### Task 13: 真实语料与双模型验收

**Files:**
- Create: `docs/acceptance.md`
- Modify: `style/style-card.md`（用真实语料重新生成）

**Interfaces:**
- 无新代码接口；验证 Task 1–12 的端到端行为。

- [ ] **Step 1: 生成真实风格卡**

```powershell
python -m eh_poem_style style build --profile deepseek
python -m eh_poem_style style review
```

在 `style review` 里检查草稿：是否覆盖常用字、意象、句法、情感、用韵、忌用、全部 56 首示例；可直接编辑，或多轮输入意见让模型改；确认后才写 `style/style-card.md`。

- [ ] **Step 2: 用真实模型生成三组**

```powershell
python -m eh_poem_style generate --genre 七绝 --prompt "写一次夜游多瑙河，灯影与静水" --profile deepseek
python -m eh_poem_style generate --genre 词 --cipai 如梦令 --prompt "写清晨林间忽然惊起的鸟" --profile deepseek
python -m eh_poem_style compare --genre 词 --cipai 相见欢 --prompt "写一只猫半夜跳上床" --profiles deepseek,local
```

验收口径：

- 诗：≤3 次内通过押韵与句数/字数；人工读起来像用户（用词、意象、句法）。
- 词：≤3 次内通过词牌谱与中华新韵；报告无 `unknown_char`，若有则说明数据缺口。
- `compare.md` 同时含两个 profile 的正文与报告。
- 稳定性：同一请求重复 5 次，至少 3 次通过硬校验且人工判断"像用户"。

可选加分项：`compare` 已能生成两版，可加 `--blind` 隐藏 profile 名做盲评；v1 不强制。

- [ ] **Step 3: 新增一个词牌（≤5 分钟）**

让用户粘贴一个未预置的词牌（如《少年游》或《祝英台近》）的"词牌名 + 平仄谱"：

```powershell
python -m eh_poem_style cipai add 少年游 --file D:\Desktop\shaonianyou.txt
python -m eh_poem_style generate --genre 词 --cipai 少年游 --prompt "..." --profile deepseek
```

Expected：从粘贴到生成不超过 5 分钟，无需改代码。

- [ ] **Step 4: 记录结果**

在 `docs/acceptance.md` 记录：日期、使用的模型名、三组请求、尝试次数、校验报告摘要、人工判断（像/不像）、发现的数据缺口。不要粘贴 API Key。

- [ ] **Step 5: 提交**

```powershell
git add docs/acceptance.md style/style-card.md
git commit -m "docs: record acceptance runs with DeepSeek and local models"
```

---

## 自检

- **Spec coverage:** 诗押韵/句数、词严格（新韵 + 现代平仄）、全部 56 首示例与整句查重、风格卡人工审查/多轮修改、语料沉淀、模型可替换与对比、词牌扩展、报告、人工修改留痕均有对应任务。
- **Step scan:** 每个代码步骤给签名/文件/关键值；测试步骤给断言；没有 "handle edge cases" 这类空话。
- **Type consistency:** `PoemDraft`、`Report`、`Cipai`、`tone_of_line`、`ShiSpec`、`GenerateRequest` 在任务间保持一致。
- **Review Focus:** 标点/围栏（Task 5/6/9）、多音字（Task 2/5/6）、非 JSON（Task 9/10）、词谱混写（Task 4）、未知字（Task 3/6）。
- **Proportion:** 计划约为规格的 2 倍，数据文件按原文给全，代码只给签名与算法要点。
