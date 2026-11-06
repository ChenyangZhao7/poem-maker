# EH-Poem-Style

用你自己写的 56 首作品做风格样本，生成古体诗、律诗、绝句与词。

- 诗：中华新韵，只校验押韵与句数/字数，不查平仄。
- 词：按词牌谱严格校验平仄、句读、韵位与韵部（中华新韵）。
- 模型可替换：DeepSeek V4.1 与本地 Ollama（默认 `qwen3.5:4b`）可同题对比。
- 所有生成、重试、人工修改都会落盘，语料持续增长。

## 快速开始

```powershell
python -m pip install -e ".[dev]"
Copy-Item config.example.toml config.toml
$env:DEEPSEEK_API_KEY = "你的 key"
python -m pytest -q
python -m eh_poem_style --help
```

设计与计划：

- 设计：`docs/superpowers/specs/2026-11-06-eh-poem-style-design.md`
- 计划：`docs/superpowers/plans/2026-11-06-eh-poem-style.md`

`demo.py` 是早期竖切演示，正式功能以 `eh_poem_style` 包为准。
