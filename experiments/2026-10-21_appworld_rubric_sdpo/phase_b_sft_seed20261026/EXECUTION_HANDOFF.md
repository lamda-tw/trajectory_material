# 新 seed SFT 三轮运行交接

当前用户授权：从原始 Qwen3-8B 开始，换 seed，保持原恒定学习率流程；只验证 seed 复现。用户最后明确“不必设置时间上限，3轮跑完为止”。不得套用此前15小时限制，不自动改为学习率衰减，不恢复旧 seed 的暂停实验。

目录：/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026

训练 seed=20261026，原 seed=20261022；dev57 seed 仍=100。原始模型初始化新 LoRA，旧 batch001 数据没有复制。前5次有效更新 warmup，然后学习率恒定5e-5，纯ZeroFail3 SFT；18批/轮，3轮共54批；每轮评估完整dev57。脚本核心数值逻辑和数据筛选与原实验一致。

监督进程及命令见 runs/sft/launch.json；心跳见 runs/sft/heartbeat.json；进度见 STATUS.json。首批必须通过 loss、梯度、显存、模型来源和无SDPO的断言，才会进入后续批次。基础设施中断按原有流程重试；确定性或数值错误停下并留下日志，不更换失败任务。

如监督进程正常运行，勿再启动第二个runner。若异常，先检查 supervision/runner 日志和完整检查点；不能仅根据GPU短暂空闲断言停止，Codex评分阶段不占GPU。所有运行代码和关键配置已在 config/preparation_manifest.json 冻结，未弄清失败原因前不要改变配方。恢复前使用锁和检查点身份检查防重复更新。

模型仅保留batch001、018、036、054与最近两批完整状态；其他中间权重在后继检查点验证后清理，留下RETENTION.json。保留全部轨迹、评分、dataset、metrics、正式评估。不要删除旧实验任何数据。

AutoPanel run：appworld-rubric-ZeroFail3-SFT-seed20261026，链接位于/root/tf-logs，独立CPU导出器每30秒读取已提交指标；全局TensorBoard服务继续运行。报告自动写入 REPORT.md，分析数据为 analysis/seed_summary.json、training_metrics.csv、train_behavior.csv、dev_tasks.csv、paired_epochs.csv。旧seed前三轮基准已冻结在config/baseline_results.json。

三轮末以正式dev57成功、Macro、重复文档占比、业务动作数和逐题得失判断复现。不要把loss下降当作能力提高，也不要将新seed差异单独归因于LoRA初始化、题目顺序或采样中的某一种。第三轮相对第二轮的三个主要方向（成功下降、Macro下降、重复文档增加）会自动比较，但报告必须同时呈现全程和固定案例。

到三轮训练与三次dev57全部完成后自动停止；不启动第四轮、学习率对照或其他分支。

2026-10-27 中断恢复：第 14 批 Codex 网络超时后，已校验并恢复两份迟到的原回复，零新增评分请求。仅修改网络/进程恢复，25 项 CPU 检查通过；核心训练算法、配置和 prompt 未改动。新版监督程序对已识别的网络故障冷却后重试，对协议或数值错误仍停止。完整记录见 [INTERRUPTION_RECOVERY_20261027.md](INTERRUPTION_RECOVERY_20261027.md)。当前监督 PID 以 runs/sft/launch.json 为准，禁止再启动重复 runner。
