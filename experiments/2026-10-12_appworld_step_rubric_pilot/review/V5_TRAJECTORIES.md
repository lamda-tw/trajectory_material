# v5 逐步评分复核

以下为模型原始标签与短依据，仅整理排版。官方成败仅供事后复核，未发送给 judge。

P=通过，F=违反，U=证据不足，N=不适用；八维没有权重，不合成总分。

R1 执行契约；R2 证据与覆盖；R3 状态与数据保真；R4 决策与计算；R5 操作与实际效果；R6 反馈与恢复；R7 结束与交付；R8 授权与交互协议。

## 八条回归样本

### 76f2c72_1__03（官方结果：成功）

What is the total cost of my electricity bills for this year? The bills are in "~/bills/" directory of my file system.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/76f2c72_1__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/76f2c72_1__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | F | N | N | N | N | N | N | F | 缺少访问令牌且未先查询完整接口规格。 |
| 3 | P | P | N | N | N | F | N | P | 重复已知接口列表，未获得新的必要信息。 |
| 4 | F | P | P | N | N | P | N | F | 登录缺少用户名，且调用前未查询完整规格。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | F | N | N | N | N | P | N | F | 调用不存在且未查规格的Supervisor接口。 |
| 7 | P | P | N | N | N | P | N | P |  |
| 8 | P | P | P | N | N | P | N | F | 未查询show_profile完整规格便调用。 |
| 9 | P | N | P | N | N | P | N | P |  |
| 10 | P | P | P | N | N | N | N | F | 未查询show_directory完整规格便调用。 |
| 11 | P | P | P | N | N | N | N | P |  |
| 12 | P | P | U | F | N | N | N | F | 未获取当前日期便假定本年为2023年。 |
| 13 | P | F | P | N | N | N | N | F | 已知漏读仅有PDF的2023年5月账单，且未查规格。 |
| 14 | F | F | N | F | N | N | N | F | 金额含美元符号导致异常，聚合范围也漏掉5月PDF。 |
| 15 | P | F | P | F | N | P | N | F | 虽修复解析错误，但总额仍漏掉已知5月PDF。 |
| 16 | P | F | F | F | N | N | F | F | 将缺少5月账单的368误作全年总额并提交，且未查规格。 |

### b0a8eae_3__03（官方结果：成功）

Start playing a playlist on Spotify that has enough songs for my workout today. I do not want to have to change the playlist in the middle of my workout. The workout plan is in Simple Note.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/b0a8eae_3__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/b0a8eae_3__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在的接口，且事前未查完整规格。 |
| 2 | P | P | N | N | N | P | N | P |  |
| 3 | F | N | N | N | N | P | N | F | 缺少访问令牌导致未授权，且未查接口规格。 |
| 4 | P | P | N | N | N | F | N | P | 重复查询已知接口列表，没有获得新信息。 |
| 5 | P | P | P | N | N | P | N | F | 登录成功，但相关接口调用前未查完整规格。 |
| 6 | F | N | N | N | N | F | N | F | 登录后仍未传令牌，重复已知的未授权错误。 |
| 7 | P | U | N | N | N | P | N | F | 未分页搜索笔记，且调用前未查完整接口规格。 |
| 8 | P | P | P | N | N | N | N | F | 读取笔记成功，但调用前未查完整接口规格。 |
| 9 | P | U | P | F | N | N | N | F | 将整周315分钟当作今日时长，且未获取当前日期。 |
| 10 | F | N | P | F | N | N | N | P | 使用未定义令牌变量，且继续采用错误的315分钟。 |
| 11 | P | P | P | N | N | P | N | F | Spotify登录成功，但读取凭据前未查接口规格。 |
| 12 | P | P | P | N | N | P | N | P |  |
| 13 | P | U | F | F | N | N | N | P | 捏造KeyError反馈，并把315分钟误当315首歌。 |
| 14 | P | P | N | N | N | N | N | P |  |
| 15 | P | P | P | F | N | F | N | P | 将各列表歌曲合计为67，且无必要重复分页查询。 |
| 16 | P | U | F | F | N | N | N | P | 未取歌曲时长，却断言今日锻炼为315分钟。 |
| 17 | P | N | F | F | N | F | N | P | 无依据地把315分钟换算成315首歌并重复旧结论。 |
| 18 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且重复使用错误的315首阈值。 |
| 19 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且无新信息地重复相同查询。 |
| 20 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且无新信息地重复相同查询。 |
| 21 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且无新信息地重复相同查询。 |
| 22 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且无新信息地重复相同查询。 |
| 23 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且无新信息地重复相同查询。 |
| 24 | P | U | F | F | N | F | N | P | 缺少歌曲时长，且无新信息地重复相同查询。 |
| 25 | P | U | F | F | N | F | N | P | 未核对时长便称均不足，并擅自改选歌曲最多列表。 |
| 26 | F | N | P | F | F | N | N | F | 调用不存在且未查规格的播放接口，未产生播放效果。 |
| 27 | P | P | N | N | N | P | N | P |  |
| 28 | P | U | N | F | U | P | N | F | 列表总时长未知，且未查play_music完整规格。 |
| 29 | P | U | U | N | N | N | U | F | 缺少今日及列表时长证据，且未查完成接口便提交。 |

### b7a9ee9_1__05（官方结果：成功）

Follow all artists of all classical-genre songs in any of my playlists on Spotify.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/b7a9ee9_1__05/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/b7a9ee9_1__05/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | P | passwords未定义，NameError终止。 |
| 2 | P | P | N | N | N | P | N | F | 调用Supervisor接口前未查完整规格。 |
| 3 | P | P | P | N | N | P | N | P |  |
| 4 | P | P | P | N | N | N | N | P |  |
| 5 | P | P | F | N | N | N | N | F | 将播放列表字典键当作歌曲汇总，且未查接口规格。 |
| 6 | F | N | F | P | N | N | N | P | 把字符串键当歌曲对象，导致AttributeError。 |
| 7 | P | P | N | N | N | P | N | P |  |
| 8 | F | N | F | N | N | P | N | F | 误把歌曲摘要当ID并调用不存在接口，且未查规格。 |
| 9 | P | P | N | N | N | P | N | P |  |
| 10 | F | N | F | N | N | P | N | F | 误把歌曲摘要当ID并传入多余参数，且未查完整规格。 |
| 11 | P | P | P | N | N | P | N | P |  |
| 12 | F | N | F | N | N | P | N | F | 把歌曲摘要字典传作整数ID，且仍调用未查规格的接口。 |
| 13 | P | P | N | N | N | P | N | P |  |
| 14 | P | P | P | N | N | P | N | P |  |
| 15 | P | P | P | N | N | P | N | F | 调用show_playlist前始终未查完整规格。 |
| 16 | P | P | P | P | N | N | N | P |  |
| 17 | P | P | P | N | N | N | N | P |  |
| 18 | F | N | F | F | F | N | N | F | 艺术家未去重且未带令牌，首个调用即失败。 |
| 19 | P | P | P | N | N | P | N | P |  |
| 20 | F | N | P | F | F | P | N | P | 未处理已关注与重复目标，循环首项即中止。 |
| 21 | F | N | F | F | N | P | N | F | 误用id字段且未查列表接口规格，恢复再次中止。 |
| 22 | P | P | P | N | N | P | N | P |  |
| 23 | F | P | P | F | P | P | N | F | 未去重导致重复关注报错；列表接口亦未查规格。 |
| 24 | P | P | N | N | N | P | N | P |  |
| 25 | P | P | P | P | N | P | N | F | 未查show_following_artists完整规格。 |
| 26 | P | N | P | N | N | N | P | F | 完成前未查complete_task完整规格。 |

### 60d0b5b_1__02（官方结果：失败）

The last Venmo payment request I sent to Robert was an accident and they approved it. Send them the money back.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/60d0b5b_1__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/60d0b5b_1__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | F | N | P | 重复既有接口列表，未获得新信息。 |
| 3 | P | P | N | N | N | N | N | P |  |
| 4 | P | P | N | N | N | F | N | P | 重复同一接口规格，未获得新信息。 |
| 5 | P | P | N | N | N | F | N | P | 重复同一接口规格，未获得新信息。 |
| 6 | P | P | N | N | N | F | N | P | 重复同一接口规格，未获得新信息。 |
| 7 | F | N | N | N | N | N | N | F | 引用未定义令牌且未按分页协议查询。 |
| 8 | P | P | P | N | N | P | N | P |  |
| 9 | F | N | N | N | N | P | N | F | 把布尔值当字典取密码，且未先查接口规格。 |
| 10 | P | P | P | N | N | P | N | F | 再次调用未查规格的Supervisor接口。 |
| 11 | P | P | P | N | N | P | N | P |  |
| 12 | P | U | P | N | N | P | N | F | 未遍历分页，无法确认覆盖全部相关请求。 |
| 13 | P | U | F | F | N | N | N | P | 未分页且把可见列表最旧项误作最后发送项。 |
| 14 | P | P | F | N | N | F | N | P | 重复既有接口列表且仍把3228称为最后请求。 |
| 15 | P | P | P | N | N | P | N | P |  |
| 16 | P | P | P | N | N | F | N | P | 重复既有接口列表，未获得新信息。 |
| 17 | F | N | F | F | F | N | N | P | 把删除已完成请求误当退款，且对象并非最后请求。 |
| 18 | P | P | F | F | N | F | F | F | 忽略可用转账接口，未退款且未查完成接口规格。 |

### cf6abd2_2__01（官方结果：成功）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/cf6abd2_2__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/cf6abd2_2__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | F | N | N | N | N | N | N | F | 未查规格且缺少访问令牌，查询返回401。 |
| 4 | F | N | N | N | N | P | N | F | 未查规格且缺少必填凭据，登录返回422。 |
| 5 | P | P | N | N | N | P | N | F | 调用前未查看凭据接口的完整规格。 |
| 6 | F | N | N | N | N | P | N | F | 未查规格并调用不存在的接口。 |
| 7 | F | N | N | N | N | P | N | F | 未查规格并再次猜测不存在的接口。 |
| 8 | P | P | N | N | N | P | N | F | 调用前未查看个人资料接口的完整规格。 |
| 9 | P | P | P | N | N | P | N | F | 调用前未查看登录接口的完整规格。 |
| 10 | P | P | N | N | N | P | N | F | 调用前未查看搜索接口的完整规格。 |
| 11 | P | P | N | N | N | P | N | F | 调用前未查看搜索接口的完整规格。 |
| 12 | P | P | N | N | N | F | N | F | 无核验需要地重复相同查询，且未查接口规格。 |
| 13 | P | P | N | N | N | P | N | F | 调用前未查看搜索接口的完整规格。 |
| 14 | P | P | N | N | N | F | N | F | 目标笔记已定位仍重复查询，且未查接口规格。 |
| 15 | P | P | P | N | N | N | N | F | 调用前未查看笔记详情接口的完整规格。 |
| 16 | P | P | P | P | P | N | N | F | 调用前未查看更新接口的完整规格。 |
| 17 | P | N | P | N | N | N | P | F | 调用complete_task前未查看其完整规格。 |

### 7d7fbf6_1__00（官方结果：失败）

The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/7d7fbf6_1__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/7d7fbf6_1__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在且未查规格的接口，执行失败。 |
| 2 | P | P | P | N | N | P | N | P |  |
| 3 | F | N | P | N | N | P | N | F | 未查完整规格且调用缺少访问令牌，返回401。 |
| 4 | F | N | P | N | N | P | N | F | 未查登录规格且缺少必填凭据，返回422。 |
| 5 | P | P | P | N | N | P | N | F | 调用前未查账户密码接口完整规格。 |
| 6 | P | P | P | N | N | P | N | F | 调用前未查文件系统登录接口完整规格。 |
| 7 | F | N | P | N | N | F | N | F | 再次未传访问令牌并忽略此前401，且未查规格。 |
| 8 | P | P | P | N | N | P | N | F | 调用前仍未查show_directory完整规格。 |
| 9 | P | P | P | N | N | N | N | F | 调用前未查show_directory完整规格。 |
| 10 | F | P | F | F | F | N | N | F | 尾斜杠导致地点名为空，参数无效且未查规格。 |
| 11 | P | P | P | N | N | P | N | P |  |
| 12 | F | P | F | F | F | P | N | P | 地点名仍为空且目标路径错误，调用冲突失败。 |
| 13 | F | P | F | F | F | F | N | F | 未核对复合写入状态即覆盖重试，空地点名路径仍错误。 |
| 14 | P | P | P | N | N | P | N | F | 调用前未查directory_exists完整规格。 |
| 15 | P | P | P | N | N | P | N | F | 调用前未查两个读取接口的完整规格。 |
| 16 | P | P | P | F | F | P | N | F | 三个压缩包保存到错误目录，且额外代码块违反协议。 |
| 17 | F | F | F | N | N | N | F | F | 未调用完成接口且错误宣称任务成功，亦无可执行代码。 |

### 302c169_2__02（官方结果：成功）

I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/302c169_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/302c169_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未先查 show_alarms 规格，且调用因缺少令牌失败。 |
| 2 | F | N | N | N | N | F | N | F | 未查规格便调用不存在的接口，未能修复认证错误。 |
| 3 | P | P | P | N | N | P | N | F | 未先查看 show_account_passwords 接口规格。 |
| 4 | F | N | F | N | N | F | N | F | 将邮箱误作手机号用户名，且未查规格，登录失败。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | F | 未先查看 show_alarms 接口规格。 |
| 8 | P | P | P | P | N | N | N | P |  |
| 9 | P | P | P | P | N | N | N | P |  |
| 10 | P | P | P | P | P | N | N | F | 未先查看 update_alarm 规格即批量修改闹钟。 |
| 11 | P | N | P | N | N | N | P | F | 未查看 complete_task 接口规格便提交完成。 |

### e7a10f8_3__04（官方结果：失败）

How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/e7a10f8_3__04/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_regression/e7a10f8_3__04/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | F | N | N | N | F | 调用不存在且未查规格的接口，并预设每首3分钟。 |
| 2 | P | P | P | N | N | P | N | F | 未先查询密码接口规格。 |
| 3 | P | P | P | N | N | N | N | P |  |
| 4 | P | U | U | N | N | N | N | F | 仅取默认第一页却称全部，未循环分页。 |
| 5 | P | U | U | F | N | N | N | P | 分页覆盖未知，且错误地以歌曲数判定时长最长。 |
| 6 | P | F | F | F | N | N | N | P | 无时长证据，擅用每首3分钟估算实际时长。 |
| 7 | P | F | F | F | N | N | F | F | 提交无时长依据的答案，且未查询完成接口规格。 |

## 四条新任务

### 07b42fd_2__00（官方结果：成功）

Follow all the edm artists on Spotify that have at least 23 followers.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/07b42fd_2__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/07b42fd_2__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | P | P | N | N | N | N | N | P |  |
| 4 | P | P | P | N | N | N | N | P |  |
| 5 | P | P | P | P | N | N | N | P |  |
| 6 | F | N | P | P | F | N | N | F | 关注调用缺少令牌且未查接口规格，执行失败。 |
| 7 | F | N | N | N | N | P | N | F | 凭据提取表达式错误，且未查Supervisor接口规格。 |
| 8 | P | P | P | N | N | P | N | F | 修正了提取错误，但仍未查凭据接口规格。 |
| 9 | P | N | P | N | N | P | N | P |  |
| 10 | P | N | P | P | P | P | N | F | 关注接口规格始终未查询。 |
| 11 | P | P | P | N | N | N | P | F | 完成接口规格未查询。 |

### 82e2fac_2__02（官方结果：成功）

What is the title of the least-played song in my Spotify song library.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/82e2fac_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/82e2fac_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | P | P | N | N | N | N | N | P |  |
| 4 | P | P | N | N | N | N | N | F | 未先查看 supervisor 凭据接口的完整规格。 |
| 5 | P | P | P | P | N | N | N | P |  |
| 6 | P | P | P | N | N | F | N | P | 重复已见的接口列表，未带来新信息。 |
| 7 | P | P | P | N | N | F | N | P | 无状态变化却重复读取完整歌曲库。 |
| 8 | F | N | F | P | N | N | N | P | 未执行的评论代码不建立变量，却声称已取得播放次数。 |
| 9 | F | N | P | F | N | P | N | F | 未查规格便传入非法参数，且将缺失播放次数默认成0。 |
| 10 | P | P | P | N | N | P | N | P |  |
| 11 | P | P | P | P | N | P | N | P |  |
| 12 | P | P | P | P | N | N | P | F | 调用 complete_task 前未查看其完整接口规格。 |

### 22cc237_3__00（官方结果：失败）

I went on a dinner with some of my coworkers yesterday. I paid the entire bill to simplify the payment. I've made a note of individual shares in simple note. Some people have already sent me their share on venmo. Make payment requests for others with a description note "Dinner with Colleagues".

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/22cc237_3__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/22cc237_3__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在且未查规格的接口。 |
| 2 | F | N | N | N | N | P | N | F | 缺少认证且未查接口规格。 |
| 3 | P | P | N | N | N | P | N | P |  |
| 4 | P | P | N | N | N | P | N | P |  |
| 5 | F | N | F | N | N | N | N | P | 捏造密码并导致认证失败。 |
| 6 | P | P | P | N | N | P | N | F | 未查Supervisor接口规格。 |
| 7 | P | N | P | N | N | P | N | P |  |
| 8 | P | U | P | N | N | P | N | F | 未分页，联系人覆盖范围不明，且未查规格。 |
| 9 | F | N | N | N | N | N | N | F | 调用不存在且未查规格的接口。 |
| 10 | P | P | N | N | N | P | N | P |  |
| 11 | F | N | N | N | N | P | N | F | 参数错误且未查接口规格。 |
| 12 | F | N | N | N | N | P | N | F | 引用未定义令牌且未查接口规格。 |
| 13 | P | P | P | N | N | P | N | F | 未查Supervisor接口规格。 |
| 14 | P | N | P | N | N | P | N | F | 未查Venmo登录接口规格。 |
| 15 | P | P | P | N | N | P | N | F | 未查接口规格且未按要求遍历分页。 |
| 16 | P | F | F | N | N | N | N | F | 收款请求不能证明同事已付款，且未分页查规格。 |
| 17 | P | F | F | F | N | N | N | P | 把本人批准他人收款请求误作同事已付账。 |
| 18 | P | F | F | F | N | N | F | P | 未读便签即选人，并捏造付款请求已创建。 |
| 19 | P | N | F | N | N | F | F | F | 付款请求未执行却宣称完成，且未查完成接口规格。 |

### 34d9492_1__01（官方结果：失败）

Arrange my "~/photographs/vacations/" directory by organizing the photos from three vacations. The files created in February and March of this year correspond to Petra and Budapest, respectively, while the others are from Amsterdam. Move them into sub-directories named after their respective vacation spots, maintaining the original file names.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/34d9492_1__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_fresh/34d9492_1__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | F | N | N | N | N | F | 使用机器OS展开到/root路径并触发FileNotFoundError。 |
| 2 | F | N | N | N | N | P | N | F | 调用被禁止的file_system模块，执行失败。 |
| 3 | P | P | P | N | N | P | N | P |  |
| 4 | F | N | P | N | N | N | N | F | 未查规格且以位置参数调用，触发TypeError。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | F | N | P | N | N | P | N | F | 未查login规格且缺少账号密码，返回422。 |
| 7 | P | P | P | N | N | P | N | F | 未先查看show_account_passwords完整规格。 |
| 8 | P | P | P | N | N | P | N | F | 未先查看login完整规格便调用。 |
| 9 | P | P | P | N | N | P | N | P |  |
| 10 | F | F | F | F | N | N | N | F | 把随机文件名臆作日期，且解析触发ValueError。 |
| 11 | P | F | F | F | N | P | N | F | 仍以文件名代替创建日期，错误得到三个空列表。 |
| 12 | P | F | F | F | N | F | N | F | 已知空结果后原样重复无效分类。 |
| 13 | P | F | F | F | N | F | N | F | 再次原样重复已知无效的分类。 |
| 14 | P | F | F | F | N | F | N | F | 继续从随机文件名截取月份，且漏掉29个文件。 |
| 15 | F | F | F | F | N | F | N | F | 明知分类仅覆盖13/42仍继续，且调用缺少令牌。 |
| 16 | F | F | F | F | N | P | N | F | 补令牌后因move_file参数错误中止，分类仍无依据。 |
| 17 | P | F | F | F | F | P | N | F | 仅移动13/42且未核对创建日期，任务范围不完整。 |
| 18 | P | F | F | N | N | F | F | F | 已知仅移动13/42仍宣称完成，且未查完成接口规格。 |

## 相同输入独立重复调用

### 302c169_2__02（官方结果：成功）

I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_repeat/302c169_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_repeat/302c169_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未查规格且缺少访问令牌，调用以401失败。 |
| 2 | F | N | P | N | N | P | N | F | 未查规格并调用不存在的令牌接口，执行失败。 |
| 3 | P | P | P | N | N | P | N | F | 未先查看凭据接口规格即调用。 |
| 4 | F | N | F | N | N | N | N | F | 未查登录规格且误用邮箱作为手机号用户名，认证失败。 |
| 5 | P | P | P | N | N | P | N | P |  |
| 6 | P | N | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | F | 未先查看闹钟列表接口规格即调用。 |
| 8 | P | P | P | P | N | N | N | P |  |
| 9 | P | P | P | P | N | N | N | P |  |
| 10 | P | P | P | P | P | N | N | F | 未先查看闹钟更新接口规格即执行修改。 |
| 11 | P | N | P | N | N | N | P | F | 未先查看任务完成接口规格即调用。 |

### cf6abd2_2__01（官方结果：成功）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_repeat/cf6abd2_2__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v5_repeat/cf6abd2_2__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | F | N | N | N | N | N | N | F | 未查完整规格且缺少令牌，调用返回401。 |
| 4 | F | N | P | N | N | P | N | F | 未查登录规格并漏传用户名和密码，调用失败。 |
| 5 | P | P | P | N | N | P | N | F | 未查完整接口规格便调用凭据接口。 |
| 6 | F | N | P | N | N | P | N | F | 调用了未查规格且不存在的用户名接口。 |
| 7 | F | N | N | N | N | F | N | F | 收到接口不存在反馈后仍猜测另一接口并失败。 |
| 8 | P | P | P | N | N | P | N | F | 恢复取得个人信息，但调用前未查完整规格。 |
| 9 | P | P | P | N | N | P | N | F | 登录成功，但调用前未查完整登录规格。 |
| 10 | P | P | P | N | N | P | N | F | 搜索正常推进，但调用前未查完整规格。 |
| 11 | P | P | P | N | N | P | N | F | 查询找到相关清单，但调用前未查完整规格。 |
| 12 | P | P | P | N | N | F | N | F | 无核验需要地原样重复查询，且未查规格。 |
| 13 | P | P | P | N | N | P | N | F | 扩大查询取得线索，但调用前未查完整规格。 |
| 14 | P | P | P | N | N | F | N | F | 已知目标清单后仍作无新信息的重复搜索。 |
| 15 | P | P | P | N | N | P | N | F | 读取内容确认目标项，但调用前未查完整规格。 |
| 16 | P | N | P | P | P | N | N | F | 正确改为未完成且执行成功，但未查更新规格。 |
| 17 | P | N | P | N | N | N | P | F | 完成证据充分，但未查complete_task规格。 |

