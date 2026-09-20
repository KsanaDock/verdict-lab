# VerdictLab · 判据实验室

输入内容与可配置判断项，比较不同模型如何选择、表达不确定性，以及支撑后续审核服务。

**状态：M1 已完成三个数据集的全量评测。** 当前代码可读取 COLDataset、ChineseHarm-Bench 与 NVIDIA Aegis 2.0，向 OpenRouter Jev 和 DeepSeek 官网 Flash 发起同例对比，并保存原始响应、token、缓存命中、延迟和成本。公网看板仅发布聚合指标，原始数据集、待审核文本与运行目录不会上传。

## 为什么做

内容审核不止输出“通过 / 不通过”。一次审核需要识别多个风险、考虑语境与例外、关联具体规则，并将结果交给解释、复核、申诉等后续环节。模型应当输出可供其他 Agent 消费的判断记录。

VerdictLab 比较三类路线，不预设 Jev 胜出：

| 路线 | 首批候选 | 核心问题 |
| --- | --- | --- |
| 快速决策模型 | OpenRouter 的 `typesafe/jev-1.13` | 多项判断与原生选项概率，能否改善效率及复核分流？ |
| 专用审核模型 | Qwen3Guard-Gen-4B；Llama Guard 4 12B | 专项训练的质量、价格及规则适应能力如何？ |
| 低价通用语言模型 | DeepSeek 官网 `deepseek-flash` | 短结构化输出是否已经足够好、足够便宜？ |

候选均需在实施阶段验证权限、接口与实际可用性；模型已上架不等于本项目已成功调用。型号、价格、限制和来源见 [模型与资料](docs/MODELS-AND-SOURCES.md)。

## 要回答的问题

1. 对同一内容、语境、规则和判断项，谁选得更准确？哪些类别会失效？
2. 在相同漏审 / 误杀约束下，谁能自动处理更多内容、少交人工？
3. 同时判断 1、5、20 个项目时，延迟和每条成本怎样变化？
4. 原生概率、标签分数、模型自报概率，实际校准质量有多大差别？
5. 加入证据、解释、复核、申诉后，完整服务是否仍有成本优势？
6. 改规则、换中文表达、加入上下文后，模型是否仍然可靠？

## 最小产品形态

一个可重复的横向对比工作台：

- **输入：** 待审核内容、关联上下文、适用规则版本、多个判断项及其候选选项。
- **运行：** 同一测试实例交给三类模型，保存原始响应和标准化结果。
- **输出：** 各判断项选中的选项、可用的选项分布、概率来源、耗时、用量与成本。
- **比较：** 并列看分歧、错误、能力不支持项；批量评测质量、速度、成本。
- **后续编排：** 标准化结果交给策略、解释、复核和申诉 Agent；每一步独立记录。

首期仅做文本，包括中文简体、繁体及英文对照。视觉、音频、视频另设赛道，不把 OCR 或语音识别费用隐藏在模型成本外。

## 判断结果、理由与概率

判断项应当细分到足以支持下一步处理。例如“外链用途”可选择普通引用、交易信息、站外引流、信息不足，而非只有“有外链 / 无外链”。并非每个选项都意味着违规。

**选项概率表达模型在候选解释之间的判断，不等于事实证明，也不是模型内部思考过程。** 不同风险可同时成立，不能把所有风险强行塞进一个总和为 100% 的分布。

创作者反馈可以展示适用规则、触发片段、选中的理由项和分项分布；解释 Agent 根据这些已验证材料写清楚缘由。没有证据或概率时明确显示缺失，不补造、不把缺失填成 0%。设计详见 [判断契约](docs/JUDGMENT-CONTRACT.md) 和 [项目方案](docs/PLAN.md)。

## 怎样判断有竞争力

不以一个总准确率或单次调用价格排名。先规定漏审、误杀和响应时间约束，再比较：

- 每千条 / 每百万条内容的模型费用及完整服务成本；
- 自动处理覆盖率、人工复核率、错误放行率、错误拦截率；
- p50 / p95 / p99 完整结果延迟、稳定吞吐及失败率；
- 规则变化、语境变化和陌生内容下的质量；
- 面向创作者的解释是否有据、是否清晰、能否有效申诉。

“Jev 更快”“概率有用”“私有部署更便宜”都是待验证假设。若低价 LLM 或专用审核模型已满足目标，应保留它们作为核心，或采用混合路由。

## 文档导航

| 文档 | 内容 |
| --- | --- |
| [项目方案](docs/PLAN.md) | 目标、服务边界、Agent 分工、工作台与阶段计划 |
| [判断契约](docs/JUDGMENT-CONTRACT.md) | 输入输出约定、判断项设计、概率语义、完整示例 |
| [评测方案](docs/BENCHMARK.md) | 公平对比、数据集、质量与成本指标、实验登记 |
| [模型与资料](docs/MODELS-AND-SOURCES.md) | 候选版本、核查快照、价格、接口风险、资料来源 |
| [M1 实现说明](docs/M1-IMPLEMENTATION.md) | 当前适配器、数据映射、运行方法与成本口径 |

## 数据集与来源

| 数据集 | 本项目评测范围 | 官方来源 |
| --- | ---: | --- |
| ChineseHarm-Bench | benchmark 全量 6,000 条 | [GitHub：zjunlp/ChineseHarm-bench](https://github.com/zjunlp/ChineseHarm-bench) |
| COLDataset | test 全量 5,323 条 | [GitHub：thu-coai/COLDataset](https://github.com/thu-coai/COLDataset) |
| Aegis AI Content Safety Dataset 2.0 | test 中 1,928 条可评测记录 | [Hugging Face：nvidia/Aegis-AI-Content-Safety-Dataset-2.0](https://huggingface.co/datasets/nvidia/Aegis-AI-Content-Safety-Dataset-2.0) |

数据集文件保存在 Git 忽略的 `data/private/`，运行结果保存在 Git 忽略的 `runs/`。请分别遵守各数据集来源页面所列的许可证和使用条件。

## 当前运行方法

代码要求 Python 3.11 或以上。先安装本地包：

```powershell
python -m pip install -e .
```

不调用模型即可检查本地 COLDataset 的转换结果：

```powershell
verdict-lab inspect --dataset cold --path COLDataset/COLDataset/test.csv --limit 3
```

设置 `OPENROUTER_API_KEY` 和 `DEEPSEEK_API_KEY` 后，可在小样本上同时运行两条路线：

```powershell
verdict-lab compare --dataset cold --path COLDataset/COLDataset/test.csv --limit 10
```

英文 Aegis 2.0 默认使用独立的官方分类方向配置。先跑 10 条：

```powershell
verdict-lab compare --dataset aegis --path data/private/Aegis-AI-Content-Safety-Dataset-2.0/test.json --limit 10
```

确认接口与预算后，必须显式使用 `--all` 才会运行全部可评测样本：

```powershell
verdict-lab compare --dataset aegis --path data/private/Aegis-AI-Content-Safety-Dataset-2.0/test.json --all
```

运行时控制台会实时显示总体进度、每次调用的模型、状态、延迟、费用和命中的方向。运行产物写入被 Git 忽略的 `runs/<run_id>/`：`results.jsonl` 是标准化逐请求记录，`summary.json` 汇总双方调用数、失败数、token、缓存命中、延迟与总成本，`raw/` 保留供应商原始响应，`errors.log` 专门记录错误与暂停原因。

如果进程中断、机器重启或某个供应商余额不足，直接恢复原 run：

```powershell
verdict-lab compare --resume runs/<run_id>
```

恢复时使用 run 内冻结的样本、分类定义和价格快照；已经成功的“样本 × 模型”会跳过，只运行失败或缺失项。鉴权、余额和限流错误会在控制台明确通知、写入 `errors.log`，并暂停对应供应商，另一家仍可继续完成。

在 Windows 上，如果编辑器、预览器或同步软件短暂锁住 `summary.json`，程序会重试并降级写入；汇总文件暂时无法更新时也不会中断 API 测试。逐请求结果仍以已即时刷盘的 `results.jsonl` 为准，锁文件警告会写入 `errors.log`。

Jev 与 DeepSeek 的小样本接口已验证；正式评测仍应逐步扩大样本，并持续核对原始响应和供应商控制台账单。
