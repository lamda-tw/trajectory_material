# DEV57 差异案例复核

以下仅解释已经产生的评测轨迹；没有再次调用外部judge，没有重写训练动作，没有据此修改训练数据或官方分数。这里的过程判断来自原始代码、执行反馈与本地AppWorld接口规格，不能证明某个训练step导致了对应行为变化。

## 6bdbc26_1：rubric成功，uniform失败

任务要求当前Spotify歌曲所属艺人的关注人数。uniform后段连续重复`show_api_descriptions`，最后因上下文耗尽终止；rubric也经历了错误，但后续查到`show_artist`的完整规格，读取`follower_count`并将变量提交，官方2/2通过。此例显示局部反馈利用可能有价值，但一例不能证明R6筛选造成了改善。

[rubric原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/rubric/trajectories/6bdbc26_1.json)；[uniform原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/uniform/trajectories/6bdbc26_1.json)。

## b119b1f_3：uniform成功，rubric失败

任务要求逐首切换上一首，直到目标艺人。uniform反复执行`previous_song`并核对当前歌曲，找到目标后提交，官方6/6通过。rubric转而读取多个歌单，未完成要求的切歌操作，最终`complete_task(status="fail")`，官方1/6通过。读取本身能运行，不能代表朝任务要求推进；诚实报告失败也不等于解决任务。

[rubric原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/rubric/trajectories/b119b1f_3.json)；[uniform原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/uniform/trajectories/b119b1f_3.json)。

## b119b1f_1：同一API也可能造成不同状态变化

uniform使用`play_music(queue_position=1)`并无答案文本提交，官方6/6通过；rubric使用`play_music(song_id=...)`后提交`answer="Done"`，官方4/6通过。本地`play_music`文档说明：`song_id`分支会把歌曲加入队列，而`queue_position`选择已有队列位置并保留队列。不能仅根据API名相同、均执行成功、均播放目标歌手，就把这两种动作当作同等正确。这里存在可见的操作参数和交付差异；没有进一步将两个失败断言分别归因于哪个差异。

[rubric原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/rubric/trajectories/b119b1f_1.json)；[uniform原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/uniform/trajectories/b119b1f_1.json)；[Spotify规格](/root/autodl-tmp/data/benchmarks/appworld/runtime/data/api_docs/standard/spotify.json)。

## 4ec8de5_2：官方通过不能证明过程正确

任务要求统计歌曲库与专辑库中今年发行的歌曲数量。uniform官方2/2通过并输出30，但过程有明确问题：第10步对日期接口返回值调用`.get("year")`，而该接口成功规格只有`date`和`time`；第12步实际收集的是歌单内容，第13步又比较歌单歌曲中未提供的`release_year`。根据接口规格，这会发生缺失值之间的比较，不能视为正确实现了“今年”的筛选。这个成功应保留在事先确定的官方TGC中，同时标为过程存在明显疑点、结果可能偶合。

rubric也没有正确处理此题：反复修补日期字符串拆分，最后从`Thursday, May 18, 2023`的第3个空格片段得到18并当作年份；只对歌曲列表累加，没有正确覆盖所需范围，官方1/2通过。两组都不能仅因“代码终于执行成功”被当作高质量流程。

[rubric原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/rubric/trajectories/4ec8de5_2.json)；[uniform原轨迹](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/evaluation/uniform/trajectories/4ec8de5_2.json)；[日期接口规格](/root/autodl-tmp/data/benchmarks/appworld/runtime/data/api_docs/standard/phone.json)。

## 对下一轮策略的含义

这些例子支持区分“执行无错”“局部行为有依据”“实现了业务目标”和“官方终态通过”，不能用任何一个替代其他三个。但它们还不能识别本轮性能差异的训练因果来源。若继续仅用现有数据，优先检验业务决策/实际操作的覆盖和步骤类型配额，再在已通过质量筛选的目标内引入当前模型NLL；不能把重复查询、低质量高loss或偶然成功直接当作重点训练目标。候选正确业务步骤数量很少，本身就是数据供给限制，而不只是权重公式没有设计好。
