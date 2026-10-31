---
name: zhongkou-evidence
description: Run the deterministic review-analysis engine and produce an evidence-linked consumer experience diagnosis. Use when analysing customer reviews, checking whether a marketing claim is supported, or writing review-grounded copy.
---

# 众口 · 证据引擎

这个技能只有一个作用：把评论文本变成**可复算**的统计，让后续每一句解释都有出处。

本文件与仓库同级目录对应。若按 `docs/搭建手册.md` 装成专家技能，把 `engine/` 改为 `scripts/`、`kb/` 改为 `references/`，其余不变。

## 目录

```
engine/zhongkou/       引擎源码（纯标准库，无第三方依赖）
engine/tests/          34 条单测
data/asap_test.csv     公开测试集 4,940 条（带人工标注，用于核验引擎）
kb/                    四份口径原文：维度定义、报告模板、禁用词、文案规则
```

## 三条命令

进入 `engine/` 后：

```bash
# 1. 18 维短板（含星级掩盖比例、重复文案簇）
python -m zhongkou diagnose --split test --top 8

# 2. 卖点取证（给一句想对外说的话）
python -m zhongkou claim "环境安静，适合聊天"

# 3. 取证据原话（按维度列出评论编号与原文片段）
python -m zhongkou quote --dim "Ambience#Noise" --limit 3
```

用户自带数据时加 `--csv`：列名包含 `评论/内容/review` 之一，以及 `星级/评分/star` 之一即可。

```bash
python -m zhongkou diagnose --csv /path/to/reviews.csv --top 8
```

## 输出怎么用

| 引擎字段 | 含义 | 写进结论时的说法 |
|---|---|---|
| `每百条抱怨` | 每 100 条评论里有几条抱怨这一维 | "每 100 位顾客有 14 位在抱怨价位" |
| `负向率` | 提及该维的评论里，负向占比 | "提到等位的人里，六成是在抱怨" |
| `提及` | 该维被明确提到的条数 | 少于 30 条不要单独下结论 |
| `星级掩盖` | 4–5 星评论中含明确负向维度的比例 | "只看星级会漏掉这部分" |
| `置信度` | 2 高 / 1 中 / 0 低 | 0 不作结论，1 要标"方向待核" |

## 引擎的边界（必须如实转述）

- 极性判断在公开测试集上的准确率是 **72.9%**，不是 100%。所以它用来**复核模型判断**，不单独当裁判。
- 维度识别 F1 **0.725**，会漏判。漏判的维度写"未形成判定"，不要补。
- 硬规则部分（禁用词、重复簇、计数、阈值比较）是确定的，可以放心引用。

## 自检

```bash
python -m unittest discover -s tests      # 34 条用例
python -m zhongkou audit --split test     # 与人工标注比对
```
