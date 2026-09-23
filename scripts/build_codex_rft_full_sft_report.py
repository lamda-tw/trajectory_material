#!/usr/bin/env python3
"""Build a factual Chinese report for the five-epoch train90 full SFT run."""
import argparse
import json
from pathlib import Path


def load(path):return json.loads(Path(path).read_text())


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--experiment',type=Path,required=True)
    parser.add_argument('--lora-experiment',type=Path,required=True)
    args=parser.parse_args()
    exp=args.experiment.resolve()
    cfg=load(exp/'config/training_config.json')
    met=load(exp/'metrics/metrics.json')
    probe=load(exp/'probe/metrics/metrics.json')
    first=load(exp/'probe/metrics/before_restart.json')
    loss=load(exp/'metrics/loss_summary_5epochs.json')
    compare=load(exp/'metrics/loss_comparison_summary.json')
    gen_path=exp/'metrics/generation_smoke.json'
    gen=load(gen_path) if gen_path.exists() else {'status':'NOT_AVAILABLE','python_block_count':0}
    tr,model=met['training'],met['model']
    val=met['validation']
    assert met['status']=='SUCCESS' and tr['epochs_completed']==5 and tr['global_steps']==2925
    assert model['trainable_parameters']==model['total_parameters']==8190735360
    assert met['data']['train']['truncated_samples']==0
    assert Path(model['final_model']).is_dir()
    assert probe['status']=='SUCCESS' and probe['training']['global_steps']==20
    assert first['status']=='STOPPED_FOR_RESUME' and first['training']['global_steps']==10
    assert model['master_parameter_dtype']==model['optimizer_state_dtype']=='float32'
    history=tr['history']
    assert [r['step'] for r in history]==list(range(1,2926))
    resources=[json.loads(x) for x in (exp/'logs/resource_usage.jsonl').read_text().splitlines() if x.strip()]
    ram_peak=max(int(r['memory.current']) for r in resources)/1024**3
    disk_min=min(r['disk_free_bytes'] for r in resources)/1024**3
    event_first=resources[0].get('memory.events','')
    event_last=resources[-1].get('memory.events','')
    old=compare['series'][0]['epoch_mean_loss']
    epoch_rows='\n'.join(f"| {r['epoch']} | {r['steps']} | {r['mean_loss']:.6f} | {r['first_20_mean_loss']:.6f} | {r['last_20_mean_loss']:.6f} | {old[r['epoch']-1]:.6f} |" for r in loss['epoch_summaries'])
    gpu_rows='\n'.join(f"| {r['rank']} | {r['peak_allocated_gib']:.2f} | {r['peak_reserved_gib']:.2f} |" for r in met['distributed']['ranks'])
    probe_peaks=[max(a['peak_allocated_gib'],b['peak_allocated_gib']) for a,b in zip(first['distributed']['ranks'],probe['distributed']['ranks'])]
    first50=sum(r['train_loss'] for r in history[:50])/50
    last50=sum(r['train_loss'] for r in history[-50:])/50
    result='SUCCESS' if gen.get('status')=='PASS' else 'TRAINING_COMPLETE_WITH_GENERATION_WARNING'
    report=f'''# AppWorld Codex-RFT train90：Qwen3-8B 全参数 SFT 五轮实验报告

## 结论

本次训练已完成 **5 个连续 epoch、2925 个双卡同步 optimizer steps**。训练状态为 **{met['status']}**，包括模型重载检查的综合状态为 **{result}**。

从原始 Qwen3-8B 初始化，更新 **{model['trainable_parameters']:,}/{model['total_parameters']:,} 个参数（100%）**，未加载或合并 LoRA。最终完整模型位于 `artifacts/model/`，可供 Transformers 或 vLLM 后续加载。

前 50 步平均 loss 为 **{first50:.6f}**，后 50 步为 **{last50:.6f}**。这些数值描述训练拟合，不能代替 AppWorld Dev/test 的端到端能力评测。本实验未运行 Dev 或 test_normal。

## 数据与对照边界

- 数据与 2026-09-21 的 train90 LoRA 相同：90 个任务、90 条 Codex 成功轨迹、1170 个决策样本；难度 1/2/3 为 36/36/18。
- train.jsonl SHA-256：`{cfg['train_sha256']}`。
- 输入 token min/p50/p95/max：3181/7249/16040/37015；最大窗口 40960，训练额外 token 截断 **0 条**。原转换数据已有 observation 脱敏与字符级裁剪，这里没有更改该数据版本。
- 只监督当前 assistant completion；prompt 和 padding 不参与 loss；chat template 使用 `enable_thinking=False`。
- 90 条训练内诊断样本来自每个任务的最后决策，全部与训练集重叠，不是独立验证集。
- 同数据 LoRA 参考：`{args.lora_experiment.resolve()}`。本实验改变了参数更新范围、学习率/调度和数值精度策略，不是只改变一个变量的消融实验。

## 实际训练设置

| 项目 | 实际设置 |
|---|---|
| 基座 | `{model['source_base_model']}` |
| 分布式 | 两张 GPU，FSDP FULL_SHARD，按 Qwen3DecoderLayer 包装 |
| 参数 / 梯度归约 / AdamW 状态 | FP32 |
| 前后向计算 / 最终 HF 权重 | BF16 |
| attention / KV cache | SDPA / 训练关闭 cache |
| 每卡 batch / 全局 batch / 梯度累积 | 1 / 2 / 1 |
| epoch / 每轮步数 / 总步数 | 5 / 585 / 2925 |
| optimizer | fused AdamW，betas=(0.9,0.999)，eps=1e-8，weight_decay=0 |
| LR | 峰值 1e-5；88 步 linear warmup；cosine 衰减至 1e-6 |
| 梯度裁剪 | global norm 1.0 |
| seed | 20260921，与同数据 LoRA 对齐 |
| 激活策略 | reentrant gradient checkpointing；未启用 activation CPU offload |
| loss 归约 | 每个样本对 completion token 求均值，再在两个 rank 间平均 |

## 显存优化与预检

旧实现虽然屏蔽了 prompt label，仍对完整长序列构造词表 logits。本次只对预测 completion 的 hidden-state 位置计算 logits，并保持 causal 标签移位正确；全部上下文仍经过 transformer，梯度回传到全部参数。

CPU 微型 Qwen3 回归测试覆盖不同 completion 长度、padding、首个目标 token，并逐参数比较 loss/梯度；另验证了恢复后的下一次更新和 scheduler 与连续执行完全一致。记录见 `logs/00_cpu_tests.log`。

正式训练前完成 **20 步真实双卡压力预检**：先用短样本初始化 AdamW 状态，覆盖最长 6 条样本、最长 completion、16K/24K 附近长度和长短交替，并交换 rank。第 10 步保存 FP32 参数与 optimizer 后退出进程，重新加载继续至第 20 步，随后完成诊断 forward。两个进程阶段的峰值 allocated 分别合并为 rank0={probe_peaks[0]:.2f} GiB、rank1={probe_peaks[1]:.2f} GiB。

probe 的权重和续训状态已在验证成功后清理；正式训练重新从原始基座初始化，不继承 probe 更新。确定顺序见 `config/probe_schedule.json`。

## 五轮 Loss

| epoch | 步数 | 本次平均 loss | 本次前20步 | 本次后20步 | 旧67轨迹平均 loss |
|---:|---:|---:|---:|---:|---:|
{epoch_rows}

![本次五轮训练 loss](metrics/loss_curve_total_5epochs.png)

本图浅蓝线为逐步 loss，红线为向后 50 步移动平均，虚线分隔 epoch。可下载 [PDF](metrics/loss_curve_total_5epochs.pdf) 和 [逐步 CSV](metrics/loss_history_5epochs.csv)。

![67轨迹与90轨迹全参数训练对比](metrics/loss_curve_compare_full_sft_67_vs_90.png)

比较图按完成的 epoch 数对齐，分别用约 0.1 个 epoch 的因果移动平均（旧 32 步、新 58 步）。另有 [PDF](metrics/loss_curve_compare_full_sft_67_vs_90.pdf)、[对比 CSV](metrics/loss_comparison_67_vs_90.csv) 和 [结构化摘要](metrics/loss_comparison_summary.json)。

旧实验为 67 任务/640 样本、最长 25070 tokens、2e-4 固定 LR、BF16 主参数/优化器状态；本次为 90 任务/1170 样本、最长 37015 tokens、1e-5 调度 LR、FP32 主参数/状态。数据来源、规模、学习率和数值实现不同，曲线只能描述各自训练集的拟合过程，不能证明泛化能力谁更好。旧实验 Dev 退化的具体原因也没有通过本次训练被隔离证明。

## 资源、耗时与保存策略

| rank | 正式训练峰值 allocated（GiB） | 峰值 reserved（GiB） |
|---:|---:|---:|
{gpu_rows}

- 正式训练、续训检查点保存、诊断和最终模型导出耗时：**{tr['elapsed_seconds']/3600:.2f} 小时**；不含此前数据准备、probe 和之后重载生成。
- 每 5 秒采样的容器 RAM 使用峰值约 **{ram_peak:.2f} GiB**，容器上限 220 GiB；采样可能漏掉更短暂的峰值。
- 采样到的最小磁盘可用量约 **{disk_min:.2f} GiB**。资源原始记录：`logs/resource_usage.jsonl`。
- cgroup memory.events 采样起点：`{event_first.replace(chr(10), '; ')}`；报告生成前末次：`{event_last.replace(chr(10), '; ')}`。
- 因初始可用磁盘约 197 GiB，本次采用**滚动完整续训状态 + 最终 HF 模型**，未保留 epoch 1–4 的独立 HF 权重。所有 epoch 的逐步 loss 均保留。
- 每 100 步和每轮末保存 `artifacts/restart/` 下的完整 FP32 参数分片、AdamW、scheduler、各 rank RNG、步数和采样进度。新状态全部写入并落盘后，才移除本实验的旧状态；保存期间最多两份。
- 最终续训状态为第 2925 步，适用于相同代码、数据哈希、依赖版本、FSDP 包装和双卡拓扑。部署/评测使用 `artifacts/model/`，不是直接加载分片 pickle。

## 诊断、模型重载与产物核验

- 训练内 token 加权诊断 loss：**{val['loss']:.6f}**；perplexity：**{val['perplexity']:.6f}**。
- 最终模型从磁盘重新加载并生成 ReAct Python：**{gen.get('status')}**；非空 Python fenced code block 数为 {gen.get('python_block_count')}。
- 完整指标：`metrics/metrics.json`；连续 2925 步历史：`metrics/training_history.jsonl`。
- 最终权重 SHA-256：`metrics/final_model_weights.sha256`；代码、配置及轻量产物清单：`artifacts.sha256`。
- 配置、代码快照及复现命令分别位于 `config/`、`scripts_snapshot/`、`command.txt`；数据和原始基座均未修改。

## 后续评测

建议使用本次最终 epoch 5 模型与同数据 LoRA 对齐 AppWorld Dev 57 题：相同 ReAct prompt、无 reasoning parser 的输出接口、temperature=0、seed=100、最多 50 步、每次最多 3000 输出 tokens、推理 context=32000。训练窗口为 40960 不意味着评测自动扩窗；如比较扩窗效果，应为双方另设同条件实验。

本次没有保留中间独立 HF 模型，不能按原计划在五个 epoch 间选模。先报告固定最终模型的 Dev 结果，再决定独立 test_normal 评测；测试集反馈不用于训练或选择 checkpoint。
'''
    (exp/'REPORT.md').write_text(report)
    (exp/'EVAL_READY.md').write_text(f'# 后续评测入口\n\n最终模型：`{model["final_model"]}`。\n\n重载生成：{gen.get("status")}。尚未运行 Dev/test；只保留最终 epoch 5 的独立 HF 模型，完整训练记录见 [REPORT.md](REPORT.md)。\n')
    print(report)

if __name__=='__main__':main()
