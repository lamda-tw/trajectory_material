# AppWorld Train-15 四模型对齐诊断套件

本套件固定评测 5 个 scenario、每个 3 个任务，共 15 题：e85d92a、302c169、34d9492、60d0b5b、3c13f5a。它们全部属于 Train90 与 SFT67 交集，覆盖五种 required-app 组合以及 7/8、10、13 步复杂度。结果只能解释训练内行为，不是未见任务泛化估计。

四组共享官方 ReAct prompt 快照、任务顺序、temperature=0、seed=100、max completion=3000、max steps=50、vLLM max model len=32000、max num seqs=3、Hermes tool parser、auto tool choice 和官方 evaluator。Base 严格复用原始正式 Dev 接口：deepseek_r1 reasoning parser，Qwen3 chat template 默认 thinking；LoRA、Full epoch2、Full epoch5 严格复用各自 aligned Dev 接口：不传 reasoning parser，并把返回的 reasoning_content null 归一化为空字符串。SimplifiedReActCodeAgent 始终消费 content 字段。

目录：
- selection/selection.json：Train90、SFT67、交集、20 个完整候选及固定 15 题元数据。
- scripts_snapshot/：冻结 runner、launchers、prompt、config contract、静态校验和报告构建器。
- smoke/<variant>/：每模型单题接口 smoke，完全不进入正式统计。
- runs/<variant>/：每模型独立 AppWorld root 与正式 15 题结果。
- artifacts/：最终中文报告、结构化摘要与报告哈希。

每个 run root 都会真实复制 data/datasets/train_15.txt。任务状态逐行 flush+fsync；已完成且已有 evaluator 报告的任务恢复时跳过。每题记录原始 OpenAI output 到 raw_openai_responses.jsonl，并审计 content、reasoning_content、finish_reason、可执行 Python、正确 task ID 和 evaluator 报告。正式阶段只有在四个 smoke 的 interface_pass 全部通过后才允许启动。

未来启动命令记录在根目录 command.txt。当前创建阶段只做静态与 fixture 校验，未启动任何模型、vLLM 或 AppWorld 正式评测。

