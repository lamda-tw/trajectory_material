# 两轮截取同一五轮学习率路径的过度训练假说验证

本次固定训练2轮/1170步，从原始基座重新初始化，沿用train90的1170个决策样本、seed=20260921、双卡batch=2、FP32主参数与AdamW状态、BF16计算、completion-only监督、梯度裁剪1.0。

学习率仍采用原五轮2925步计划（88步warmup、峰值1e-5、cosine最低比例0.1），仅执行前1170步。直接将整个cosine压缩到两轮会同时改变学习率路径，本次不这样做。

每轮导出一份BF16模型，保存epoch1及最终epoch2；不保存optimizer大文件。本次仅评测预先指定的epoch2。模型导出通过权重结构、SHA-256和重载检查后，按epoch5原协议运行test_normal168（32K、50步、3000输出tokens、temperature0、seed100、无reasoning parser）。

最终报告对照epoch2、epoch5与LoRA，并比较训练前1170步的LR、样本顺序/长度及loss复现程度。旧epoch2权重已不存在，因此这是同设置重跑，不能预先保证逐位复现。测试集已在前次实验中被观察，本次属于预先固定轮次的验证性对照，不是新的盲测，也不证明其他轮次或全部全参数训练会有相同规律。

实验产物和缓存保存在这两个experiments目录；评测沿用工作区内的短临时目录workspace-tw/tmp/aw-*（Unix socket路径长度限制）和GPU锁；原始基座、envs和既有实验只读。
