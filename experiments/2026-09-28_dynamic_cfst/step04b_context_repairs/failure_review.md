# CFST 第4B步：上下文拒绝前的错误审查

这8题严格来自第2步冻结的来源60题，顺序未改变。候选输入均满足 `prompt tokens + 3000 <= 32000`。暂定标签只描述执行前证据，最终只按成功修复时教师实际动作重核。

| 顺序 | 任务 | 替换动作 | 窗口占用 | 暂定标签 | 审查结论 |
| --- | --- | ---: | ---: | --- | --- |
| 1 | 76f2c72_2 | 11 | 8616+3000=11616 | 恢复错误 | 第10步用缺少月份部分的正则筛选当前年份账单，得到意外空列表；第11步扩大搜索范围却重复同一错误正则，仍返回空列表。 |
| 2 | b0a8eae_1 | 5 | 9146+3000=12146 | 状态错误 | 首次业务查询同时翻完所有含workout的笔记和所有公开歌单，并把完整对象全部打印，单步输出把下一请求推到66,948 tokens。 |
| 3 | 2a163ab_1 | 9 | 8959+3000=11959 | 状态错误 | 登录与室友关系已经恢复成功，但第9步翻完并打印整个Venmo社交动态，没有在环境内按当天和室友邮箱过滤。 |
| 4 | 2a163ab_2 | 17 | 10539+3000=13539 | 状态错误 | 日期解析异常已经在第8步自行恢复；第17步仍翻完并打印整个Venmo动态，没有按昨天和兄弟姐妹邮箱过滤。 |
| 5 | 22cc237_2 | 19 | 28506+3000=31506 | 恢复错误 | 模型已看到unpaid_friends的值是金额而不是邮箱，也已连续收到user_email类型错误，第19步仍逐项重复完全相同的无效付款请求。 |
| 6 | 22cc237_1 | 5 | 7330+3000=10330 | 状态错误 | 首次业务查询把所有含dinner的笔记和全部收款记录完整打印；此后又重复读取同一批笔记，历史在第11次请求因预留3,000输出tokens而超限。 |
| 7 | c901732_2 | 3 | 7867+3000=10867 | 状态错误 | 歌单搜索接口返回宽泛结果，第3步翻完所有页面并打印数百个歌单，没有即时限定标题和目标所有者。 |
| 8 | 2a163ab_3 | 9 | 9554+3000=12554 | 状态错误 | 联系人401已通过登录恢复；第9步翻完并打印整个Venmo动态，没有在环境内按昨天/今天和同事邮箱过滤。 |

## 逐题证据

### 1. 76f2c72_2：替换第11步
- 任务：What is the total cost of my internet bills for this year? The bills are in "~/bills/" directory of my file system.
- 官方未满足条件（仅审查可见）：assert answers match.
- 日志证据：动作10输出[]；动作11再次使用 current_year + r'\.\w+'，而真实文件名包含 YYYY-MM，输出仍为[]。
- 暂定类别：恢复错误。第10步用缺少月份部分的正则筛选当前年份账单，得到意外空列表；第11步扩大搜索范围却重复同一错误正则，仍返回空列表。
- 修复方向：利用已经读入的账单内容或改正年份-月份文件名筛选，直接计算当前年份网络账单总额，停止跨应用漫游。
- 固定窗口：原输入8616 tokens，预留输出3000，合计11616/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 2. b0a8eae_1：替换第5步
- 任务：Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match spotify.MusicPlayer.；assert music_player in the end state is in the playing state.；assert the music_player's queue_songs' total duration in the end state is >= data.private.workout_duration_mins.；assert the set music_player's queue_songs' song_ids in the end state match set of private_data.long_enough_playlist_song_ids.
- 日志证据：动作5输入9,146 tokens，输出包含大量无关Habit Tracking笔记和歌单；紧接着的第6次模型请求被32,000窗口拒绝。
- 暂定类别：状态错误。首次业务查询同时翻完所有含workout的笔记和所有公开歌单，并把完整对象全部打印，单步输出把下一请求推到66,948 tokens。
- 修复方向：只保留与当天锻炼计划和候选歌单有关的少量字段，读取匹配笔记正文并计算所需时长，避免打印全集。
- 固定窗口：原输入9146 tokens，预留输出3000，合计12146/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 3. 2a163ab_1：替换第9步
- 任务：Like all the venmo transactions from today involving any of my roommates on my venmo social feed.
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match venmo.Transaction, venmo.TransactionLike；assert set of all new transaction likes (obtained via models.changed_records) is identical to set of private_data.recent_relative_transaction_ids.；assert all newly liked transaction_ids are in private_data.recent_transaction_ids.；assert all newly liked transaction_ids are in private_data.relative_transaction_ids.
- 日志证据：动作9输入8,959 tokens；完整social_feed输出使下一请求达到197,952 tokens。此前第5步401已在第7步成功恢复。
- 暂定类别：状态错误。登录与室友关系已经恢复成功，但第9步翻完并打印整个Venmo社交动态，没有在环境内按当天和室友邮箱过滤。
- 修复方向：在同一代码单元中按当前日期和室友邮箱筛选，保留目标transaction_id并执行或准备点赞，不回传完整动态。
- 固定窗口：原输入8959 tokens，预留输出3000，合计11959/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 4. 2a163ab_2：替换第17步
- 任务：Like all the venmo transactions from yesterday involving any of my siblings on my venmo social feed.
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match venmo.Transaction, venmo.TransactionLike；assert set of all new transaction likes (obtained via models.changed_records) is identical to set of private_data.recent_relative_transaction_ids.；assert all newly liked transaction_ids are in private_data.recent_transaction_ids.；assert all newly liked transaction_ids are in private_data.relative_transaction_ids.
- 日志证据：动作17输入10,539 tokens，完整列表使下一请求达到266,081 tokens；第7步日期异常并非未恢复错误。
- 暂定类别：状态错误。日期解析异常已经在第8步自行恢复；第17步仍翻完并打印整个Venmo动态，没有按昨天和兄弟姐妹邮箱过滤。
- 修复方向：在环境内按昨天日期和兄弟姐妹邮箱过滤，只输出或处理目标交易ID。
- 固定窗口：原输入10539 tokens，预留输出3000，合计13539/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 5. 22cc237_2：替换第19步
- 任务：I went on a dinner with some of my friends yesterday. I paid the entire bill to simplify the payment. I've made a note of individual shares in simple note. Some people have already sent me their share on venmo. Make payment requests for others with a description note "Friends Dinner".
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match venmo.Notification, venmo.PaymentRequest.；assert user_id_to_share obtained from added_payment_requests matches the private_data.pending_user_id_to_share (tolerance=1.0)
- 日志证据：动作18明确打印Adrian->36.0等错误映射；动作17的8次请求全部422；动作19再次把这些浮点数传给user_email。
- 暂定类别：恢复错误。模型已看到unpaid_friends的值是金额而不是邮箱，也已连续收到user_email类型错误，第19步仍逐项重复完全相同的无效付款请求。
- 修复方向：从已经取得的联系人中重建姓名到邮箱映射，排除已付款者，再用正确邮箱、金额和固定描述创建收款请求。
- 固定窗口：原输入28506 tokens，预留输出3000，合计31506/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 6. 22cc237_1：替换第5步
- 任务：I went on a dinner with some of my coworkers yesterday. I paid the entire bill to simplify the payment. I've made a note of individual shares in simple note. Some people have already sent me their share on venmo. Make payment requests for others with a description note "Work Dinner".
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match venmo.Notification, venmo.PaymentRequest.；assert user_id_to_share obtained from added_payment_requests matches the private_data.pending_user_id_to_share (tolerance=1.0)
- 日志证据：动作5输入7,330 tokens，下一输入立即增至23,735；动作7再次打印全集后增至28,399，最终请求29,514+3,000超过32,000。
- 暂定类别：状态错误。首次业务查询把所有含dinner的笔记和全部收款记录完整打印；此后又重复读取同一批笔记，历史在第11次请求因预留3,000输出tokens而超限。
- 修复方向：在环境内筛选昨天的工作晚餐笔记和相关付款，只返回精确笔记/付款摘要，避免两次完整列表输出。
- 固定窗口：原输入7330 tokens，预留输出3000，合计10330/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 7. c901732_2：替换第3步
- 任务：Play the most listened to song on Spotify from my Woodstock Reimagined: Festival Vibes playlist.
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match spotify.MusicPlayer.；obtain added, updated, removed spotify.MusicPlayer records using models.changed_records, and assert 1 has been updated, and 0 have been added or removed.；assert the updated music player is in playing state.；assert the updated music player's current_song is part of album/playlist with private_data.collection_id.；assert the updated music player's current_song has id matching private_data.least_or_most_played_song_id.
- 日志证据：动作3输入7,867 tokens；输出不仅有同名歌单，也含大量其他Vibes歌单，使下一请求达到62,083 tokens。
- 暂定类别：状态错误。歌单搜索接口返回宽泛结果，第3步翻完所有页面并打印数百个歌单，没有即时限定标题和目标所有者。
- 修复方向：只保留精确标题候选及歌曲ID，结合可见任务信息确定目标歌单，再查播放次数并播放最高者。
- 固定窗口：原输入7867 tokens，预留输出3000，合计10867/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

### 8. 2a163ab_3：替换第9步
- 任务：Like all the venmo transactions from yesterday or today involving any of my coworkers on my venmo social feed.
- 官方未满足条件（仅审查可见）：assert answers match.；assert model changes match venmo.Transaction, venmo.TransactionLike；assert set of all new transaction likes (obtained via models.changed_records) is identical to set of private_data.recent_relative_transaction_ids.；assert all newly liked transaction_ids are in private_data.recent_transaction_ids.；assert all newly liked transaction_ids are in private_data.relative_transaction_ids.
- 日志证据：动作9输入9,554 tokens，完整动态使下一请求达到263,599 tokens；先前401并非仍未解决的恢复失败。
- 暂定类别：状态错误。联系人401已通过登录恢复；第9步翻完并打印整个Venmo动态，没有在环境内按昨天/今天和同事邮箱过滤。
- 修复方向：在环境内按两天日期范围和同事邮箱过滤，只输出或处理目标交易ID并点赞。
- 固定窗口：原输入9554 tokens，预留输出3000，合计12554/32000，通过。
- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。

