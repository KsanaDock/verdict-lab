# 模型候选与资料核查

核查日期：2026-09-20（Asia/Taipei）。本页记录公开资料和一次无需认证的模型目录查询；未调用任何模型推理，没有质量或时延实测。

## 1. 候选与接入决策

| 候选 | 角色 | 计划接入 | 当前证据与限制 |
| --- | --- | --- | --- |
| `typesafe/jev-1.13` | A 组主候选 | OpenRouter 的 Decisions 能力 | 模型页面和官方 Lab 示例已查到；账户权限、返回分布及用量待实测 |
| `Qwen/Qwen3Guard-Gen-4B` | B 组中文审核候选 | 先考虑自部署 | 官方模型卡提供部署方式；默认输出安全等级和类别，不能假定支持任意自定义判断 |
| `meta-llama/llama-guard-4-12b` | B 组另一专用审核基线 | OpenRouter | 模型目录中可见；概率字段、自定义规则和中文表现待实测 |
| `deepseek/deepseek-v4-flash-0731` | C 组低价 LLM 主候选 | OpenRouter | 有日期版本；需冻结 provider，验证短结构化输出和推理设置 |
| `deepseek/deepseek-v4-flash` | C 组成本候选 | OpenRouter | 目录显示名称为 V4 Flash 0423，核查时输入 / 输出报价略低于 0731 |
| `deepseek/deepseek-v3.2` | C 组可选历史基线 | OpenRouter | 已查到，但当前报价高于上述 Flash，不称为最便宜 |
| `Qwen/Qwen3Guard-Stream-4B` | 流式专项 | 自部署，后续阶段 | 使用增量输入与分类头；单独评估检测延迟，不混入整条文本赛道 |

“业界常用”在本项目中落实为公开可获得、可复现的代表性专用审核基线，不声称已经验证市场占有率。首期至少覆盖 A / B / C 各一个可用版本，B 组逐步增加第二个基线。

## 2. OpenRouter Jev 已确认与未确认事项

OpenRouter 模型页列出的 ID 为 `typesafe/jev-1.13`，标价输入每百万 tokens $0.042、输出 $0、上下文 32K。正式实验不用 `~typesafe/jev-latest` 这样的滚动别名。[模型页面](https://openrouter.ai/typesafe/jev-1.13)

官方 Jev Lab 的编排示例调用 `openRouter.alpha.decisions.create`，传入 `model`、`state`、`questions`，并说明可返回选择和分布。实施时从最新官方 SDK / API 规范确认，不把普通 Chat Completions 兼容性自动延伸到 Jev 的所有字段。[官方 Lab 示例](https://openrouter.ai/labs/jev/compile)

2026-09-20 约 04:08 +08:00 查询 `GET https://openrouter.ai/api/v1/models` 时，返回目录中没有匹配 `jev` 或 `typesafe` 的条目，但模型页与 Lab 页面可读。此差异尚未解释，不能据此判断已下线，也不能声称已接通。M1 必须验证对应 Decisions 发现方式、账户权限和实际请求；若失败，明确报告 A 组未完成，不偷偷改成 TypeSafe 直连。直连可作为独立诊断轨道，单独标注。

M1 探测清单：

- 最小单选能否返回被选项、完整分布、错误状态与用量。
- 多判断项如何对应 ID，概率是否保持原生字段，供应商 confidence 是否保留。
- 真实请求窗口、判断项与选项限制、限流、超时及费用明细。
- 页面 ID、实际模型 revision 与实际供应商能否固定；不能固定时记录未知。
- 当前支持的计费数据是否足以区分报价估算与实际收费。

## 3. 价格快照

单位为 USD / 1,000,000 tokens；不是每百万条内容价格，也不是吞吐或延迟实测。API 目录按每 token 给价，本表乘以 1,000,000。

| 模型 | 输入 | 输出 | 来源 |
| --- | ---: | ---: | --- |
| Jev 1.13 | 0.042 | 0 | OpenRouter 模型页 |
| DeepSeek V4 Flash 0731 | 0.04000 | 0.08000 | 模型目录与模型页 |
| DeepSeek V4 Flash（0423） | 0.03976 | 0.07952 | 模型目录 |
| DeepSeek V3.2 | 0.26900 | 0.40000 | 模型目录 |
| Llama Guard 4 12B | 0.18000 | 0.18000 | 模型目录 |
| Qwen3Guard 自部署 | 待测 | 待测 | 不按 API token 报价或零成本计算 |

目录报价可能反映不同供应商的低价路由，并受促销、缓存、时间和端点变化影响；实际支持结构化输出、概率或推理开关的供应商不一定有该报价。页面汇总价格和动态别名价格也可能不同。开跑前冻结实际端点及价格条件，以账单校验。

低价组的筛选原则：先过滤目标语言、上下文、输出能力和付费稳定端点，再按代表性样本的输入、输出、推理、重试总费用排序；选候选后再测质量。不能只按输入单价选“最便宜”。

## 4. 概率与能力的核查结论

- TypeSafe 文档区分概率分布与从分布计算的 confidence；这不是内部理由或正确性保证。[官方 confidence 文档](https://docs.typesafe.ai/confidence)
- Jev 当前以文本为输入，官方说明英语表现最佳；对抗内容和复杂间接判断是已知弱点。中文审核与提示干扰需要专项验证。[模型说明](https://docs.typesafe.ai/models)、[局限列表](https://docs.typesafe.ai/model-jaggedness/jev-1.13)
- Qwen3Guard 的 Gen 和 Stream 是不同模型形态；不能把 Stream 的流式能力直接归到 Gen。默认安全类别与客户社区规则的差别需要显式映射。[Gen 模型卡](https://huggingface.co/Qwen/Qwen3Guard-Gen-4B)、[Stream 模型卡](https://huggingface.co/Qwen/Qwen3Guard-Stream-4B)
- Llama Guard 4 是可比较的专用审核候选；首期只走文本，不能用它额外支持的输入能力替代三方的共同测试条件。[官方模型卡](https://huggingface.co/meta-llama/Llama-Guard-4-12B)
- OpenRouter 的参数支持列表只能用于能力探测，不能保证某 provider 返回完整标签分布。缺字段必须保留缺失。

不根据模型名称推断“原生校准”，不把 token 概率当成整条审核的正确率。具体协议见 [判断契约](JUDGMENT-CONTRACT.md)。

## 5. 资料索引

以下均为产品方、模型作者或官方托管平台的一手页面。引用表示查阅了资料，不表示已经实测、采用或确认质量优势。

| 资料 | 用途 |
| --- | --- |
| [OpenRouter Jev 1.13](https://openrouter.ai/typesafe/jev-1.13) | Jev 的平台型号与价格 |
| [OpenRouter Jev Lab](https://openrouter.ai/labs/jev/compile) | Decisions SDK 请求与结构化输出示例 |
| [OpenRouter 公共模型目录](https://openrouter.ai/api/v1/models) | 无认证目录与报价查询；本次字段摘录见上表 |
| [OpenRouter DeepSeek V4 Flash 0731](https://openrouter.ai/deepseek/deepseek-v4-flash-0731) | 低价组版本及供应商差异 |
| [OpenRouter DeepSeek V3.2](https://openrouter.ai/deepseek/deepseek-v3.2) | 可选旧版本基线 |
| [OpenRouter Llama Guard 4](https://openrouter.ai/meta-llama/llama-guard-4-12b) | 专用审核模型的 API 路线 |
| [TypeSafe 模型说明](https://docs.typesafe.ai/models) | 语言、输入及模型使用限制 |
| [TypeSafe 概率与置信度](https://docs.typesafe.ai/confidence) | 字段含义 |
| [TypeSafe 已知局限](https://docs.typesafe.ai/model-jaggedness/jev-1.13) | 边界测试设计 |
| [Qwen3Guard-Gen-4B](https://huggingface.co/Qwen/Qwen3Guard-Gen-4B) | 专用审核候选与标准输出 |
| [Qwen3Guard-Stream-4B](https://huggingface.co/Qwen/Qwen3Guard-Stream-4B) | 后续流式扩展 |
| [Llama Guard 4 官方模型卡](https://huggingface.co/meta-llama/Llama-Guard-4-12B) | 另一专用审核基线 |

## 6. 不确定项登记

| 项目 | 当前状态 | 下一步 |
| --- | --- | --- |
| OpenRouter Jev 原生分布 | 官方示例支持；未实调 | M1 记录真实响应 |
| Jev 目录缺项原因 | 未知 | 核对 Decisions 文档和账户可用性 |
| “最低价”模型 | 未做全目录、全费用筛选 | 用代表样本量与输出模式选型 |
| 中文与规则适应质量 | 无本项目测量 | 人工标注集评测 |
| 自部署硬件及成本 | 仅知道约 30 多张可能 80GB H100 | 实施时核实机器、卡型、互联和成本 |
| 解释是否改善体验 | 产品假设 | 盲评与用户理解测试 |

目前没有任何跑分、延迟或竞争力结论。评测必须允许结果证明无需采用 Jev。
