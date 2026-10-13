# v4 逐步评分复核

以下为模型原始标签与短依据，仅整理排版。官方成败仅供事后复核，未发送给 judge。

P=通过，F=违反，U=证据不足，N=不适用；八维没有权重，不合成总分。

R1 执行契约；R2 证据与覆盖；R3 状态与数据保真；R4 决策与计算；R5 操作与实际效果；R6 反馈与恢复；R7 结束与交付；R8 授权与交互协议。

## 八条回归样本

### 302c169_2__02（官方结果：成功）

I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/302c169_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/302c169_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未先查规格且缺少访问令牌，读取以401失败。 |
| 2 | F | N | N | N | N | F | N | F | 未查规格便调用不存在的接口，恢复失败。 |
| 3 | P | P | P | N | N | P | N | F | 未先查看 show_account_passwords 的接口规格。 |
| 4 | F | N | N | N | N | P | N | F | 未查登录规格且误用邮箱，认证以401失败。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | F | 未先查看 show_alarms 的接口规格。 |
| 8 | P | P | P | P | N | N | N | P |  |
| 9 | P | P | P | P | N | N | N | P |  |
| 10 | P | P | P | P | P | N | N | F | 未先查看 update_alarm 的接口规格。 |
| 11 | P | N | P | N | N | N | P | F | 未先查看 complete_task 的接口规格。 |

### 302c169_3__03（官方结果：失败）

I am going on a vacation. Move my go-to-sleep phone alarm to 20 minutes later and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/302c169_3__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/302c169_3__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | F | N | N | N | N | N | N | F | 未查接口规格且缺少令牌，调用返回401。 |
| 3 | P | P | N | N | N | P | N | P |  |
| 4 | P | P | N | N | N | P | N | F | 调用凭据接口前未查看其完整规格。 |
| 5 | F | N | N | N | N | P | N | P | 错误下标访问布尔值，登录未执行。 |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | N | N | N | P | N | F | 调用show_alarms前未查看其完整规格。 |
| 8 | P | F | F | F | N | N | N | P | 将启用的“Wake Up”无依据认作睡眠闹钟。 |
| 9 | P | F | F | F | F | N | N | F | 未查更新规格，并修改了错误识别的闹钟。 |
| 10 | P | F | F | N | N | N | F | F | 其余闹钟未执行禁用，却宣称完成且未查完成接口规格。 |

### cf6abd2_2__01（官方结果：成功）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/cf6abd2_2__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/cf6abd2_2__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | F | F | N | N | N | P | 将清单项误当成名为该项的独立笔记。 |
| 2 | P | P | P | N | N | N | N | P |  |
| 3 | F | N | P | N | N | N | N | F | 未查search_notes规格且缺少令牌，调用返回401。 |
| 4 | F | N | P | N | N | P | N | F | 未查登录规格且缺少必填参数，调用返回422。 |
| 5 | P | P | P | N | N | P | N | F | 调用前未查show_account_passwords完整规格。 |
| 6 | F | N | P | N | N | F | N | F | 猜测不存在的API，未取得用户名且未查规格。 |
| 7 | F | N | F | N | N | F | N | F | 继续猜测不存在的API，且无新恢复信息。 |
| 8 | P | P | F | N | N | P | N | F | 笼统声称无账户信息API，且未查show_profile规格。 |
| 9 | P | N | U | N | N | P | N | F | 未查登录规格，且无证据即把个人邮箱当作用户名。 |
| 10 | P | P | P | N | N | N | N | F | 未查search_notes规格，且未按协议遍历分页。 |
| 11 | P | P | P | N | N | P | N | F | 未查search_notes规格，且未按协议遍历分页。 |
| 12 | P | P | P | N | N | F | N | F | 无新信息仍重复同一查询，且未查规格或分页。 |
| 13 | P | P | P | N | N | P | N | F | 未查search_notes规格，且未按协议遍历分页。 |
| 14 | P | P | P | N | N | F | N | F | 已有目标笔记ID仍重复查询，且未查规格或分页。 |
| 15 | P | P | P | N | N | P | N | F | 调用show_note前未查看完整接口规格。 |
| 16 | P | P | P | P | P | N | N | F | 调用update_note前未查看完整接口规格。 |
| 17 | P | N | P | N | N | N | P | F | 调用complete_task前未查看完整接口规格。 |

### cf6abd2_2__02（官方结果：失败）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/cf6abd2_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/cf6abd2_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在的接口导致异常，且事前未查完整规格。 |
| 2 | P | P | P | N | N | P | N | P |  |
| 3 | F | N | N | N | N | P | N | F | 搜索因缺少认证失败，且事前未查完整规格。 |
| 4 | P | P | P | N | N | F | N | P | 重复查询已知的API列表，未利用已显示的login信息。 |
| 5 | F | N | P | N | N | P | N | F | 引用未定义passwords导致异常，且未查登录规格。 |
| 6 | F | P | P | N | N | P | N | F | 密码筛选产生布尔值后被下标，且未查接口规格。 |
| 7 | P | P | P | N | N | P | N | F | 未查看凭据接口完整规格即重复调用。 |
| 8 | P | N | P | N | N | P | N | F | 未查看simple_note.login完整规格即调用。 |
| 9 | P | P | P | N | N | P | N | F | 未查搜索接口完整规格，且未按协议遍历分页。 |
| 10 | P | P | U | N | N | N | N | F | 读取前断言目标项在该笔记中证据不足，且未查规格。 |
| 11 | P | P | F | P | P | N | N | F | 将[x]误述为未完成，且调用更新接口前未查规格。 |
| 12 | F | N | P | N | N | N | F | F | 空代码触发终止，且未调用规定的complete_task。 |

### e7a10f8_3__02（官方结果：成功）

How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/e7a10f8_3__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/e7a10f8_3__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | N | F | N | N | N | N | F | 捏造并使用fake_access_token，违反凭据获取要求。 |
| 2 | F | N | F | N | N | N | N | F | 以捏造令牌调用接口，返回401且未取得播放列表。 |
| 3 | F | N | P | N | N | F | N | F | 未查规格即调用不存在的接口，未能恢复认证。 |
| 4 | P | P | P | N | N | P | N | F | 调用show_account_passwords前未查看接口规格。 |
| 5 | P | P | P | N | N | N | N | P |  |
| 6 | F | N | P | F | N | N | N | F | 未查接口规格，误用song_ids并假设每首3分钟。 |
| 7 | P | P | P | N | N | P | N | P |  |
| 8 | P | P | P | P | N | P | N | P |  |
| 9 | P | P | P | P | N | N | P | F | 调用complete_task前未查看接口规格。 |

### e7a10f8_3__04（官方结果：失败）

How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/e7a10f8_3__04/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/e7a10f8_3__04/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | F | N | N | N | F | 调用不存在接口且未查规格，并预设3分钟均长。 |
| 2 | P | P | P | N | N | P | N | F | 未先查询show_account_passwords的完整接口规格。 |
| 3 | P | P | P | N | N | N | N | P |  |
| 4 | P | U | P | N | N | N | N | F | 仅取默认5条且未分页，无法证明覆盖全部歌单。 |
| 5 | P | U | P | F | N | N | N | N | 覆盖范围未明，且用歌曲数代替总时长判定最长。 |
| 6 | P | F | F | F | N | N | N | F | 无歌曲时长证据，猜测均长并据此计算答案。 |
| 7 | P | N | F | N | N | N | F | F | 提交了无充分依据的24，且未查询完成接口规格。 |

### 76f2c72_1__03（官方结果：成功）

What is the total cost of my electricity bills for this year? The bills are in "~/bills/" directory of my file system.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/76f2c72_1__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/76f2c72_1__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | F | N | N | N | N | N | N | F | 未查接口规格且缺少访问令牌，调用返回401。 |
| 3 | P | P | P | N | N | F | N | P | 重复已取得的接口列表，未提供恢复所需新信息。 |
| 4 | F | P | P | N | N | P | N | F | 未查接口规格且登录缺少username，调用返回422。 |
| 5 | P | P | P | N | N | P | N | P |  |
| 6 | F | N | N | N | N | P | N | F | 未查规格即调用不存在的show_account并报错。 |
| 7 | P | P | P | N | N | P | N | P |  |
| 8 | P | P | P | N | N | P | N | F | 调用show_profile前未查看完整接口规格。 |
| 9 | P | P | P | N | N | P | N | P |  |
| 10 | P | P | P | N | N | N | N | F | 调用show_directory前未查看完整接口规格。 |
| 11 | P | P | P | P | N | N | N | P |  |
| 12 | P | P | F | F | N | N | N | F | 未获取当前日期便认定本年为2023。 |
| 13 | P | P | P | F | N | N | N | F | 沿用未经核实的年份，且未查show_file接口规格。 |
| 14 | F | F | F | F | N | N | N | F | 仅按TXT集合求全年总额，金额含$又导致转换报错。 |
| 15 | P | F | P | F | N | P | N | F | 仅汇总4个TXT，已知2023-05账单仅有PDF。 |
| 16 | P | F | F | F | N | N | F | F | 提交的全年总额遗漏五月账单，且未查完成接口规格。 |

### 7d7fbf6_1__00（官方结果：失败）

The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/7d7fbf6_1__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_regression/7d7fbf6_1__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在的接口，且未先查看完整规格。 |
| 2 | P | P | P | N | N | P | N | P |  |
| 3 | F | N | P | N | N | P | N | F | 未查完整规格且未传访问令牌，返回401。 |
| 4 | F | N | P | N | N | P | N | F | 未查login规格且缺少必填凭据，返回422。 |
| 5 | P | P | P | N | N | P | N | F | 未先查看show_account_passwords完整规格。 |
| 6 | P | P | P | N | N | P | N | F | 未先查看file_system.login完整规格。 |
| 7 | F | N | P | N | N | F | N | F | 已知需令牌却仍未传入，并再次返回401。 |
| 8 | P | P | P | N | N | P | N | F | 调用show_directory前未查看其完整规格。 |
| 9 | P | P | P | N | N | N | N | F | 调用show_directory前未查看其完整规格。 |
| 10 | F | P | F | F | F | N | N | F | 参数无效且末尾斜杠使地点名为空。 |
| 11 | P | P | P | N | N | P | N | P |  |
| 12 | F | P | F | F | F | P | N | P | 地点名为空且归档目录错误，调用返回409。 |
| 13 | F | P | F | F | F | F | N | P | 错误路径上强制覆盖并未核验重试，返回422。 |
| 14 | P | P | P | N | N | P | N | F | 调用directory_exists前未查看完整规格。 |
| 15 | P | P | P | N | N | P | N | F | 调用两个文件系统接口前均未查看完整规格。 |
| 16 | P | P | P | F | F | P | N | P | 归档被保存到photographs根目录而非vacations。 |
| 17 | F | F | F | N | N | F | F | F | 未调用complete_task，归档位置错误且遗漏Athens。 |

## 七条新任务（含最长输入）

### 2a163ab_1__03（官方结果：失败）

Like all the venmo transactions from today involving any of my roommates on my venmo social feed.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/2a163ab_1__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/2a163ab_1__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | F | 调用前未查看show_account_passwords完整规格。 |
| 3 | F | N | N | N | N | N | N | P | 列表元素为布尔值，索引password字段触发TypeError。 |
| 4 | P | P | P | N | N | P | N | P |  |
| 5 | P | P | N | N | N | N | N | P |  |
| 6 | P | P | P | N | N | N | N | F | 调用前未查看Venmo login完整规格。 |
| 7 | P | P | N | N | N | N | N | P |  |
| 8 | P | P | N | N | N | N | N | P |  |

### b0a8eae_3__03（官方结果：成功）

Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/b0a8eae_3__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/b0a8eae_3__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未查规格即调用不存在的API，执行失败。 |
| 2 | P | N | P | N | N | P | N | P |  |
| 3 | F | N | N | N | N | P | N | F | 未查规格且未传认证令牌，调用返回401。 |
| 4 | P | N | P | N | N | F | N | P | 重复已知接口列表，未从401反馈中恢复。 |
| 5 | P | P | P | N | N | P | N | F | 未查Supervisor取密及Simple Note登录规格。 |
| 6 | F | N | P | N | N | F | N | F | 取得令牌后仍未传入，重复401且未查规格。 |
| 7 | P | P | P | N | N | P | N | F | 未查search_notes完整规格即调用。 |
| 8 | P | U | F | N | N | N | N | F | 未翻页即断言无同名笔记，且未查show_note规格。 |
| 9 | P | U | P | F | N | N | N | N | 未获取今天星期，误把全周315分钟当今日时长。 |
| 10 | F | N | P | N | N | N | N | P | 引用未定义的spotify_access_token，执行失败。 |
| 11 | P | P | P | N | N | P | N | F | 未查Supervisor凭据接口规格。 |
| 12 | P | P | P | N | N | N | N | P |  |
| 13 | P | U | F | F | N | N | N | N | 虚构KeyError，且将分钟错误等同歌曲数。 |
| 14 | P | N | F | N | N | N | N | P | 前步实际未报KeyError，却据此声称接口缺字段。 |
| 15 | P | P | P | P | N | F | N | P | 已有完整列表却无核验需要地重复查询。 |
| 16 | P | U | P | F | N | N | N | N | 未取歌曲时长，以315首作为315分钟门槛。 |
| 17 | P | U | F | F | N | F | N | N | 无依据断言需315首，并未从无结果中有效恢复。 |
| 18 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 19 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 20 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 21 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 22 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 23 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 24 | P | U | F | F | N | F | N | N | 未取时长且重复已知无效判断。 |
| 25 | P | P | F | F | N | F | N | N | 明知未找到合格列表仍改选歌曲最多者。 |
| 26 | F | N | P | F | F | N | N | F | 调用不存在且未查规格的接口，播放对象未经时长验证。 |
| 27 | P | N | P | N | N | P | N | P |  |
| 28 | P | N | P | F | F | P | N | F | 未查play_music规格，播放了时长未经验证的列表。 |
| 29 | P | N | P | N | N | N | F | F | 未验证列表覆盖今日训练即完成，且未查提交规格。 |

### b7a9ee9_1__05（官方结果：成功）

Follow all artists of all classical-genre songs in any of my playlists on Spotify.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/b7a9ee9_1__05/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/b7a9ee9_1__05/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | P | 引用未定义的 passwords，且筛选表达式会产生布尔值。 |
| 2 | P | P | N | N | N | P | N | F | 调用密码接口前未查看完整规格。 |
| 3 | P | P | P | N | N | P | N | P |  |
| 4 | P | P | P | N | N | N | N | P |  |
| 5 | P | F | F | N | N | N | N | F | 将播放列表字段键误作歌曲，且未查接口规格。 |
| 6 | F | N | F | P | N | N | N | P | 字符串元素无 get 方法，且误称已取得80首歌曲。 |
| 7 | P | P | F | N | N | P | N | P | 误称 songs 是字符串；实际为字符串列表。 |
| 8 | F | N | F | N | N | P | N | F | 调用不存在的接口，并误述 songs 中对象的含义。 |
| 9 | P | P | P | N | N | P | N | P |  |
| 10 | F | N | P | N | N | P | N | F | 未查完整规格便传入不支持的 access_token。 |
| 11 | P | P | P | N | N | P | N | P |  |
| 12 | F | N | F | N | N | P | N | F | 把歌曲字典当整数ID传入，且重复调用未查规格的接口。 |
| 13 | P | P | P | N | N | P | N | P |  |
| 14 | P | P | P | N | N | P | N | P |  |
| 15 | P | P | P | N | N | P | N | F | 调用 show_playlist 前始终未查看完整规格。 |
| 16 | P | P | P | P | N | N | N | P |  |
| 17 | P | P | F | P | N | N | N | F | 10条关联含重复却称10位艺人，且代码围栏未闭合。 |
| 18 | F | N | N | F | U | N | N | F | 缺少令牌且未查规格，重复艺人也未去重。 |
| 19 | P | P | P | N | N | P | N | P |  |
| 20 | F | N | N | F | F | P | N | P | 未处理重复及已关注状态，首个请求即中止循环。 |
| 21 | F | F | N | N | N | P | N | F | 仅取一页且误用 id 字段，触发 KeyError。 |
| 22 | P | P | P | N | N | P | N | P |  |
| 23 | F | F | P | F | F | P | N | F | 遗漏分页记录，错误重试已关注艺人并中止。 |
| 24 | P | P | F | N | N | P | N | P | 输出显示共有ID相符，所谓ID不匹配诊断不实。 |
| 25 | P | F | F | F | P | F | N | F | 沿用已失败且未分页的逻辑，未去重也未查规格。 |
| 26 | P | N | P | N | N | N | P | F | 提交前未查 complete_task 完整规格。 |

### 60d0b5b_1__02（官方结果：失败）

The last Venmo payment request I sent to Robert was an accident and they approved it. Send them the money back.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/60d0b5b_1__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/60d0b5b_1__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | F | N | N | N | N | N | P | 重复接口列表，未取得所称请求记录。 |
| 3 | P | P | N | N | N | N | N | P |  |
| 4 | P | F | N | N | N | N | N | P | 重复完整规格，未取得所称请求记录。 |
| 5 | P | F | N | N | N | N | N | P | 重复完整规格，未取得所称请求记录。 |
| 6 | P | F | N | N | N | N | N | P | 重复完整规格，未取得所称请求记录。 |
| 7 | F | N | P | N | N | N | N | P | 引用未定义的venmo_access_token，触发NameError。 |
| 8 | P | P | P | N | N | P | N | P |  |
| 9 | F | N | N | N | N | P | N | F | 密码筛选式产出布尔值并被下标，且未先查接口规格。 |
| 10 | P | P | P | N | N | P | N | F | 再次调用Supervisor接口前仍未查看其完整规格。 |
| 11 | P | N | P | N | N | P | N | P |  |
| 12 | P | U | P | N | N | P | N | F | 仅取默认5条，未核实分页覆盖；违反全分页协议。 |
| 13 | P | F | F | F | N | N | N | P | 把可见日期最早的末项误认作最新请求。 |
| 14 | P | P | F | N | N | N | N | P | 沿用3228为最新请求，但所示五条中它最旧。 |
| 15 | P | P | N | N | N | N | N | P |  |
| 16 | P | P | N | N | N | F | N | P | 重复已看过的接口列表，未获得新的退款路径信息。 |
| 17 | F | N | F | F | F | N | N | P | 把删除误当退款且选中错误请求；调用返回422。 |
| 18 | P | N | P | F | N | F | F | F | 忽略可用转账接口而报失败，且未查complete_task规格。 |

### 771d8fc_1__01（官方结果：失败）

All phone text messages and voice messages from 3654328626 are spam, delete them.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/771d8fc_1__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/771d8fc_1__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在且未查规格的接口。 |
| 2 | F | N | P | N | N | P | N | F | 改用的接口仍未经查证且不存在。 |
| 3 | P | P | F | N | N | P | N | P | 错误断言电话应用无法管理消息。 |
| 4 | F | N | P | N | N | N | N | F | 未查完整规格且缺少访问令牌。 |
| 5 | F | N | P | N | N | P | N | F | 调用未经查证且不存在的令牌接口。 |
| 6 | P | P | P | N | N | F | N | P | 重复查询已取得的接口列表，未获新信息。 |
| 7 | P | P | P | N | N | P | N | P |  |
| 8 | F | N | P | N | N | N | N | F | 调用未经查证且不存在的凭据接口。 |
| 9 | P | P | F | N | N | P | N | P | 错误声称应使用不存在的show_account接口。 |
| 10 | P | P | F | N | N | N | N | P | 仍错误声称应使用show_account接口。 |
| 11 | P | P | P | N | N | N | N | P |  |
| 12 | P | P | F | N | N | N | N | P | 注释中伪造的接口路径与实际规格不符。 |
| 13 | F | N | F | N | N | N | N | P | 误称密码接口已调用，并调用不存在的文档接口。 |
| 14 | P | P | F | N | N | P | N | P | 错误声称没有直接获取账户密码的接口。 |
| 15 | P | N | P | N | N | N | N | P |  |
| 16 | P | U | P | N | N | N | N | F | 未查完整规格或分页，无法确认覆盖全部短信。 |
| 17 | P | P | P | P | P | N | N | F | 删除接口调用前未查完整规格。 |
| 18 | P | U | F | N | N | N | N | F | 仅删一条却称短信已全删，语音覆盖亦未确认。 |
| 19 | P | P | P | P | P | N | N | F | 删除接口调用前未查完整规格。 |
| 20 | P | F | F | N | N | N | F | F | 仍有已知短信和语音未删，却宣称完成且未查提交规格。 |

### 6104387_1__05（官方结果：失败）

Export a unique list of all the songs in my song and album library and all playlists in my Spotify account into "~/backups/spotify.csv" file in my file system. The file should have headers, "Title" and "Artists" and artists should be separated by "|". Terminate my account after this backup is complete.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/6104387_1__05/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/6104387_1__05/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | P | N | N | N | N | P |  |
| 2 | P | P | P | N | N | N | N | P |  |
| 3 | P | P | P | N | N | N | N | P |  |
| 4 | P | P | P | N | N | N | N | P |  |
| 5 | P | P | P | N | N | F | N | P | 无核验需要却重复查询同一接口规格。 |
| 6 | P | P | P | N | N | F | N | P | 无核验需要却重复查询同一接口规格。 |
| 7 | P | P | P | N | N | F | N | P | 无核验需要却重复查询同一接口规格。 |
| 8 | P | P | P | N | N | F | N | P | 无核验需要却重复查询同一接口规格。 |
| 9 | P | P | P | N | N | N | N | P |  |
| 10 | P | P | P | N | N | N | N | P |  |
| 11 | P | P | P | N | N | N | N | F | 调用前未查看show_account_passwords完整规格。 |
| 12 | P | P | P | N | N | N | N | P |  |
| 13 | P | P | P | N | N | N | N | P |  |
| 14 | P | P | F | N | N | N | N | P | 文本声称输出23，实际播放列表数为6。 |
| 15 | P | P | P | N | N | F | N | P | 无核验需要却重复获取完整歌曲库。 |
| 16 | P | F | F | F | N | N | N | P | 遗漏专辑库，且声称26首而实际输出52首。 |
| 17 | F | F | F | N | N | N | N | P | song_details未定义，且“全部歌曲”覆盖不实。 |
| 18 | F | F | P | F | N | P | N | F | 遗漏专辑库，并在查规格前错误调用show_song。 |
| 19 | P | F | P | N | N | F | N | P | 重复接口列表未取得参数信息，未有效处理旧错。 |
| 20 | P | P | P | N | N | P | N | P |  |
| 21 | P | F | P | F | N | P | N | P | 所用歌曲集合已知遗漏专辑库歌曲。 |
| 22 | F | F | F | F | N | N | N | P | 集合与列表相加报错，并虚构67首等完成状态。 |
| 23 | P | F | F | F | N | P | N | P | 仍遗漏专辑库，却称得到全部歌曲ID。 |
| 24 | F | F | F | F | F | N | F | F | 使用禁用OS文件接口，未导出或删号却宣称完成。 |
| 25 | P | P | P | N | N | P | N | P |  |
| 26 | F | F | F | F | F | P | N | F | 遗漏专辑歌曲、参数名错误，文件未创建且未查规格。 |
| 27 | F | F | F | F | F | P | N | F | 使用Spotify令牌导致401，文件未创建且未查规格。 |
| 28 | P | F | F | F | N | F | N | P | 把已知Spotify令牌误认作文件系统有效令牌。 |
| 29 | P | F | F | N | N | F | F | F | 文件未创建、账户未删除，且未查完成接口规格。 |

### 29caf6f_1__00（官方结果：失败）

Christopher has asked for my movie recommendations via phone text message. Reply to them with a list of comma-separated movie titles from my Simple Note account as per their request.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/29caf6f_1__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_fresh/29caf6f_1__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | P | N | N | N | N | F | 调用不存在的接口，且未先查其完整规格。 |
| 2 | P | P | P | N | N | P | N | P |  |
| 3 | F | N | P | N | N | P | N | F | 未查完整规格便使用错误参数，调用失败。 |
| 4 | P | P | P | N | N | P | N | P |  |
| 5 | F | N | P | N | N | P | N | P | 未传必需访问令牌，返回401。 |
| 6 | P | P | P | N | N | F | N | P | 重复已知接口列表，未针对401获取登录规格。 |
| 7 | F | N | F | N | N | F | N | F | 编造密码且未查登录规格，认证失败。 |
| 8 | P | P | P | N | N | P | N | F | 未先查看密码查询接口的完整规格。 |
| 9 | F | N | P | N | N | P | N | F | 登录仍失败，且未查看登录接口完整规格。 |
| 10 | P | P | P | N | N | F | N | P | 登录失败后重复已知接口列表，未获新信息。 |
| 11 | F | N | P | N | N | F | N | P | 布尔值被当作对象取字段，触发TypeError。 |
| 12 | P | P | P | N | N | P | N | P |  |
| 13 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 14 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 15 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 16 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 17 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 18 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 19 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 20 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 21 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 22 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 23 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 24 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 25 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 26 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |
| 27 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 28 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 29 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 30 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |
| 31 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 32 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 33 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 34 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |
| 35 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 36 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 37 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 38 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |
| 39 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 40 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 41 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 42 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |
| 43 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 44 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 45 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 46 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |
| 47 | P | P | P | N | N | F | N | P | 重复已知接口列表，未获得认证恢复信息。 |
| 48 | P | P | P | N | N | F | N | P | 重复核对已确认密码，未获得恢复所需新信息。 |
| 49 | F | N | P | N | N | F | N | F | 原样重试已知失败的登录组合，且仍未查规格。 |
| 50 | P | F | P | N | N | F | N | F | 用户资料不含登录凭据，且调用前未查规格。 |

## 相同输入独立重复调用

### 302c169_2__02（官方结果：成功）

I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_repeat/302c169_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_repeat/302c169_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未查规格且缺少令牌，查询返回401。 |
| 2 | F | N | P | N | N | P | N | F | 调用未查规格且不存在的接口，执行失败。 |
| 3 | P | P | P | N | N | P | N | F | 调用密码接口前未查其规格。 |
| 4 | F | N | P | N | N | N | N | F | 未查登录规格并误用邮箱，返回401。 |
| 5 | P | P | P | N | N | P | N | P |  |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | F | 调用闹钟查询接口前未查其规格。 |
| 8 | P | P | P | P | N | N | N | P |  |
| 9 | P | P | P | P | N | N | N | P |  |
| 10 | P | P | P | P | P | N | N | F | 批量更新前未查更新闹钟接口规格。 |
| 11 | P | P | P | N | N | N | P | F | 提交前未查complete_task接口规格。 |

### cf6abd2_2__01（官方结果：成功）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_repeat/cf6abd2_2__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_repeat/cf6abd2_2__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | P | N | N | N | N | P |  |
| 2 | P | P | P | N | N | N | N | P |  |
| 3 | F | N | P | N | N | N | N | F | 未查完整规格且调用缺少认证，返回401。 |
| 4 | F | N | P | N | N | P | N | F | 未查登录规格且缺少必填参数，返回422。 |
| 5 | P | P | P | N | N | P | N | F | 调用前未查看密码接口的完整规格。 |
| 6 | F | N | P | N | N | P | N | F | 未查规格并调用不存在的用户名接口。 |
| 7 | F | N | P | N | N | F | N | F | 继续猜测不存在的接口，未依据反馈查规格。 |
| 8 | P | P | P | N | N | P | N | F | 调用show_profile前未查看完整规格。 |
| 9 | P | P | P | N | N | P | N | F | 调用login前未查看完整规格。 |
| 10 | P | P | P | N | N | N | N | F | 调用search_notes前未查看完整规格。 |
| 11 | P | P | P | N | N | N | N | F | 调用search_notes前未查看完整规格。 |
| 12 | P | F | F | N | N | F | N | F | 重复相同查询，且摘要不能证明条目不在内容中。 |
| 13 | P | F | F | N | N | P | N | F | 仍以摘要断言条目不存在，且未查接口规格。 |
| 14 | P | F | F | N | N | F | N | F | 已知候选笔记仍重复搜索，且据摘要断言不存在。 |
| 15 | P | P | P | N | N | P | N | F | 调用show_note前未查看完整规格。 |
| 16 | P | P | P | P | P | N | N | F | 更新前未查看update_note完整规格。 |
| 17 | P | N | P | N | N | N | P | F | 提交前未查看complete_task完整规格。 |

### 7d7fbf6_1__00（官方结果：失败）

The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_repeat/7d7fbf6_1__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v4_repeat/7d7fbf6_1__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | P | N | N | N | N | F | 调用不存在且未查规格的接口，执行失败。 |
| 2 | P | P | P | N | N | P | N | P |  |
| 3 | F | N | P | N | N | P | N | F | 未查完整规格且缺少访问令牌，读取失败。 |
| 4 | F | N | P | N | N | P | N | F | 未查登录规格并遗漏必需参数，执行失败。 |
| 5 | P | P | P | N | N | P | N | F | 未查密码查询接口的完整规格。 |
| 6 | P | P | P | N | N | P | N | F | 未查登录接口的完整规格。 |
| 7 | F | N | P | N | N | F | N | F | 忽略令牌要求而重复401错误，且未查规格。 |
| 8 | P | P | P | N | N | P | N | F | 未查目录读取接口的完整规格。 |
| 9 | P | P | P | N | N | N | N | F | 未查目录读取接口的完整规格。 |
| 10 | F | P | F | F | F | N | N | F | 地点名被解析为空，参数错误且未查接口规格。 |
| 11 | P | P | P | N | N | P | N | P |  |
| 12 | F | P | F | F | F | P | N | P | 地点名为空，首个目录错存后循环因路径冲突中止。 |
| 13 | F | U | F | F | F | F | N | P | 复合写入报错后未核对结果即重试，仍使用空地点名。 |
| 14 | P | P | P | N | N | P | N | F | 未查目录存在性接口的完整规格。 |
| 15 | P | P | P | N | N | P | N | F | 两个读取接口均未查完整规格。 |
| 16 | P | P | P | F | F | P | N | P | 压缩包保存到photographs而非vacations目录。 |
| 17 | F | F | F | N | N | N | F | F | 错误宣称完成，归档路径不符且未调用complete_task。 |

