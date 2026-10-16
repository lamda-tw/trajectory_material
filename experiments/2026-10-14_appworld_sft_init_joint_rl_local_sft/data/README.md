# Completion-only SFT 数据

正式入口为 `data_manifest.json`；只遍历其中的 2,623 个样本，不递归扫描归档目录。

- `sft_samples.jsonl`：原始历史消息、完整目标文本和编码引用。
- `encoded/*.npz`：input_ids、labels、attention_mask、loss_mask；无 padding、无截断。
- `scripts/sft_dataset.py`（实验根下）：Dataset 返回 input_ids/labels/attention_mask 的 torch.long 张量；collator 右侧 padding，labels=-100。

labels 未移位。手写 loss 用 logits[:, :-1] 对 labels[:, 1:]，只做一次 causal shift。不能直接使用 HF 模型默认的标量 loss 代替步骤等权目标；应获取逐 token CE，排除 labels=-100 后，在每个原始步骤内平均，再对本次 optimizer update 的步骤平均。不要再次应用 chat template 或把末尾 EOS 重复加入目标。loss_mask 仅供检查，不直接作为模型 forward 的额外参数。

单遍目标 205,238 token；最长完整样本 31,814 token。初始 empty-think 前缀在 prompt 内，不监督；原始生成的 EOS 在 target 内，参与监督。历史中的原始示例及工具观察保留但不监督。训练是否能在 GPU1 完整运行仍需实际模型 smoke，当前未训练。

若一次更新有 M 个原始步骤、步骤 s 有 T_s 个完整目标 token，微批或分段应累积 CE_sum/(M*T_s)。分段长度不取代 T_s；padding 和历史不计分母。总目标 token 数仅用于预算。现有 Dataset/Collator 提供所需 token 和 mask；自定义归约及梯度验收待联合 trainer 步骤实现。
