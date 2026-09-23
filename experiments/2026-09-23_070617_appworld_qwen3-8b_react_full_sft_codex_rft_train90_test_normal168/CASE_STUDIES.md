以下案例来自固定模型的一次正式运行，按不同失败类型选取，不能用少量案例估算全体原因占比。步号是原始环境交互编号；评分结论由官方 evaluator 给出，解释仅追溯实际执行过程。既列出退化，也列出 FFT 优于 LoRA 的反例。

### A. `8749218_1`：有明确错误反馈，仍重复同一个错误参数

- **要求**：用推荐歌曲重置 Spotify 队列，打乱并播放。LoRA **6/6 条件通过，20步**；FFT **1/6，50步耗尽**，没有上下文错误。
- **FFT过程**：第9步向 `search_songs` 传入不支持的 `access_token`，环境明确列出允许参数；第14、20、26、32、38、44、50步仍执行带同一非法参数的查询，中间反复查文档、取凭据、登录。累计8次相同类型的参数拒绝，播放队列没有发生任务要求的变更。
- **LoRA过程**：使用 `show_recommendations` 获取推荐歌曲；也经历过删除队列时参数名和动态下标错误，但随后继续清空、添加推荐歌曲、打乱和播放，全部条件通过。
- **说明**：关键差异是根据反馈修正行为并推动状态变化的能力。仅统计“有没有 Python 错误”会掩盖 LoRA 的恢复过程；FFT 并非因为生成格式失效或32K窗口而失败。

证据：[FFT交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/logs/environment_io.md:826)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/logs/environment_io.md:1176)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/8749218_1/evaluation/report.md)。

### B. `0d01c76_2`：返回结构理解错误，最终用空内容替代应复制的正文

- **要求**：把目录里的 Markdown 文件逐个导入笔记，文件名去扩展名、下划线换空格作为标题，保留对应正文。LoRA **6/6，9步**；FFT **3/6，36步**，没有上下文错误。
- **FFT过程**：第17、25、27、32步用 `.content` 访问 API 返回的字典，收到 `AttributeError` 后仍重复；还出现未定义的 `markdown_files`。第33、34步最终改为调用 `create_note(..., content='')`，部分标题也未按要求去掉扩展名，然后提交完成。官方判定新增笔记的标题集合、正文集合及标题到正文映射不符合要求。
- **LoRA过程**：第4步打印不可序列化对象也报过错，但第6步取得文件结构，第7步用 `file['content']` 访问正文，并从文件名生成标题后创建笔记，最终通过。
- **说明**：这是返回结构、变量状态和最终内容核验的复合失败；任务已提交不等于完成。该场景三个变体 `0d01c76_1/_2/_3` 均出现 LoRA 成功而 FFT 失败，提示应在场景层面看稳定性，不能把三个相关任务当作三次独立训练实验证据。

证据：[FFT交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/logs/environment_io.md:622)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/logs/environment_io.md:734)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/0d01c76_2/evaluation/report.md)。

### C. `325d6ec_2`：把“找到已下载歌曲”变成“下载一首歌曲”

- **要求**：继续切换下一首，直到遇到用户已经下载的歌曲。LoRA **5/5，18步**；FFT **3/5，16步**，没有上下文错误。
- **FFT过程**：查询已下载列表和队列后，发现候选歌曲未下载，却在第12步执行 `download_song`，随后选择一个队列位置播放并提交。官方评分显示额外改变了 `UserDownloadedSong`，且播放光标没有落在任务要求的目标歌曲。
- **LoRA过程**：多次调用 `next_song`，逐次核对该歌曲是否在原有下载集合内，到符合条件的歌曲才停止；没有额外下载，全部通过。
- **说明**：API 可以成功返回，但执行的是被改写的目标。此例主要是任务约束与状态选择错误，单纯延长窗口或增加步数并不会自动消除。

证据：[FFT交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/logs/environment_io.md:1798)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/logs/environment_io.md:823)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/325d6ec_2/evaluation/report.md)。

### D. `3d9a636_3`：FFT 的新增成功，不能把所有能力都概括为退化

- **要求**：将 Venmo 好友调整为手机中标记为朋友的联系人集合，按需增删。FFT **5/5，18步**；LoRA **1/5，9步**；两者都没有上下文错误。
- **FFT过程**：最初查询不存在的 `contacts` 文档失败，随后改查有效接口；用 `relationship='friend'` 筛选手机联系人，计算两个集合的增删差集，执行加好友和移除好友，并重新查询核对后提交。
- **LoRA过程**：读取全部联系人后，对“待添加”和“待删除”使用了相同的错误集合表达式；又因好友记录不存在 `contact_id` 报错，之后直接提交，未发生要求的好友变更。
- **说明**：FFT 并未整体失去代码/API使用或错误恢复能力。总分差异应表述为这些任务上的总体泛化和执行稳定性差异，不能解释成每一道题都更差或模型权重完全损坏。

证据：[FFT交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/logs/environment_io.md:952)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/logs/environment_io.md:1330)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3d9a636_3/evaluation/report.md)。

### E. `21abae1_1`：把“本月累计”错误压缩为一个时间点的查询

- **要求**：计算本月至今向他人转出的 Venmo 金额。LoRA **2/2，11步**；FFT **1/2，10步**，两者都没有上下文错误。
- **FFT过程**：第7步以 `YYYY-MM` 同时作为查询起止边界，收到日期格式错误；第8步改成当前完整时间，但仍把 `min_created_at` 和 `max_created_at` 设为同一个值，得到空列表后直接回答0。
- **LoRA过程**：构建按月的起止边界，分页查询转出交易，对金额求和，最终答案通过官方校验。
- **说明**：把一次异常修到“不再报错”，仍可能留下错误的业务语义。正确答案需要时间范围和聚合逻辑同时正确；该题的差异与输出格式和上下文窗口无关。

证据：[FFT交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:499)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/logs/environment_io.md:641)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/21abae1_1/evaluation/report.md)。

### F. `3b8fb7a_2`：双方都因长观察中断，这是共同限制而非单独的FFT退化

- **要求**：依据旅行欠款笔记创建相应付款或收款请求。FFT **2/7 条件通过**，6次正常回复后第7次请求被拒绝；LoRA **2/7**，11次正常回复后第12次请求被拒绝，两者均失败。
- **FFT过程**：第6步遍历并打印好友和全部交易记录，下一次请求输入达到 **40,802 tokens**，超过32,000，尚未开始生成就被拒绝。
- **LoRA过程**：第11步批量查询并打印联系人匹配结果，下一次输入达到 **33,596 tokens**，同样被拒绝。
- **说明**：单次过量打印就能耗尽上下文，并不一定要跑到50步。此例还解释了日志中的空content：它是服务拒绝后的占位记录，不能算作模型真实输出空白。双方都失败的此题不能计入“LoRA成功、FFT失败”的差额；扩大窗口后的潜在分数本次没有测量。

证据：[FFT交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/environment_io.md:1275)、[LoRA交互](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/environment_io.md:1141)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/evaluation/report.md)。
错误响应证据：[FFT第7次请求](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/lm_calls.jsonl:7)、[LoRA第12次请求](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/3b8fb7a_2/logs/lm_calls.jsonl:12)。

### G. `b9c5c9a_1`：发生在退化题中的超窗，但超窗前已经多次偏离正确过程

- **要求**：根据朋友最新的短信回复更新聚会 RSVP CSV。LoRA **7/7，26步**；FFT **1/7，24次正常回复后第25次请求被拒绝**，该次输入 **38,696 tokens**。
- **FFT过程**：第9步对不带分页参数的 `show_directory` 套用“直到空列表才结束”的循环，虽然递增 `page_index` 却没有传入接口，因此不断读取同一列表，触发单次代码1000次API请求上限。之后多次猜测不存在的CSV路径；第20和24步重复批量打印朋友消息，最终超出32K窗口。没有成功更新目标文件或提交。
- **LoRA过程**：先读取目录并定位实际文件，再按 `only_latest_per_contact=True` 检索回复；也经历了不存在接口和环境不允许的CSV函数报错，但后续采用字符串处理完成文件更新，全部通过。
- **说明**：本题确实贡献了“LoRA成功、FFT失败”的差额，且FFT终止于窗口限制；但错误分页、路径选择与重复输出在超窗前就已发生。不能把此题直接计算为“扩大窗口就能挽回的一题”，也不能把分页模板套错直接当作已经证明的训练记忆化。

证据：[FFT错误循环](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/b9c5c9a_1/logs/environment_io.md:1091)、[FFT重复消息输出](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/b9c5c9a_1/logs/environment_io.md:2866)、[FFT拒绝记录](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/b9c5c9a_1/logs/lm_calls.jsonl:25)、[LoRA文件更新与核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/b9c5c9a_1/logs/environment_io.md:1681)、[FFT官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/b9c5c9a_1/evaluation/report.md)、[LoRA官方评分](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/test_normal/tasks/b9c5c9a_1/evaluation/report.md)。
