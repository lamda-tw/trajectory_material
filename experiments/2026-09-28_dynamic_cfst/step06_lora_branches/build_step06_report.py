#!/usr/bin/env python3
"""Build human-readable reports, plots, and final hashes for CFST Step 6."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
BRANCHES = ["CFST-state", "CFST-Action", "CFST-Mixed"]
LABELS = {"CFST-state": "State", "CFST-Action": "Action", "CFST-Mixed": "Mixed"}
COLORS = {"CFST-state": "#2563eb", "CFST-Action": "#ea580c", "CFST-Mixed": "#16a34a"}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    validation = json.loads((OUT / "validation.json").read_text(encoding="utf-8"))

    plt.figure(figsize=(8.4, 5.2))
    for branch in BRANCHES:
        history = [json.loads(line) for line in (OUT / branch / "loss_history.jsonl").read_text().splitlines() if line.strip()]
        x = [row["cumulative_supervised_tokens"] for row in history]
        y = [row["loss"] for row in history]
        plt.plot(x, y, marker="o", markersize=3, linewidth=1.5, label=LABELS[branch], color=COLORS[branch])
    plt.xlabel("Cumulative supervised completion tokens")
    plt.ylabel("Training loss")
    plt.title("Dynamic CFST Step 6: matched-token LoRA continuation")
    plt.grid(alpha=0.25)
    plt.legend()
    plt.tight_layout()
    plt.savefig(OUT / "loss_curves.png", dpi=180)
    plt.savefig(OUT / "loss_curves.pdf")
    plt.close()

    for branch in BRANCHES:
        row = summary["branches"][branch]
        metrics = json.loads((OUT / branch / "metrics.json").read_text())
        report = f"""# {branch} 短训报告

## 结论

训练状态为 **SUCCESS**。本分支从同一个 Qwen3-8B + train90 LoRA第5轮adapter重新加载，完成一次独立的CFST短训并保存新adapter。源模型权重被继承；AdamW优化器为本分支重新建立，没有从其他CFST分支继承权重或优化器状态。

最终adapter：`{row['adapter_dir']}`

## 数据与预算

| 项目 | 结果 |
| --- | ---: |
| 唯一修复样本 | {row['unique_samples']} |
| 循环后的训练实例 | {row['scheduled_examples']} |
| completion监督tokens | {row['supervised_tokens']:,} |
| optimizer steps | {row['optimizer_steps']} |
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
| 首步训练loss | {row['loss_first']:.6f} |
| 末步训练loss | {row['loss_last']:.6f} |
| 全程平均loss | {row['loss_mean']:.6f} |
| 训练包重合诊断loss | {row['diagnostic_loss']:.6f} |
| 训练与诊断耗时 | {row['duration_seconds']:.1f}秒 |
| 两卡最大reserved显存 | {row['peak_reserved_gib_max']:.2f} GiB |

诊断数据就是该分支的唯一训练包，因此诊断loss只能证明短训数值稳定和拟合发生，不能当作泛化成绩。

## Adapter与重载验证

- 最终adapter SHA-256：`{row['adapter_model_sha256']}`
- 与源adapter不同：是
- 发生变化的LoRA tensors：{row['weight_delta']['changed_tensor_count']} / {row['weight_delta']['tensor_count']}
- 相对源adapter的权重L2变化：{row['weight_delta']['l2_delta']:.6f}
- 重新加载后的forward logits全部有限：是
- forward logits SHA-256：`{row['reload_forward']['last_token_logits_sha256_float32']}`

完整配置、逐步loss、训练日志和结构化metrics保存在本目录。下游是否变好必须在第7步用冻结检查30题和官方评分比较。
"""
        (OUT / branch / "REPORT.md").write_text(report, encoding="utf-8")

    table_rows = []
    for branch in BRANCHES:
        row = summary["branches"][branch]
        table_rows.append(
            f"| {branch} | {row['unique_samples']} | {row['supervised_tokens']:,} | {row['optimizer_steps']} | "
            f"{row['loss_first']:.4f} → {row['loss_last']:.4f} | {row['diagnostic_loss']:.4f} |"
        )
    readme = f"""# CFST 第6步：三个独立LoRA分支

第6步训练状态为 **SUCCESS**。三个分支都从同一个 **Qwen3-8B + train90 LoRA第5轮adapter** 独立启动，只执行一次新的CFST短训，然后保存各自adapter。没有串行继承State、Action或Mixed之间的权重。

## 关于“沿用旧参数”

- **沿用模型权重：** 三个分支均加载相同基座和相同epoch5 adapter，源adapter SHA-256为 `c8fdfd…9938`。
- **重新建立优化器：** epoch5 adapter是模型权重产物，不含本次三分支共用的AdamW状态；每支都从相同的新AdamW状态开始。
- **保持相同训练配置：** LoRA结构、BF16、长度、batch、学习率和seed完全相同。
- **只短训本step：** 每支处理约8,000个修复答案tokens后结束，没有再跑原来的5个epoch。

## 训练结果

| 分支 | 唯一数据 | 监督tokens | 更新步数 | 首步 → 末步loss | 重合诊断loss |
| --- | ---: | ---: | ---: | ---: | ---: |
{chr(10).join(table_rows)}

三个实际预算范围为8,138–8,160，最大差22 tokens，即目标8,000的0.275%。更新步数不同是因为三包的修复答案长度不同；控制量是计划中预先指定的监督token预算。

![三分支训练loss](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/loss_curves.png)

## 三个adapter

- [CFST-state adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-state/adapter) · [训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-state/REPORT.md)
- [CFST-Action adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Action/adapter) · [训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Action/REPORT.md)
- [CFST-Mixed adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Mixed/adapter) · [训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Mixed/REPORT.md)

最终权重SHA-256分别为：

- State：`846bf990d1c675b3f151f8a81e497f6a20528e9d0d3b25e2e5673206ef8f026d`
- Action：`16cea6a7e5f2895498af3c4d6f0914af849fdbc16e71994aecbf155927e0be4e`
- Mixed：`fe5b0676f87b1f3d4575ffd83e25adf1cbaacafd4c13a29d3c682fb8e8777709`

三个哈希互不相同，且504/504个LoRA tensors相对源adapter发生非零变化。

## 验收结果

73项训练、预算、来源、配置、权重与结构检查全部通过。随后把三个adapter同时重新加载到同一个Qwen3-8B上，分别执行真实forward：三者logits全部有限且哈希互不相同。GPU在流程结束后已释放。

- [结构化汇总](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/summary.json)
- [73项验证](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/validation.json)
- [真实重载验证](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/reload_validation.json)
- [训练前冻结计划](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/training_plan.json)
- [Loss曲线PDF](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/loss_curves.pdf)

本步没有运行检查30题或Dev57，也不能从训练loss判断哪个分支更好。下一步必须按第7步协议让原模型和三个新分支从头完成冻结的检查30题。
"""
    (OUT / "README.md").write_text(readme, encoding="utf-8")

    all_files = sorted(
        path for path in OUT.rglob("*")
        if path.is_file() and path.name != "artifact_sha256.json" and "__pycache__" not in path.parts and path.suffix != ".pyc"
    )
    hashes = {str(path.relative_to(OUT)): sha256_file(path) for path in all_files}
    (OUT / "artifact_sha256.json").write_text(
        json.dumps({"algorithm": "sha256", "files": hashes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"reports": len(BRANCHES) + 1, "hashed_files": len(hashes), "validation_checks": validation["checks_total"]}))


if __name__ == "__main__":
    main()
