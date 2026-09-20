# M1：Jev 与 DeepSeek Flash 对比实现

版本：0.1 · 日期：2026-09-20 · 状态：离线测试通过，待小额真实调用

## 1. 本阶段固定范围

首轮只比较两条路径：

- OpenRouter Decisions API 的 `typesafe/jev-1.13`。
- DeepSeek 官方 API 的 `deepseek-flash`。

数据使用 COLDataset、ChineseHarm-Bench 和 NVIDIA Aegis AI Content Safety Dataset 2.0。原始数据放在被 Git 忽略的目录，不复制进源码或测试夹具。

## 2. 输出不是一个互斥总分类

站外引流、广告、黑产广告、色情、暴力、政治敏感风险、辱骂攻击、欺诈、赌博分别作为独立方向。一个内容可以同时命中多个方向，因此这些分数不要求、也不应该合计为 1。

Jev 对每个方向使用独立 `noul` 问题，保存原生 yes 概率。DeepSeek 返回同一组 0 到 1 的自报估计，`probability_source` 明确记为 `self_reported`，不能与 Jev 原生分布直接宣称等价。

“需要更多上下文”是独立的认识状态，不是违规类别。它可以与某些风险方向同时为高分，例如文本已明显广告推广，但是否获得授权仍缺材料。

分数在当前实现中表示“该方向在可见材料中成立的估计概率”，不是违规严重程度。若以后需要轻微、明显、严重，应增加单独的等级判断，不能复用概率字段。

## 3. 数据集真值边界

ChineseHarm-Bench 官方 `bench.json` 是六分类：博彩、低俗色情、谩骂引战、欺诈、黑产广告和不违规。加载器将前五类映射为对应的一对多二值真值，但不凭文本或类别名补造站外引流、一般广告、暴力或政治标签。

COLDataset 的训练集和开发集只有 offensive 二分类；测试集另有攻击个人、攻击群体、反偏见和其他非冒犯细标签。项目仅用它监督 `abuse_harassment` 方向，其他方向保持未标注。报告指标时，每个方向只在具有该方向真值的样本上计算。

Aegis 2.0 官方 test split 有 1,964 行，使用 CC-BY-4.0 许可。项目将每行的 user prompt 与可选 assistant response 保留为一个带角色的对话 case，并使用整体 safe/unsafe 与逗号分隔的多类别标签。官方将 36 条 Suicide Detection 来源 prompt 替换成 `REDACTED`，原文不随数据集分发；默认排除这些不可验证样本，因此全量可评测分母为 1,928。Aegis 使用独立的 `taxonomy-aegis.json`，包含 overall unsafe、12 个核心风险、9 个细风险、Needs Caution 与 Other，共 24 个独立方向。

这两套数据都不能验证全部产品方向。站外引流、一般广告、暴力、政治风险和上下文不足需要另建人工核验集；不得把“数据集没有该标签”当成负例。

新 run 默认只取 10 条，避免误触发大额调用。全量运行必须显式传入 `--all`；样本清单会在第一次请求前完整冻结到 `cases.jsonl`，随后按相同断点机制保存和恢复。

## 4. 请求与缓存

DeepSeek 的 system message 固定放在最前面，包含方向 ID 和判断标准；每条内容只改变后面的 user message，以便供应商尽可能命中相同前缀缓存。缓存由 DeepSeek 自动管理，不保证每次命中。

DeepSeek Flash 默认开启思考模式。T1 短结构化判断显式传入 `thinking: {"type": "disabled"}`，避免把隐藏推理 token 和时延混入最短判断赛道；若后续测试思考模式，必须作为单独配置和成本层报告。

每条结果保存：

- prompt、completion、cache-hit、cache-miss token；
- 请求完整结果延迟；
- 峰/谷价格带和按冻结快照计算的费用；
- 模型名、供应商、状态、选中方向和全部方向分数；
- 原始供应商响应引用。

OpenRouter Jev 优先读取响应中的实际 cost。DeepSeek 费用按请求开始时的 UTC 时段和响应 token 拆分计算。正式报告还应与两个供应商控制台账单核对。

## 5. 运行产物

`verdict-lab compare` 对每个 case 随机交错两家调用顺序，避免固定先后顺序与时段、缓存或服务负载绑定。默认只跑 10 条，必须显式增加 `--limit` 才会扩大花费。

每次运行生成：

- `manifest.json`：运行 ID、方向、阈值、供应商和随机种子；
- `cases.jsonl`：规范化输入与可用真值；
- `results.jsonl`：标准化结果及原始响应路径；
- `raw/*.json`：供应商原始响应；
- `summary.json`：请求成功率、token、缓存命中、延迟分位数和总费用。
- `errors.log`：只记录失败、无效输出、进程中断和供应商暂停原因，不写 API Key 或原始待审核文本。

控制台在启动时打印 run 目录、case 数、模型和总组合数；每次请求完成后打印 `完成数/总数`、case ID、模型、attempt、状态、延迟、费用和选中方向。余额或额度不足显示 `[VerdictLab][PAUSED]` 并给出准确的恢复命令；进程被 Ctrl+C 中断时显示 `[INTERRUPTED]`。

## 6. 断点恢复

每个“样本 × 模型”完成后，程序立即追加一行 `results.jsonl`、保存带 attempt 编号的原始响应，并原子更新 `summary.json`。硬中断最多可能丢失当时尚未落盘的单次请求，之前已成功的结果不会重跑。

Windows 若短暂锁定 `summary.json`，写入会自动重试并降级为直接写入；两种写法都暂时受阻时只记录一次警告并继续运行，避免汇总文件锁导致付费测试中断。此时 `results.jsonl` 仍是完整的逐请求事实记录。

恢复命令只需要原 run 目录：

```powershell
verdict-lab compare --resume runs/<run_id>
```

恢复过程以 `cases.jsonl` 为冻结样本清单，并校验 run 内的 taxonomy 与 pricing 快照。成功状态直接跳过；`provider_error`、`invalid_output` 或从未产生结果的组合重新运行。所有历史尝试都保留在 `results.jsonl`，费用与 token 汇总包含全部尝试，质量指标只采用每个组合的最新结果。

供应商返回 401、402、403、429，或明确的余额、credit、quota 错误时，本轮暂停该供应商，避免对剩余样本重复发送必然失败的请求；控制台和 `errors.log` 分别标记 `billing_or_quota`、`authentication_or_permission` 或 `rate_limit_or_quota`。另一供应商继续运行。补充额度或恢复服务后执行同一条 `--resume` 命令即可续跑。

`manifest.json` 的状态为 `running`、`paused` 或 `complete`，并记录当前暂停的供应商。新 run 同时保存 `taxonomy.snapshot.json` 和 `pricing.snapshot.json`，防止恢复期间配置发生静默变化。

`summary.json` 已按具有真值的方向计算 precision、recall、F1、accuracy 和缺失预测数。首次真实调用只用于接口探测，不形成模型质量结论；确认请求形状、权限、用量和账单后，再增加校准、阈值覆盖率及配对置信区间报告。
