# AppWorld 裸 Qwen3-8B test_normal 评测报告

## 一、结论

裸 Qwen3-8B 已完成 AppWorld `test_normal` 全部 168 道任务的真实 one-shot ReAct 推理与官方评分。
最终成功 12/168，TGC 为 7.1，SGC 为 0.0；基础设施与评分链路完成 168/168，最终退出码为 0。

## 二、官方指标

| 指标 | 结果 |
|---|---:|
| 成功任务 | 12/168 |
| TGC | 7.1 |
| 成功 scenario | 0/56 |
| SGC | 0.0 |
| evaluator 条件通过 | 386/1077 (35.8%) |

按难度统计：

| 难度 | 成功/总数 | TGC |
|---|---:|---:|
| 1 | 11/57 | 19.3 |
| 2 | 1/48 | 2.1 |
| 3 | 0/63 | 0.0 |

成功任务：09b0ee6_3、13547f5_1、13547f5_2、166f4ff_1、21abae1_2、29a7b7e_1、522e5e5_2、5a83b05_3、7847649_1、7847649_3、dac78d9_3、f3f60f0_3

完整成功 scenario：无

## 三、配置与可比性

- 模型：`/root/autodl-tmp/models/Qwen3-8B` 裸基座，未加载 LoRA/adapter，未修改权重。
- Agent/Prompt：官方 `simplified_react_code_agent` 与官方 one-shot ReAct prompt。
- 模型 preset：`qwen3-8b-with-reasoning`；reasoning parser：`deepseek_r1`。
- temperature=0、seed=100、单次输出上限 3000 tokens、每题最多 50 步、context 32000。
- 单 AppWorld 进程、GPU0 顺序执行；AppWorld 0.2.0.dev0 官方 evaluator。
- 上述协议与 Dev 基线 `/root/autodl-tmp/workspace-tw/experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev` 一致，仅数据集从 `dev` 改为 `test_normal`。

## 四、错误总结与接口审计

### 4.1 中文错误类别

同一题可能同时违反多个 evaluator 条件，因此下面各类别的题数不可相加后当作失败题总数。

| 错误类别 | 涉及题数 | 任务 ID |
|---|---:|---|
| 最终答案不匹配 | 90 | 024c982_1、024c982_3、042a9fc_2、0a9d82a_1、0a9d82a_2、0a9d82a_3、0d01c76_2、0de03ea_1、0de03ea_2、0de03ea_3、1150ed6_1、1150ed6_2、166f4ff_2、166f4ff_3、21abae1_1、21abae1_3、29a7b7e_2、29a7b7e_3、2c544f9_2、2c544f9_3、2d9f728_1、2d9f728_3、31dc501_1、31dc501_2、31dc501_3、325d6ec_2、32616b5_2、32616b5_3、3aa1a22_2、425a494_1、425a494_2、425a494_3、522e5e5_3、552869a_1、552869a_2、552869a_3、5a83b05_2、634f342_1、634f342_2、652485c_1、6b6ca61_2、6b6ca61_3、6f4b9a5_1、7847649_2、83a7951_1、83a7951_2、8749218_1、8749218_3、8ce6779_2、90adc3f_3、986aa4e_2、986aa4e_3、9dabbc9_2、9ef798c_1、9ef798c_2、9ef798c_3、afc4005_1、afc4005_2、afc4005_3、b6d1104_1、b6d1104_3、b9c5c9a_1、b9c5c9a_3、bde252e_1、bde252e_3、ccf4b82_1、ccf4b82_3、cef9191_1、cef9191_2、cef9191_3、d18139b_2、d18139b_3、d194965_3、d6ac34d_1、d6ac34d_2、d6ac34d_3、dac78d9_1、dac78d9_2、f323bae_1、f323bae_2、f323bae_3、f3f60f0_1、f861c32_1、f861c32_2、fd1f8fa_2、fd1f8fa_3、ff58e36_2、ffe6d5e_1、ffe6d5e_2、ffe6d5e_3 |
| 交易或购物状态错误 | 48 | 024c982_1、024c982_2、09b0ee6_1、09b0ee6_2、270f1ff_1、270f1ff_2、270f1ff_3、2c544f9_1、2c544f9_2、2c544f9_3、2d9f728_1、2d9f728_2、2d9f728_3、3aa1a22_1、3aa1a22_2、3aa1a22_3、3b8fb7a_1、3b8fb7a_2、3b8fb7a_3、59fae45_1、59fae45_2、59fae45_3、6b6ca61_1、6b6ca61_2、6b6ca61_3、83a7951_1、83a7951_2、83a7951_3、90adc3f_1、90adc3f_2、90adc3f_3、9dabbc9_1、9dabbc9_2、9dabbc9_3、9ef798c_2、9ef798c_3、ccf4b82_1、ccf4b82_2、ccf4b82_3、d18139b_1、d18139b_2、d18139b_3、f323bae_1、f323bae_2、f323bae_3、f861c32_1、f861c32_2、f861c32_3 |
| Venmo 好友、交易或付款状态错误 | 39 | 024c982_1、024c982_2、270f1ff_1、270f1ff_2、270f1ff_3、2c544f9_1、2c544f9_2、2c544f9_3、2d9f728_1、2d9f728_2、2d9f728_3、3b8fb7a_1、3b8fb7a_2、3b8fb7a_3、3d9a636_1、3d9a636_2、3d9a636_3、522e5e5_1、6b6ca61_1、6b6ca61_2、6b6ca61_3、83a7951_1、83a7951_2、83a7951_3、90adc3f_1、90adc3f_2、9dabbc9_1、9dabbc9_2、9dabbc9_3、c77c005_1、c77c005_2、c77c005_3、ccf4b82_2、ccf4b82_3、d18139b_1、d18139b_2、ff58e36_1、ff58e36_2、ff58e36_3 |
| Spotify 播放、队列或收藏状态错误 | 38 | 042a9fc_1、042a9fc_2、042a9fc_3、0de03ea_1、0de03ea_2、0de03ea_3、1150ed6_1、1150ed6_2、1150ed6_3、325d6ec_1、325d6ec_2、325d6ec_3、59fae45_1、59fae45_2、59fae45_3、634f342_1、634f342_2、634f342_3、652485c_1、652485c_2、652485c_3、6f4b9a5_1、6f4b9a5_2、6f4b9a5_3、8749218_1、8749218_2、8749218_3、986aa4e_1、986aa4e_2、986aa4e_3、d194965_1、d194965_2、d194965_3、f3f60f0_1、f3f60f0_2、fd1f8fa_1、fd1f8fa_2、fd1f8fa_3 |
| 其他业务条件未满足 | 36 | 13547f5_3、270f1ff_1、270f1ff_2、270f1ff_3、325d6ec_1、325d6ec_3、59fae45_1、59fae45_2、59fae45_3、634f342_1、634f342_2、634f342_3、652485c_1、652485c_2、652485c_3、8ce6779_1、8ce6779_2、8ce6779_3、986aa4e_1、986aa4e_3、a30375d_1、a30375d_2、a30375d_3、b9c5c9a_1、b9c5c9a_2、b9c5c9a_3、bde252e_1、bde252e_2、bde252e_3、d194965_1、d194965_2、d6ac34d_1、f323bae_3、f3f60f0_1、f3f60f0_2、ffe6d5e_3 |
| 笔记状态或内容错误 | 28 | 024c982_1、024c982_2、0d01c76_1、0d01c76_3、270f1ff_1、270f1ff_2、270f1ff_3、2d9f728_1、2d9f728_2、2d9f728_3、6f4b9a5_1、6f4b9a5_2、6f4b9a5_3、83a7951_1、83a7951_2、83a7951_3、9dabbc9_1、9dabbc9_2、9dabbc9_3、b6d1104_1、b6d1104_2、b6d1104_3、d6ac34d_1、d6ac34d_2、d6ac34d_3、f861c32_1、f861c32_2、f861c32_3 |
| 文件系统路径、目录或内容错误 | 19 | 29a7b7e_3、5a83b05_1、6b6ca61_1、6b6ca61_2、6b6ca61_3、83a7951_1、83a7951_2、83a7951_3、9ef798c_2、9ef798c_3、b9c5c9a_1、b9c5c9a_2、b9c5c9a_3、ccf4b82_1、ccf4b82_2、ccf4b82_3、f861c32_1、f861c32_2、f861c32_3 |
| 电话、消息或联系人状态错误 | 14 | 13547f5_3、270f1ff_1、270f1ff_2、270f1ff_3、3aa1a22_1、3aa1a22_2、3aa1a22_3、652485c_2、652485c_3、9016950_1、9016950_2、9016950_3、ffe6d5e_2、ffe6d5e_3 |
| Splitwise 或费用状态错误 | 12 | 32616b5_1、32616b5_2、32616b5_3、3aa1a22_1、3aa1a22_2、3aa1a22_3、6b6ca61_1、6b6ca61_2、6b6ca61_3、b6d1104_1、b6d1104_2、b6d1104_3 |
| 数据库变更不符合要求 | 8 | 3aa1a22_1、3aa1a22_2、3aa1a22_3、59fae45_1、59fae45_2、59fae45_3、f3f60f0_1、f3f60f0_2 |
| 邮件状态或内容错误 | 7 | 270f1ff_1、270f1ff_2、270f1ff_3、9016950_1、9016950_2、9016950_3、9ef798c_2 |
| 待办或项目状态错误 | 6 | 8ce6779_1、8ce6779_2、8ce6779_3、bde252e_1、bde252e_2、bde252e_3 |

### 4.2 重复出现的官方失败条件

下表保留官方 evaluator 的英文 requirement 原文，便于精确复核；仅列出现于两题及以上的前 30 项。
它能够区分“同一业务场景的相似失败”和“跨场景统一接口故障”。

| 官方 requirement | 涉及题数 | 任务 ID |
|---|---:|---|
| assert answers match. | 90 | 024c982_1、024c982_3、042a9fc_2、0a9d82a_1、0a9d82a_2、0a9d82a_3、0d01c76_2、0de03ea_1、0de03ea_2、0de03ea_3、1150ed6_1、1150ed6_2、166f4ff_2、166f4ff_3、21abae1_1、21abae1_3、29a7b7e_2、29a7b7e_3、2c544f9_2、2c544f9_3、2d9f728_1、2d9f728_3、31dc501_1、31dc501_2、31dc501_3、325d6ec_2、32616b5_2、32616b5_3、3aa1a22_2、425a494_1、425a494_2、425a494_3、522e5e5_3、552869a_1、552869a_2、552869a_3、5a83b05_2、634f342_1、634f342_2、652485c_1、6b6ca61_2、6b6ca61_3、6f4b9a5_1、7847649_2、83a7951_1、83a7951_2、8749218_1、8749218_3、8ce6779_2、90adc3f_3、986aa4e_2、986aa4e_3、9dabbc9_2、9ef798c_1、9ef798c_2、9ef798c_3、afc4005_1、afc4005_2、afc4005_3、b6d1104_1、b6d1104_3、b9c5c9a_1、b9c5c9a_3、bde252e_1、bde252e_3、ccf4b82_1、ccf4b82_3、cef9191_1、cef9191_2、cef9191_3、d18139b_2、d18139b_3、d194965_3、d6ac34d_1、d6ac34d_2、d6ac34d_3、dac78d9_1、dac78d9_2、f323bae_1、f323bae_2、f323bae_3、f3f60f0_1、f861c32_1、f861c32_2、fd1f8fa_2、fd1f8fa_3、ff58e36_2、ffe6d5e_1、ffe6d5e_2、ffe6d5e_3 |
| assert model changes match spotify.MusicPlayer. | 13 | 0de03ea_1、0de03ea_2、0de03ea_3、1150ed6_1、1150ed6_2、1150ed6_3、325d6ec_1、325d6ec_3、8749218_1、8749218_2、8749218_3、fd1f8fa_1、fd1f8fa_3 |
| assert model changes match simple_note.Note. | 7 | 0d01c76_1、0d01c76_3、6f4b9a5_1、6f4b9a5_2、6f4b9a5_3、b6d1104_2、b6d1104_3 |
| assert model changes match spotify.Playlist, spotify.PlaylistSong. | 6 | 634f342_1、634f342_2、634f342_3、d194965_1、d194965_2、d194965_3 |
| assert the updated music player is in the playing state. | 6 | 1150ed6_1、1150ed6_2、1150ed6_3、8749218_1、8749218_2、8749218_3 |
| obtain added, updated, removed venmo.Transaction records using models.changed_records, and assert 1 was added, 0 were updated or removed. | 6 | 2c544f9_1、2c544f9_2、2c544f9_3、9dabbc9_1、9dabbc9_2、9dabbc9_3 |
| assert model changes match file_system.File. | 5 | 29a7b7e_3、5a83b05_1、b9c5c9a_1、b9c5c9a_2、b9c5c9a_3 |
| assert model changes match venmo.Friendship | 5 | 3d9a636_3、522e5e5_1、ff58e36_1、ff58e36_2、ff58e36_3 |
| assert model changes match venmo.Notification, venmo.PaymentRequest | 4 | 024c982_1、024c982_2、90adc3f_1、90adc3f_2 |
| obtain added, updated, removed spotify.MusicPlayer records using models.changed_records, and assert 1 has been updated, and 0 have been added or removed. | 4 | 325d6ec_1、325d6ec_3、fd1f8fa_1、fd1f8fa_3 |
| assert 1 file_system.File record was updated. | 3 | b9c5c9a_1、b9c5c9a_2、b9c5c9a_3 |
| assert The note's content starts with "# Venmo Expenses". | 3 | b6d1104_1、b6d1104_2、b6d1104_3 |
| assert added and removed song ids have playlist_id = private_data.playlist_id | 3 | 042a9fc_1、042a9fc_2、042a9fc_3 |
| assert added_payment_requests have amount private_data.dinner_share +/- public_data.difference_amount as per public_data.less_more (round_to=0) | 3 | 90adc3f_1、90adc3f_2、90adc3f_3 |
| assert added_payment_requests have description private_data.dinner_description (normalize_text=True) | 3 | 90adc3f_1、90adc3f_2、90adc3f_3 |
| assert all added payment requests have amount public_data.taxi_cost / (1 + number of roommates) with a tolerance of 0.51. | 3 | 2d9f728_1、2d9f728_2、2d9f728_3 |
| assert all added payment requests have description public_data.taxi_note (normalize_text=True). | 3 | 2d9f728_1、2d9f728_2、2d9f728_3 |
| assert all added payments have description public_data.note (normalize_text=True). | 3 | 83a7951_1、83a7951_2、83a7951_3 |
| assert all added playlist_songs' song_ids match private_data.suggested_add_song_ids (ignoring order). | 3 | 986aa4e_1、986aa4e_2、986aa4e_3 |
| assert all added tasks have the same priority as private_data.priority | 3 | bde252e_1、bde252e_2、bde252e_3 |
| assert all main_user's friends on venmo match private_data.all_friends_venmo_user_ids in the end state (ignore_order) | 3 | 3d9a636_1、3d9a636_2、3d9a636_3 |
| assert all of added friend ids are in private_data.to_befriend_venmo_user_ids. | 3 | ff58e36_1、ff58e36_2、ff58e36_3 |
| assert all of private_data.to_befriend_venmo_user_ids_1 are in newly_befriended_venmo_user_ids. | 3 | ff58e36_1、ff58e36_2、ff58e36_3 |
| assert all of private_data.to_befriend_venmo_user_ids_2 are in newly_befriended_venmo_user_ids. | 3 | ff58e36_1、ff58e36_2、ff58e36_3 |
| assert all song_ids in private_data.downloaded_song_ids are in queue_song_ids from music player in the end state. | 3 | 0de03ea_1、0de03ea_2、0de03ea_3 |
| assert all the added_transactions are private/public based on public_data.privacy. | 3 | 6b6ca61_1、6b6ca61_2、6b6ca61_3 |
| assert all the removed playlist_songs' song_ids match the private_data.suggested_delete_song_ids. | 3 | 986aa4e_1、986aa4e_2、986aa4e_3 |
| assert all these transactions have amount public_data.payment_amount | 3 | f861c32_1、f861c32_2、f861c32_3 |
| assert all these transactions have note public_data.note. | 3 | f861c32_1、f861c32_2、f861c32_3 |
| assert all transactions have description "For {data.public.vacation_spot} trip" (normalize_text=True) | 3 | 3b8fb7a_1、3b8fb7a_2、3b8fb7a_3 |

### 4.3 模型—AppWorld 接口健康检查

结论：**响应格式风险告警已触发：无法解释的空响应、空 content 或日志格式异常跨 3 个 scenario；但仅有 3/2859 次 LM 调用（0.105%）命中，呈低频孤立分布，需要复核，但不足以解释主体失败；主要失败仍来自业务状态、最终答案和代理执行/终止策略。**

| 接口信号 | 次数/题数 |
|---|---:|
| `message.content=null` | 80 次，45 题 |
| 其中纯 reasoning 长度截断 | 80 次，45 题 |
| 无法由长度截断解释的 `content=null` | 0 次，0 题 |
| `finish_reason=length` | 110 次，58 题 |
| 空 `message.content` | 3 次，3 题 |
| 无法解析的 LM 日志行 | 0 次，0 题 |
| `No code available to execute` | 1025 次，76 题 |
| 含 `complete_task` action | 144 题 |
| 含 Python 执行错误 | 143 题 |
| 达到 50 步上限 | 23 题 |

### 4.4 逐题官方结果与错误信号

“正确/错误”直接来自 AppWorld 官方 evaluator；“条件通过”是该题通过的 evaluator 条件数/条件总数。

| 任务 ID | 官方结果 | 条件通过 | 中文错误类别 | 接口/执行信号 |
|---|---|---:|---|---|
| 3d9a636_1 | 错误 | 2/5 | Venmo 好友、交易或付款状态错误 | Python执行错误 |
| 3d9a636_2 | 错误 | 2/5 | Venmo 好友、交易或付款状态错误 | Python执行错误 |
| 3d9a636_3 | 错误 | 1/5 | Venmo 好友、交易或付款状态错误 | 正常 |
| fd1f8fa_1 | 错误 | 1/5 | Spotify 播放、队列或收藏状态错误 | Python执行错误 |
| fd1f8fa_2 | 错误 | 3/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 无可执行代码×46；Python执行错误；达到50步上限；未调用complete_task |
| fd1f8fa_3 | 错误 | 0/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | Python执行错误 |
| 325d6ec_1 | 错误 | 1/5 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足 | 正常 |
| 325d6ec_2 | 错误 | 3/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 其他长度截断×1；无可执行代码×18；Python执行错误；达到50步上限；未调用complete_task |
| 325d6ec_3 | 错误 | 1/5 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足 | 正常 |
| 29a7b7e_1 | 正确 | 4/4 | — | 无可执行代码×2；Python执行错误 |
| 29a7b7e_2 | 错误 | 3/4 | 最终答案不匹配 | 纯reasoning截断×14；其他长度截断×1；无可执行代码×15；Python执行错误 |
| 29a7b7e_3 | 错误 | 1/4 | 文件系统路径、目录或内容错误；最终答案不匹配 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| 21abae1_1 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| 21abae1_2 | 正确 | 2/2 | — | 正常 |
| 21abae1_3 | 错误 | 1/2 | 最终答案不匹配 | 无可执行代码×36；Python执行错误；达到50步上限；未调用complete_task |
| 634f342_1 | 错误 | 0/7 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；最终答案不匹配 | content为空×1；Python执行错误 |
| 634f342_2 | 错误 | 0/7 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；最终答案不匹配 | 无可执行代码×50；达到50步上限；未调用complete_task |
| 634f342_3 | 错误 | 1/7 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足 | Python执行错误 |
| 8749218_1 | 错误 | 1/6 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | Python执行错误 |
| 8749218_2 | 错误 | 2/6 | Spotify 播放、队列或收藏状态错误 | 正常 |
| 8749218_3 | 错误 | 1/6 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | Python执行错误 |
| 2d9f728_1 | 错误 | 1/10 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×1；其他长度截断×1；无可执行代码×4；Python执行错误 |
| 2d9f728_2 | 错误 | 2/10 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；笔记状态或内容错误 | 纯reasoning截断×3；其他长度截断×1；无可执行代码×4；Python执行错误 |
| 2d9f728_3 | 错误 | 4/10 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×3；其他长度截断×1；无可执行代码×31；Python执行错误；达到50步上限；未调用complete_task |
| 6f4b9a5_1 | 错误 | 1/8 | Spotify 播放、队列或收藏状态错误；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×2；无可执行代码×44；Python执行错误；达到50步上限；未调用complete_task |
| 6f4b9a5_2 | 错误 | 2/8 | Spotify 播放、队列或收藏状态错误；笔记状态或内容错误 | Python执行错误 |
| 6f4b9a5_3 | 错误 | 2/8 | Spotify 播放、队列或收藏状态错误；笔记状态或内容错误 | 正常 |
| d6ac34d_1 | 错误 | 3/9 | 其他业务条件未满足；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| d6ac34d_2 | 错误 | 7/9 | 最终答案不匹配；笔记状态或内容错误 | Python执行错误 |
| d6ac34d_3 | 错误 | 7/9 | 最终答案不匹配；笔记状态或内容错误 | 正常 |
| 0d01c76_1 | 错误 | 2/6 | 笔记状态或内容错误 | Python执行错误 |
| 0d01c76_2 | 错误 | 5/6 | 最终答案不匹配 | Python执行错误 |
| 0d01c76_3 | 错误 | 2/6 | 笔记状态或内容错误 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| ff58e36_1 | 错误 | 2/6 | Venmo 好友、交易或付款状态错误 | Python执行错误 |
| ff58e36_2 | 错误 | 1/6 | Venmo 好友、交易或付款状态错误；最终答案不匹配 | 其他长度截断×1；Python执行错误 |
| ff58e36_3 | 错误 | 2/6 | Venmo 好友、交易或付款状态错误 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| d18139b_1 | 错误 | 2/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | Python执行错误 |
| d18139b_2 | 错误 | 1/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配 | 其他长度截断×1；content为空×1；Python执行错误；未调用complete_task |
| d18139b_3 | 错误 | 5/7 | 交易或购物状态错误；最终答案不匹配 | Python执行错误 |
| 5a83b05_1 | 错误 | 1/3 | 文件系统路径、目录或内容错误 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| 5a83b05_2 | 错误 | 2/3 | 最终答案不匹配 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| 5a83b05_3 | 正确 | 3/3 | — | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| 042a9fc_1 | 错误 | 1/5 | Spotify 播放、队列或收藏状态错误 | Python执行错误 |
| 042a9fc_2 | 错误 | 0/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 纯reasoning截断×1；无可执行代码×36；Python执行错误；达到50步上限；未调用complete_task |
| 042a9fc_3 | 错误 | 1/5 | Spotify 播放、队列或收藏状态错误 | Python执行错误 |
| cef9191_1 | 错误 | 1/2 | 最终答案不匹配 | 其他长度截断×1 |
| cef9191_2 | 错误 | 1/2 | 最终答案不匹配 | 正常 |
| cef9191_3 | 错误 | 1/2 | 最终答案不匹配 | 纯reasoning截断×1；无可执行代码×1 |
| 3b8fb7a_1 | 错误 | 3/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | Python执行错误 |
| 3b8fb7a_2 | 错误 | 3/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | 纯reasoning截断×1；无可执行代码×3；Python执行错误 |
| 3b8fb7a_3 | 错误 | 3/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| afc4005_1 | 错误 | 1/2 | 最终答案不匹配 | 无可执行代码×11；Python执行错误 |
| afc4005_2 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| afc4005_3 | 错误 | 1/2 | 最终答案不匹配 | 无可执行代码×3；Python执行错误 |
| 9dabbc9_1 | 错误 | 1/9 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；笔记状态或内容错误 | 纯reasoning截断×1；其他长度截断×1；无可执行代码×1；Python执行错误 |
| 9dabbc9_2 | 错误 | 2/9 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| 9dabbc9_3 | 错误 | 1/9 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；笔记状态或内容错误 | 纯reasoning截断×2；无可执行代码×2 |
| 425a494_1 | 错误 | 1/2 | 最终答案不匹配 | 纯reasoning截断×1；无可执行代码×1 |
| 425a494_2 | 错误 | 1/2 | 最终答案不匹配 | 正常 |
| 425a494_3 | 错误 | 1/2 | 最终答案不匹配 | 正常 |
| a30375d_1 | 错误 | 1/3 | 其他业务条件未满足 | 无可执行代码×6；Python执行错误 |
| a30375d_2 | 错误 | 1/3 | 其他业务条件未满足 | 无可执行代码×3；Python执行错误 |
| a30375d_3 | 错误 | 1/3 | 其他业务条件未满足 | 无可执行代码×7；Python执行错误 |
| 09b0ee6_1 | 错误 | 1/2 | 交易或购物状态错误 | 无可执行代码×47；Python执行错误；达到50步上限；未调用complete_task |
| 09b0ee6_2 | 错误 | 1/2 | 交易或购物状态错误 | 纯reasoning截断×2；其他长度截断×1；无可执行代码×19；Python执行错误 |
| 09b0ee6_3 | 正确 | 2/2 | — | 其他长度截断×1；无可执行代码×1；Python执行错误 |
| d194965_1 | 错误 | 2/6 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足 | 正常 |
| d194965_2 | 错误 | 2/6 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足 | 正常 |
| d194965_3 | 错误 | 3/6 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | Python执行错误 |
| 7847649_1 | 正确 | 2/2 | — | 无可执行代码×1；Python执行错误 |
| 7847649_2 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| 7847649_3 | 正确 | 2/2 | — | Python执行错误 |
| 552869a_1 | 错误 | 1/2 | 最终答案不匹配 | 无可执行代码×1；Python执行错误 |
| 552869a_2 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| 552869a_3 | 错误 | 1/2 | 最终答案不匹配 | 无可执行代码×1；Python执行错误 |
| 652485c_1 | 错误 | 5/11 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；最终答案不匹配 | 纯reasoning截断×1；其他长度截断×1；无可执行代码×2；Python执行错误 |
| 652485c_2 | 错误 | 3/11 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；电话、消息或联系人状态错误 | Python执行错误 |
| 652485c_3 | 错误 | 3/11 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；电话、消息或联系人状态错误 | Python执行错误 |
| ccf4b82_1 | 错误 | 6/11 | 交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配 | Python执行错误 |
| ccf4b82_2 | 错误 | 5/11 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| ccf4b82_3 | 错误 | 2/11 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配 | 纯reasoning截断×2；其他长度截断×1；无可执行代码×18；Python执行错误；达到50步上限；未调用complete_task |
| 522e5e5_1 | 错误 | 2/4 | Venmo 好友、交易或付款状态错误 | 无可执行代码×1；Python执行错误 |
| 522e5e5_2 | 正确 | 4/4 | — | Python执行错误 |
| 522e5e5_3 | 错误 | 3/4 | 最终答案不匹配 | 纯reasoning截断×1；无可执行代码×42；Python执行错误；达到50步上限；未调用complete_task |
| 0de03ea_1 | 错误 | 2/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 其他长度截断×1；无可执行代码×2；Python执行错误 |
| 0de03ea_2 | 错误 | 2/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 正常 |
| 0de03ea_3 | 错误 | 2/5 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 无可执行代码×49；达到50步上限；未调用complete_task |
| 2c544f9_1 | 错误 | 2/6 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | Python执行错误 |
| 2c544f9_2 | 错误 | 1/6 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| 2c544f9_3 | 错误 | 1/6 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配 | Python执行错误 |
| 270f1ff_1 | 错误 | 1/11 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；其他业务条件未满足；电话、消息或联系人状态错误；笔记状态或内容错误；邮件状态或内容错误 | Python执行错误 |
| 270f1ff_2 | 错误 | 1/11 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；其他业务条件未满足；电话、消息或联系人状态错误；笔记状态或内容错误；邮件状态或内容错误 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| 270f1ff_3 | 错误 | 1/11 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；其他业务条件未满足；电话、消息或联系人状态错误；笔记状态或内容错误；邮件状态或内容错误 | 纯reasoning截断×1；无可执行代码×6；Python执行错误 |
| 024c982_1 | 错误 | 0/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；最终答案不匹配；笔记状态或内容错误 | Python执行错误 |
| 024c982_2 | 错误 | 1/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；笔记状态或内容错误 | Python执行错误 |
| 024c982_3 | 错误 | 6/7 | 最终答案不匹配 | Python执行错误 |
| 9ef798c_1 | 错误 | 5/6 | 最终答案不匹配 | Python执行错误 |
| 9ef798c_2 | 错误 | 0/6 | 交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配；邮件状态或内容错误 | 正常 |
| 9ef798c_3 | 错误 | 3/6 | 交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配 | Python执行错误 |
| b9c5c9a_1 | 错误 | 1/7 | 其他业务条件未满足；文件系统路径、目录或内容错误；最终答案不匹配 | Python执行错误 |
| b9c5c9a_2 | 错误 | 2/7 | 其他业务条件未满足；文件系统路径、目录或内容错误 | Python执行错误 |
| b9c5c9a_3 | 错误 | 1/7 | 其他业务条件未满足；文件系统路径、目录或内容错误；最终答案不匹配 | Python执行错误 |
| 90adc3f_1 | 错误 | 2/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | Python执行错误 |
| 90adc3f_2 | 错误 | 2/7 | Venmo 好友、交易或付款状态错误；交易或购物状态错误 | Python执行错误 |
| 90adc3f_3 | 错误 | 2/7 | 交易或购物状态错误；最终答案不匹配 | Python执行错误 |
| c77c005_1 | 错误 | 2/5 | Venmo 好友、交易或付款状态错误 | 其他长度截断×1；Python执行错误 |
| c77c005_2 | 错误 | 3/5 | Venmo 好友、交易或付款状态错误 | Python执行错误 |
| c77c005_3 | 错误 | 3/5 | Venmo 好友、交易或付款状态错误 | Python执行错误 |
| f323bae_1 | 错误 | 3/9 | 交易或购物状态错误；最终答案不匹配 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| f323bae_2 | 错误 | 3/9 | 交易或购物状态错误；最终答案不匹配 | Python执行错误 |
| f323bae_3 | 错误 | 2/9 | 交易或购物状态错误；其他业务条件未满足；最终答案不匹配 | 其他长度截断×1；无可执行代码×2；Python执行错误 |
| 13547f5_1 | 正确 | 6/6 | — | Python执行错误 |
| 13547f5_2 | 正确 | 6/6 | — | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| 13547f5_3 | 错误 | 2/6 | 其他业务条件未满足；电话、消息或联系人状态错误 | Python执行错误 |
| 1150ed6_1 | 错误 | 0/6 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 无可执行代码×42；Python执行错误；达到50步上限；未调用complete_task |
| 1150ed6_2 | 错误 | 0/6 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 无可执行代码×43；Python执行错误；达到50步上限；未调用complete_task |
| 1150ed6_3 | 错误 | 1/6 | Spotify 播放、队列或收藏状态错误 | 其他长度截断×1；Python执行错误 |
| 31dc501_1 | 错误 | 5/6 | 最终答案不匹配 | 无可执行代码×44；Python执行错误；达到50步上限；未调用complete_task |
| 31dc501_2 | 错误 | 5/6 | 最终答案不匹配 | Python执行错误 |
| 31dc501_3 | 错误 | 5/6 | 最终答案不匹配 | 无可执行代码×44；Python执行错误；达到50步上限；未调用complete_task |
| 59fae45_1 | 错误 | 2/6 | Spotify 播放、队列或收藏状态错误；交易或购物状态错误；其他业务条件未满足；数据库变更不符合要求 | 其他长度截断×1；Python执行错误 |
| 59fae45_2 | 错误 | 2/6 | Spotify 播放、队列或收藏状态错误；交易或购物状态错误；其他业务条件未满足；数据库变更不符合要求 | 正常 |
| 59fae45_3 | 错误 | 2/6 | Spotify 播放、队列或收藏状态错误；交易或购物状态错误；其他业务条件未满足；数据库变更不符合要求 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| b6d1104_1 | 错误 | 3/10 | Splitwise 或费用状态错误；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×1；其他长度截断×2；无可执行代码×2；Python执行错误 |
| b6d1104_2 | 错误 | 1/10 | Splitwise 或费用状态错误；笔记状态或内容错误 | 纯reasoning截断×1；其他长度截断×1；无可执行代码×1；Python执行错误 |
| b6d1104_3 | 错误 | 0/10 | Splitwise 或费用状态错误；最终答案不匹配；笔记状态或内容错误 | 无可执行代码×41；Python执行错误；达到50步上限；未调用complete_task |
| f861c32_1 | 错误 | 2/8 | 交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配；笔记状态或内容错误 | 无可执行代码×42；Python执行错误；达到50步上限 |
| f861c32_2 | 错误 | 2/8 | 交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配；笔记状态或内容错误 | Python执行错误 |
| f861c32_3 | 错误 | 3/8 | 交易或购物状态错误；文件系统路径、目录或内容错误；笔记状态或内容错误 | Python执行错误 |
| 0a9d82a_1 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| 0a9d82a_2 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| 0a9d82a_3 | 错误 | 1/2 | 最终答案不匹配 | 正常 |
| 166f4ff_1 | 正确 | 2/2 | — | 纯reasoning截断×3；其他长度截断×2；无可执行代码×3；Python执行错误 |
| 166f4ff_2 | 错误 | 1/2 | 最终答案不匹配 | 无可执行代码×28；Python执行错误 |
| 166f4ff_3 | 错误 | 1/2 | 最终答案不匹配 | Python执行错误 |
| 9016950_1 | 错误 | 3/7 | 电话、消息或联系人状态错误；邮件状态或内容错误 | Python执行错误 |
| 9016950_2 | 错误 | 4/7 | 电话、消息或联系人状态错误；邮件状态或内容错误 | Python执行错误 |
| 9016950_3 | 错误 | 3/7 | 电话、消息或联系人状态错误；邮件状态或内容错误 | 纯reasoning截断×2；无可执行代码×2；Python执行错误 |
| dac78d9_1 | 错误 | 1/2 | 最终答案不匹配 | 其他长度截断×1；Python执行错误 |
| dac78d9_2 | 错误 | 1/2 | 最终答案不匹配 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| dac78d9_3 | 正确 | 2/2 | — | 正常 |
| f3f60f0_1 | 错误 | 2/8 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；数据库变更不符合要求；最终答案不匹配 | Python执行错误；达到50步上限；未调用complete_task |
| f3f60f0_2 | 错误 | 3/8 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；数据库变更不符合要求 | 纯reasoning截断×1；无可执行代码×1 |
| f3f60f0_3 | 正确 | 8/8 | — | 无可执行代码×22 |
| ffe6d5e_1 | 错误 | 7/8 | 最终答案不匹配 | Python执行错误 |
| ffe6d5e_2 | 错误 | 6/8 | 最终答案不匹配；电话、消息或联系人状态错误 | Python执行错误 |
| ffe6d5e_3 | 错误 | 1/8 | 其他业务条件未满足；最终答案不匹配；电话、消息或联系人状态错误 | 纯reasoning截断×1；无可执行代码×45；Python执行错误；达到50步上限；未调用complete_task |
| 8ce6779_1 | 错误 | 3/9 | 其他业务条件未满足；待办或项目状态错误 | Python执行错误 |
| 8ce6779_2 | 错误 | 2/9 | 其他业务条件未满足；待办或项目状态错误；最终答案不匹配 | Python执行错误 |
| 8ce6779_3 | 错误 | 3/9 | 其他业务条件未满足；待办或项目状态错误 | 纯reasoning截断×1；其他长度截断×1；无可执行代码×1；Python执行错误 |
| 83a7951_1 | 错误 | 3/10 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配；笔记状态或内容错误 | 其他长度截断×1；无可执行代码×4；Python执行错误 |
| 83a7951_2 | 错误 | 3/10 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配；笔记状态或内容错误 | 纯reasoning截断×3；其他长度截断×1；content为空×1；无可执行代码×4；Python执行错误；未调用complete_task |
| 83a7951_3 | 错误 | 4/10 | Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误；笔记状态或内容错误 | Python执行错误 |
| 3aa1a22_1 | 错误 | 3/7 | Splitwise 或费用状态错误；交易或购物状态错误；数据库变更不符合要求；电话、消息或联系人状态错误 | 纯reasoning截断×1；其他长度截断×1；无可执行代码×2；Python执行错误 |
| 3aa1a22_2 | 错误 | 2/7 | Splitwise 或费用状态错误；交易或购物状态错误；数据库变更不符合要求；最终答案不匹配；电话、消息或联系人状态错误 | 纯reasoning截断×2；其他长度截断×1；无可执行代码×35；Python执行错误；达到50步上限；未调用complete_task |
| 3aa1a22_3 | 错误 | 3/7 | Splitwise 或费用状态错误；交易或购物状态错误；数据库变更不符合要求；电话、消息或联系人状态错误 | 其他长度截断×1；Python执行错误 |
| 32616b5_1 | 错误 | 4/10 | Splitwise 或费用状态错误 | Python执行错误 |
| 32616b5_2 | 错误 | 3/10 | Splitwise 或费用状态错误；最终答案不匹配 | 无可执行代码×32；Python执行错误；达到50步上限；未调用complete_task |
| 32616b5_3 | 错误 | 3/10 | Splitwise 或费用状态错误；最终答案不匹配 | 无可执行代码×36；Python执行错误；达到50步上限；未调用complete_task |
| 986aa4e_1 | 错误 | 3/10 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足 | Python执行错误 |
| 986aa4e_2 | 错误 | 5/10 | Spotify 播放、队列或收藏状态错误；最终答案不匹配 | 纯reasoning截断×1；无可执行代码×7；Python执行错误 |
| 986aa4e_3 | 错误 | 2/10 | Spotify 播放、队列或收藏状态错误；其他业务条件未满足；最终答案不匹配 | Python执行错误 |
| 6b6ca61_1 | 错误 | 8/19 | Splitwise 或费用状态错误；Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误 | Python执行错误 |
| 6b6ca61_2 | 错误 | 7/19 | Splitwise 或费用状态错误；Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配 | Python执行错误 |
| 6b6ca61_3 | 错误 | 8/19 | Splitwise 或费用状态错误；Venmo 好友、交易或付款状态错误；交易或购物状态错误；文件系统路径、目录或内容错误；最终答案不匹配 | 无可执行代码×2；Python执行错误 |
| bde252e_1 | 错误 | 0/9 | 其他业务条件未满足；待办或项目状态错误；最终答案不匹配 | 纯reasoning截断×2；无可执行代码×2；Python执行错误；达到50步上限；未调用complete_task |
| bde252e_2 | 错误 | 1/9 | 其他业务条件未满足；待办或项目状态错误 | 纯reasoning截断×1；无可执行代码×1；Python执行错误 |
| bde252e_3 | 错误 | 0/9 | 其他业务条件未满足；待办或项目状态错误；最终答案不匹配 | Python执行错误 |

## 五、运行完整性与成本

| 检查项 | 结果 |
|---|---:|
| 任务输出与 finished | 168/168 |
| 官方逐题 evaluation | 168/168 |
| LM 调用 | 2859 |
| AppWorld API 调用 | 6926 |
| 输入 tokens | 22327946 |
| 输出 tokens | 2597327 |
| 总 tokens | 24925273 |
| 含 Python 执行错误的任务 | 143 |
| 含无可执行代码响应的任务 | 76 |
| 达到 50 次 LM 调用的任务 | 23 |
| 墙钟时间 | 9 小时 57 分 10 秒 |
| 实验目录实际文件大小 | 754.81 MiB |

## 六、产物

- `REPORT.md`：本报告。
- `summary.json`：机器可读指标与运行统计。
- `task_status.jsonl`：168 道任务的完成、评分和调用计数。
- `manifest.json`：模型、数据哈希与冻结推理协议。
- `INTERFACE_AUDIT.md`：运行期间持续更新的逐题官方评分与接口审计。
- `live_summary.json`、`live_task_status.jsonl`：运行期间的即时机器可读评分和逐题记录。
- `experiments/outputs/.../evaluations/test_normal.json`：AppWorld 官方聚合及逐题评分。
- `experiments/outputs/.../tasks/`：逐题 LM、环境、API、数据库与 evaluator 产物。
- `logs/run.log`：完整运行日志。
- `scripts_snapshot/`：本次实际使用的脚本快照。
