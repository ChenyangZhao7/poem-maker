# 验收记录

日期：2026-11-06

模型：

- DeepSeek V4.1 Flash（`deepseek-flash`，OpenAI 兼容接口）
- 本地 `qwen3.5:4b`（Ollama 原生 `/api/chat`，`think=false` + JSON schema）

## 风格卡

- `style build --profile deepseek` 生成 `style/style-card.draft.md`。
- 人工审查：把“韵部宜宽，允许邻韵通押与疏韵”改为“诗可从宽；词必须按词牌谱一韵到底”，避免与词的严格校验冲突。
- `style review` 确认后写入 `style/style-card.md`；生成只读正式卡。

## 七绝：夜游多瑙河

DeepSeek（1 次通过）：

> 灯影斜铺水底天
> 满城灯火入空明
> 不知两岸千年事
> 静水无声波自平

本地 `qwen3.5:4b`（1 次通过）：

> 蓝釉街灯影万重
> 静水无声接晚风
> 不知此去何方去
> 且听流波万古同

说明：本地首次用 OpenAI 兼容 `/v1` 时，思考过程耗尽输出预算，`content` 为空。改为 Ollama 原生 `/api/chat`、`think=false`、JSON schema 后正常。

## 词对比：相见欢·夜猫

DeepSeek（2 次通过）：

> 三更黑影来西
> 跃床低
> 猫影轻巡床尾复窥衣
> 忽惊起
> 眸难闭
> 问何期
> 夜半猫巡床尾又闻啼

本地 `qwen3.5:4b`（3 次仍未通过）：

> 忽有跃上床
> 尾尖轻触席
> 幽微耳畔听细泣
> 惊起
> 翻寻觅
> 怕被主人嗔弃迹
> 独守空房伴寂寥

错误摘要：句长多处不合（应为 6/3/9/3/3/3/9），韵部与平仄也不合。
这是预期结果：4B 模型在长词牌谱下仍不稳定，严格校验把它挡住了。

## 新增词牌：浣溪沙

- 用 `cipai add 浣溪沙 --file ... --rhyme-tone 平` 从文本谱新增，生成 `data/cipai/huan-xi-sha.yaml`。
- 从粘贴到生成完成约 1 分钟，无需改代码。
- `generate --genre 词 --cipai 浣溪沙 --profile deepseek`（2 次通过）：

> 雾散江天未见曦
> 江桥人语破晨稀
> 长风推浪作低啼
> 古渡石阶随浪去
> 不知何处问归期
> 几回潮水向人低

## 结论

- 诗：两套模型都能在 1 次内通过“押韵 + 句数/字数”；本地 4B 可用，但需要原生 Ollama 参数。
- 词：DeepSeek 能在 ≤3 次内通过严格词牌校验；本地 4B 目前不能，校验器能明确报错。
- 新增词牌流程可用，满足 ≤5 分钟目标。
- 本轮未出现 `unknown_char`；数据缺口暂未暴露。
