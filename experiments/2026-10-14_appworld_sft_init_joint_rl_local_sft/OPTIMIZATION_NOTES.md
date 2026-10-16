# 前缀共享优化：留作后续改进，本次不启用

2026-10-15，北京时间。用户最新指令：“暂时不跑，将优化留作之后的改进，当前任务仍进行。”

**决定：停止推进本次优化切换。当前训练继续使用原代码、原配置和原进程，在物理 GPU1 完成15批、导出最终LoRA后结束。没有安排优化版训练、GPU基准测试、自动切换或完成后的优化任务。**

记录时已提交6/15批，正在第7批。训练进程PID仍为684724；范围控制中记录的7个训练源码文件哈希全部保持一致。此次调查只增加了独立CPU原型、核算和测试结果，没有修改正在运行的训练实现。

## 已完成的调查

现实现对每个action分别计算完整前缀并反向传播，同一轨迹的历史因此反复计算。参考模型概率已有一次性缓存；RL和KL共享当前策略的前向结果。主要优化机会是历史前缀的重复主干计算。

不能直接把最后一步的历史当成全部步骤的原始输入：真实数据中，当前生成提示末尾的空thinking包装与下一步历史中的assistant文本不同。可行候选是按**完全相同的原始token前缀**建立树，分支只关注自己的祖先，RoPE位置使用原始深度，并让共享前缀参与正常反向传播。不能使用detach的推理KV缓存代替这一梯度图。

独立原型位于 [optimization/prefix_sharing](optimization/prefix_sharing/)。它没有接入联合训练器。链式分支attention使用带前缀偏移的因果mask；对应机制见 [PyTorch 2.8 causal_lower_right](https://docs.pytorch.org/docs/2.8/generated/torch.nn.attention.bias.causal_lower_right.html)。

540条真实轨迹的原始输入路径、目标token和位置均已核对：

| 核算项目 | 原实现 | 候选前缀共享 |
| --- | ---: | ---: |
| RL主干token位置 | 104,808,460 | 不限树大小：9,450,300 |
| RL主干token位置，单组最多32,000节点 | 104,808,460 | 13,947,353 |
| SFT主干token位置，本候选暂不优化 | 22,227,470 | 22,227,470 |
| RL+SFT总位置，按上述分组 | 127,035,930 | 36,174,823 |

无限制树最大57,241节点，56条轨迹超过32,000节点，因此不能只报告理想共享量而忽略显存。候选按action组拆分成730个计算组，保留全部样本及完整上下文，归约仍使用原轨迹/步骤的分母。32,000只是待验证的节点预算，尚未证明GPU显存足够。计算位置约减少71.5%，**不是实测加速71.5%或保证3.51倍提速**。

- [完整布局核算](checks/prefix_sharing_layouts.json)：基于前6批耗时，原整轮梯度阶段线性估计约29.18小时；候选按位置线性缩放约8.31小时。这不是GPU实测ETA，不包含实现/验收时间，也不能据此批准停止当前运行。既有reference缓存可复用，无须重复其约5小时计算。
- [CPU FP32数值测试](checks/prefix_sharing_equivalence.json)：tiny Qwen3、7种LoRA投影、非零LoRA B、开启/关闭checkpoint，覆盖分支、重复目标、不同目标共享query和不同序列根。最大logprob误差约4.77e-7，梯度相对L2误差小于5.6e-7；不是8B GPU验收。
- [CPU BF16探索性对照](checks/prefix_sharing_bf16_cpu.json)：单个tiny模型分支案例，logprob最大差约9.62e-4、梯度相对L2差约0.00845、梯度余弦约0.999966。不能宣称逐位一致，也不能用此替代真实模型验证。

## 以后恢复优化工作时的步骤

1. 完成独立训练器集成，保留全部540条RL轨迹、2623个SFT步骤、原始EOS、old/reference概率及原调度；保持RL按轨迹token归约、SFT步内平均后步骤平均。仅优化计算复用。
2. 在用户允许的后续GPU1测试窗口，用真实8B、BF16和已有LoRA比较原实现与候选的logprob、联合loss、LoRA梯度和一次更新，覆盖短/中/最长轨迹及需要拆组的轨迹。
3. 测量前向、反向、峰值显存及完整联合batch耗时，检查attention实际使用的kernel。不同后端的性能和浮点结果可能不同，见 [PyTorch SDPA说明](https://docs.pytorch.org/docs/2.8/generated/torch.nn.functional.scaled_dot_product_attention.html)。
4. 再决定是否采用。若将来在另一次运行中切换，优先保留最新已提交checkpoint的LoRA、AdamW状态、RNG、全局学习率位置和已消费数据范围，在独立输出中记录实现变更。无须因为优化计算方式就丢弃已有更新。

以上步骤目前均不自动执行。当前任务仍遵循 [SINGLE_POOL_MODEL_SCOPE.md](SINGLE_POOL_MODEL_SCOPE.md)。
