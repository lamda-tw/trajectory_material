# CFST-state 短训报告

## 结论

训练状态为 **SUCCESS**。本分支从同一个 Qwen3-8B + train90 LoRA第5轮adapter重新加载，完成一次独立的CFST短训并保存新adapter。源模型权重被继承；AdamW优化器为本分支重新建立，没有从其他CFST分支继承权重或优化器状态。

最终adapter：`/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-state/adapter`

## 数据与预算

| 项目 | 结果 |
| --- | ---: |
| 唯一修复样本 | 12 |
| 循环后的训练实例 | 54 |
| completion监督tokens | 8,138 |
| optimizer steps | 27 |
| 最大长度 | 40,960 |
| prompt是否计算loss | 否 |

训练实例来自第5步对应的唯一JSONL，按固定顺序循环到不少于8,000个监督tokens，并保证实例数为偶数。没有使用检查30题或Dev57答案。

## 共同训练配置

- 基座：`/root/autodl-tmp/models/Qwen3-8B`
- 起点adapter SHA-256：`c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`
- LoRA：r=8，alpha=16，dropout=0；训练21,823,488个LoRA参数
- 两卡DDP；每卡batch=1；全局batch=2；gradient accumulation=1
- AdamW；learning rate=2e-4；weight decay=0；无warmup与scheduler
- BF16；SDPA；seed=20260928；Qwen thinking关闭
- loss只覆盖assistant修复completion，并按两卡实际监督tokens做全局加权

## 数值结果

| 指标 | 结果 |
| --- | ---: |
| 首步训练loss | 1.063175 |
| 末步训练loss | 0.094404 |
| 全程平均loss | 0.386611 |
| 训练包重合诊断loss | 0.036427 |
| 训练与诊断耗时 | 152.9秒 |
| 两卡最大reserved显存 | 91.53 GiB |

诊断数据就是该分支的唯一训练包，因此诊断loss只能证明短训数值稳定和拟合发生，不能当作泛化成绩。

## Adapter与重载验证

- 最终adapter SHA-256：`846bf990d1c675b3f151f8a81e497f6a20528e9d0d3b25e2e5673206ef8f026d`
- 与源adapter不同：是
- 发生变化的LoRA tensors：504 / 504
- 相对源adapter的权重L2变化：6.224807
- 重新加载后的forward logits全部有限：是
- forward logits SHA-256：`0997bf9efda5d28c304050b3dcfa682ff89f97373f51afe99201835df60058d2`

完整配置、逐步loss、训练日志和结构化metrics保存在本目录。下游是否变好必须在第7步用冻结检查30题和官方评分比较。
