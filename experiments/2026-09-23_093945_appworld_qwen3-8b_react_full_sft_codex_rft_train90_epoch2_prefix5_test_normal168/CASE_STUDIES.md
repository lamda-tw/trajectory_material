# 两轮与五轮的配对案例

以下案例按成功状态变化和不同执行行为选取，均核对原始模型回复、环境交互与官方评分。它们用于解释具体过程，不用于估计所有失败的原因占比；训练轮数对应的是本次两轮重训与旧五轮模型，不能忽略重训数值差异。

## A. `3d9a636_3`：两轮丢失五轮已能完成的好友同步任务

任务要求将Venmo好友调整为手机中标记为朋友的联系人集合，按需增删。**两轮0/5条件通过、50步耗尽；五轮5/5、18步完成。**

两轮模型前16步已经登录两个应用，按`relationship='friend'`检索手机联系人、读取Venmo好友，并查询增删好友文档。第17步却转而查询不存在的`phone.search_contact`，环境明确返回“没有这个API”。之后第19、21……49步重复查询同一不存在的接口，第18、20……50步交替打印接口列表；共17次相同接口文档查询失败。没有执行任务要求的好友增删，也没有提交完成。官方评分显示未发生要求的`venmo.Friendship`变更。

五轮模型也经历过错误接口查询，但随后使用有效的`search_contacts`和`relationship='friend'`，按两组好友集合计算差集并增删，重新查询后提交，全部通过。

这个例子说明**缩短到两轮不会让所有任务都改善**，也未自动消除“收到明确错误仍重复查询”的问题。两轮模型已能生成格式正确的Python并完成登录，但在推进到状态修改前陷入循环。它是任务规划与错误恢复层面的退化，不是模型文件损坏或上下文服务拒绝；也不能仅凭此例判定整体分数。

证据：[两轮第17步反馈](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/logs/environment_io.md:1070)、[两轮逐步模型回复](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/logs/lm_calls.jsonl:17)、[两轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/evaluation/report.md)、[五轮交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/logs/environment_io.md:952)、[五轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/evaluation/report.md)。

## B. `325d6ec_2`：两轮与五轮都偏离“已经下载”的目标

原始指令要求不断切换下一首，直到遇到**已经下载**的歌曲。**两轮3/5、16步；五轮3/5、16步；LoRA5/5、18步。**

两轮模型第9步给不支持分页的队列接口添加分页参数，报错后在第11步修正，说明它能处理一部分API错误。但第12步明确把目标改为“下一首没有下载的歌曲”，第14步用`play_music(song_id=30)`播放该歌曲，然后提交完成。官方核验显示目标歌曲应为66，实际停在30，而且除播放光标外还改动了队列。错误不仅是接口调用，还是选择条件取反和操作范围扩大。

五轮模型的实现又有所不同：它把原本未下载的歌曲主动下载，然后选择播放位置并提交；官方仍判定目标播放光标不正确，并存在额外下载状态变更。LoRA则逐次`next_song`，核对原有下载集合，达到条件后停止，全部通过。

这是一组**缩短训练后仍未修正任务语义的共同失败**。两轮修复了分页参数错误，并不意味着任务规划也正确；五轮的额外下载行为也不能靠更低的训练loss证明合理。它说明轮次之外，按用户原始约束选择目标、限制状态变更范围仍是需要观察的问题；本次没有进一步消融其训练来源。

证据：[两轮原始请求](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/logs/lm_calls.jsonl:1)、[两轮选择与播放过程](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/logs/environment_io.md:946)、[两轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/evaluation/report.md)、[五轮交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/logs/environment_io.md:1798)、[五轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/evaluation/report.md)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/logs/environment_io.md:823)。

## C. `21abae1_1`：两轮挽回五轮的月度转账统计错误

任务要求统计本月至今向他人转出的Venmo金额。**两轮2/2、19步；五轮1/2、10步；LoRA2/2、11步。** 两轮实际提交1029，五轮提交0，LoRA提交1029.0；官方核验两轮与LoRA答案正确。

五轮在日期格式报错后，把查询起止边界都设成当前同一时间，得到空列表便回答0。两轮第7步读取当前日期，第17步使用从月初到当前日期的查询范围和`direction='sent'`，分页取得交易，第19步求和并提交。本题中它避免了把“本月至今”缩成一个时间点的错误。

两轮过程并不干净：第8步尝试导入不允许的`contact`模块，第9步查询不存在的`contacts_list`接口；之后检索`relationship='person'`返回空列表，又把该空列表传入`user_email`。从实际环境返回看，第17步仍获取了非空的本月转出交易，最终金额通过官方核验。因此不能把这题概括成“联系人过滤逻辑全都正确”，只能说实际执行在此任务上得到正确答案。

这是明确的**两轮新增成功**，说明不同轮次确实会改变日期查询和执行决策；同时它也提醒我们：总体结论应来自168题配对，而不能只展示一个正确答案或一条更低的loss曲线。

证据：[两轮日期与首次错误](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:499)、[两轮实际交易返回](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:1241)、[两轮求和提交](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:1627)、[两轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/evaluation/report.md)、[五轮日期处理](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:499)、[五轮实际提交请求](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/api_calls.jsonl)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:641)。

## D. `8749218_1`：没有Python异常，也可以持续40步不推进任务

任务要求用推荐歌曲重置Spotify队列、打乱并播放。**两轮1/6、50步；五轮1/6、50步；LoRA6/6、20步。**

两轮前10步完成登录并读出队列、推荐歌曲。第11至50步共40次模型动作，只交替查询`play_music`和`show_song_queue`的文档，每个接口20次。原始环境日志没有Python执行异常，实际API日志也没有重置队列、打乱或播放的调用；全题52次API尝试中46次是文档查询。最终达到步数上限，任务条件未满足。

五轮同题也耗尽50步，但形式不同：它反复对`search_songs`传入不支持的`access_token`，收到明确错误后仍重试。LoRA虽也遇到过参数或队列索引错误，后来完成了清空、添加推荐、打乱和播放，全部通过。

这说明不能把“Python错误次数下降”直接解读成能力提高，也不能把所有重复行为都归因于五轮才出现的过拟合。两轮模型已经出现了文档查询取代实际操作的停滞；这个案例通过连续相同查询和缺失的任务操作确认停滞，而不是仅凭“查文档多”下结论。

证据：[两轮第11步起的重复查询](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/logs/environment_io.md:806)、[两轮API调用清单](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/logs/api_calls.jsonl)、[两轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/evaluation/report.md)、[五轮错误参数及重复](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/logs/environment_io.md:826)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/logs/environment_io.md:1176)。

## E. `0d01c76_2`：两轮正确保留文件正文，但同场景另两题仍失败

任务要求把指定目录中的Markdown文件导入笔记，按文件名生成标题并保留正文。**两轮6/6、15步；五轮3/6、36步；LoRA6/6、9步。**

两轮第8步列出目标文件，第10步逐个`show_file`，第12步用字典键`file['path']`和`file['content']`生成标题、创建15条笔记，第13步读回笔记检查存在及内容长度，最后提交。官方核验标题、正文及映射关系全部通过。

五轮此前反复对字典使用`.content`，出现`AttributeError`及未定义变量；最终以空字符串创建部分笔记并提交，正文和映射关系失败。两轮在这个任务上避开了错误的返回结构用法，恢复了应有内容。

但这不等于整个场景已经稳定解决：本次`0d01c76_1`和`0d01c76_3`都只有1/6条件通过，仍失败。因此该题贡献一个新增成功，**没有贡献一个完整成功场景**；应结合SGC和同场景三个变体理解泛化，不把单题改善扩大成场景级结论。

证据：[两轮读取文件](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/logs/environment_io.md:535)、[两轮创建与读回](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/logs/environment_io.md:807)、[两轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/evaluation/report.md)、[三个变体状态](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/task_status.jsonl:31)、[五轮返回结构错误与后续创建](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/logs/environment_io.md:622)、[五轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/evaluation/report.md)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/logs/environment_io.md:734)。

## F. `3b8fb7a_2`：两轮同样会因过量打印观察而超窗

任务要求依据旅行欠款笔记创建相应付款或收款请求。**两轮2/7、8次请求；五轮2/7、7次请求；LoRA2/7、12次请求，三者均失败。** 最后一次均为服务拒绝，不是正常模型生成。

两轮第7步按7个名字分别分页搜索Venmo用户，合并并打印全部匹配记录；下一次请求输入达到 **62,529 tokens**，超过固定32,000上下文，服务端返回400。实际只有7次正常模型回复，第8条空content是错误占位。五轮对应输入为40,802，LoRA为33,596，均在此前独立评测中超窗。

这个案例说明缩短训练并没有自动解决信息筛选和输出体积控制。两轮甚至在较早阶段输出了更大的候选集合，而不是因为用尽50步才失败；62,529也超过模型原生40,960窗口。它是三组共同失败，不能计入“两轮独有成功”或“五轮独有成功”的差额，也不能直接计算成扩大窗口后一定能挽回的一题。

证据：[两轮第7步批量查询](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/environment_io.md:1069)、[两轮第8次拒绝](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/lm_calls.jsonl:8)、[两轮官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/evaluation/report.md)、[五轮拒绝](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/lm_calls.jsonl:7)、[LoRA拒绝](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/lm_calls.jsonl:12)。
