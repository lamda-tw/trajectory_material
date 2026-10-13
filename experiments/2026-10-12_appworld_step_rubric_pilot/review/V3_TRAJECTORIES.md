# v3 逐步评分复核

以下为模型原始标签与短依据，仅整理排版。官方成败仅供事后复核，未发送给 judge。

P=通过，F=违反，U=证据不足，N=不适用；八维没有权重，不合成总分。

R1 执行契约；R2 证据与覆盖；R3 状态与数据保真；R4 决策与计算；R5 操作与实际效果；R6 反馈与恢复；R7 结束与交付；R8 授权与交互协议。

## 原六条开发样本

### 302c169_2__02（官方结果：成功）

I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/302c169_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/302c169_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未查规格且缺少令牌，调用返回401。 |
| 2 | F | N | N | N | N | P | N | F | 未查规格并调用不存在的接口。 |
| 3 | P | P | P | N | N | P | N | F | 调用账户密码接口前未查规格。 |
| 4 | F | N | N | N | N | P | N | F | 未查规格且用户名类型错误，登录返回401。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | P | N | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | F | 调用闹钟查询接口前未查规格。 |
| 8 | P | P | P | P | N | N | N | P |  |
| 9 | P | N | P | P | N | N | N | P |  |
| 10 | P | N | P | P | P | N | N | F | 调用更新闹钟接口前未查规格。 |
| 11 | P | N | P | N | N | N | P | F | 调用complete_task前未查其完整规格。 |

### 302c169_3__03（官方结果：失败）

I am going on a vacation. Move my go-to-sleep phone alarm to 20 minutes later and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/302c169_3__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/302c169_3__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | F | N | N | N | N | N | N | F | 未查show_alarms规格且缺少认证，返回401。 |
| 3 | P | P | N | N | N | P | N | P |  |
| 4 | P | P | P | N | N | P | N | F | 未先查看show_account_passwords完整规格。 |
| 5 | F | N | F | N | N | P | N | P | 将布尔列表元素当字典索引，触发TypeError。 |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | P | N | F | 未先查看show_alarms完整规格。 |
| 8 | P | F | F | F | N | N | N | P | 无依据将Wake Up闹钟认作睡眠闹钟。 |
| 9 | P | F | F | F | F | F | N | F | 改动了错误闹钟，且未查看update_alarm规格。 |
| 10 | P | N | F | F | N | F | F | F | 其余闹钟未实际禁用却提交完成，且未查提交规格。 |

### cf6abd2_2__01（官方结果：成功）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/cf6abd2_2__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/cf6abd2_2__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | F | N | N | N | N | N | N | F | 缺少访问令牌且未先查完整接口规格，调用返回401。 |
| 4 | F | N | N | N | N | P | N | F | 未提供必填用户名和密码，且未先查接口规格。 |
| 5 | P | P | N | N | N | P | N | F | 调用凭据接口前未查看其完整规格。 |
| 6 | F | N | N | N | N | P | N | F | 调用不存在的接口，且未先查完整规格。 |
| 7 | F | N | N | N | N | F | N | F | 前一接口不存在后仍猜测新接口，调用再次失败。 |
| 8 | P | P | N | N | N | P | N | F | 调用show_profile前未查看完整接口规格。 |
| 9 | P | P | P | N | N | P | N | F | 调用登录接口前未查看其完整规格。 |
| 10 | P | P | P | N | N | P | N | F | 调用search_notes前未查看完整接口规格。 |
| 11 | P | P | P | N | N | P | N | F | 调用search_notes前未查看完整接口规格。 |
| 12 | P | P | P | N | N | F | N | F | 无信息变化却重复相同查询，且仍未查看接口规格。 |
| 13 | P | P | P | N | N | P | N | F | 调用search_notes前未查看完整接口规格。 |
| 14 | P | P | P | N | N | F | N | F | 已定位目标笔记仍重复搜索，且未查看接口规格。 |
| 15 | P | P | P | N | N | P | N | F | 调用show_note前未查看完整接口规格。 |
| 16 | P | N | P | P | P | N | N | F | 调用update_note前未查看完整接口规格。 |
| 17 | P | N | P | N | N | N | P | F | 调用complete_task前未查看完整接口规格。 |

### cf6abd2_2__02（官方结果：失败）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/cf6abd2_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/cf6abd2_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在的接口，且未先查完整规格。 |
| 2 | P | P | P | N | N | P | N | P |  |
| 3 | F | N | P | N | N | P | N | F | 未查完整规格且缺少访问令牌，返回401。 |
| 4 | P | P | P | N | N | F | N | P | 重复已知的接口列表，未增加恢复所需信息。 |
| 5 | F | N | F | F | N | P | N | F | 引用未定义变量，且密码筛选逻辑错误。 |
| 6 | F | P | F | F | N | P | N | F | 把布尔值当字典取密码，导致类型错误。 |
| 7 | P | P | P | P | N | P | N | F | 成功修复密码筛选，但未先查接口完整规格。 |
| 8 | P | N | P | N | N | P | N | F | 登录成功，但未先查登录接口完整规格。 |
| 9 | P | P | P | N | N | P | N | F | 搜索成功并修复鉴权问题，但未查完整规格及分页。 |
| 10 | P | P | F | P | N | N | N | F | 读取前无依据断言目标项在该笔记中，且未查规格。 |
| 11 | P | N | F | P | P | N | N | F | 误称原项已是未完成；更新正确但未查接口规格。 |
| 12 | F | N | F | N | N | N | F | F | 无代码导致终止，且未实际调用完成任务接口。 |

### e7a10f8_3__02（官方结果：成功）

How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/e7a10f8_3__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/e7a10f8_3__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | N | F | N | N | N | N | F | 捏造并冒充已取得的访问令牌，违反禁止猜测。 |
| 2 | F | N | F | N | N | N | N | P | 使用已知伪造令牌，接口返回401。 |
| 3 | F | N | N | N | N | F | N | F | 未查规格便调用不存在接口，未有效处理鉴权错误。 |
| 4 | P | P | P | N | N | P | N | F | 调用凭据接口前未查看其API规格。 |
| 5 | P | P | P | N | N | P | N | P |  |
| 6 | F | N | F | F | N | N | N | F | 未查规格且误用字段，并无依据假设每首歌3分钟。 |
| 7 | P | P | P | N | N | P | N | P |  |
| 8 | P | P | P | P | N | P | N | P |  |
| 9 | P | N | P | P | N | N | P | F | 调用complete_task前未查看其API规格。 |

### e7a10f8_3__04（官方结果：失败）

How long is my longest Spotify playlist, in minutes, rounded to the nearest number?

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/e7a10f8_3__04/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_test/e7a10f8_3__04/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | F | N | N | N | F | 调用不存在且未查规格的接口，并提出无依据时长假设。 |
| 2 | P | P | P | N | N | P | N | F | 虽修复取密方式，但调用前未查看该接口规格。 |
| 3 | P | N | P | N | N | N | N | P |  |
| 4 | P | F | F | N | N | N | N | F | 仅取默认首个分页却宣称取得全部播放列表。 |
| 5 | P | F | F | F | N | F | N | F | 基于未完整分页的数据判定全局最长，且未纠正覆盖缺口。 |
| 6 | P | F | F | F | N | F | N | F | 用臆定的每首3分钟替代歌曲实际时长。 |
| 7 | P | N | F | F | N | F | F | F | 未查完成接口规格，并提交了基于臆测的错误答案。 |

## 两条新增任务

### 76f2c72_1__03（官方结果：成功）

What is the total cost of my electricity bills for this year? The bills are in "~/bills/" directory of my file system.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_unseen/76f2c72_1__03/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_unseen/76f2c72_1__03/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | F | N | N | N | N | N | N | F | 缺少认证且调用前未查show_directory完整规格。 |
| 3 | P | P | N | N | N | F | N | P | 401后重复已见的接口简介，未获取认证规格。 |
| 4 | F | P | P | N | N | P | N | F | 登录缺少username，且两个接口均未先查完整规格。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | F | N | N | N | N | P | N | F | 调用不存在的接口，且未先查询其完整规格。 |
| 7 | P | P | N | N | N | P | N | P |  |
| 8 | P | P | P | N | N | P | N | F | 调用show_profile前未查询完整接口规格。 |
| 9 | P | N | P | N | N | P | N | P |  |
| 10 | P | P | P | N | N | P | N | F | 调用show_directory前未查询完整接口规格。 |
| 11 | P | P | P | P | N | N | N | P |  |
| 12 | P | U | P | F | N | N | N | F | 未获取当前日期即认定今年为2023。 |
| 13 | P | P | N | N | N | N | N | F | 调用show_file前未查询完整接口规格。 |
| 14 | F | N | P | F | N | N | N | F | 金额含美元符号导致转换失败，且未查接口规格。 |
| 15 | P | F | P | F | N | P | N | F | 漏算仅有PDF的五月账单，且未查接口规格。 |
| 16 | P | N | F | F | F | F | F | F | 将不完整总额作为答案提交，且未查complete_task规格。 |

### 7d7fbf6_1__00（官方结果：失败）

The "~/photographs/" directory in my file system has photo files organized in sub-directories for each vacation spot. Compress them and save them in "~/photographs/vacations/<vacation_spot>.zip" for each vacation spot, and then delete all vacation spot sub-directories. Here, <vacation_spot> is the name of the vacation spot as it appears in the sub-directory name.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_unseen/7d7fbf6_1__00/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_unseen/7d7fbf6_1__00/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未查规格且调用不存在的API，执行失败。 |
| 2 | P | P | N | N | N | P | N | P |  |
| 3 | F | N | N | N | N | P | N | F | 缺少访问令牌且调用前未查完整规格。 |
| 4 | F | N | N | N | N | P | N | F | 缺少必需登录参数且调用前未查完整规格。 |
| 5 | P | P | N | N | N | P | N | F | 调用凭据接口前未查完整规格。 |
| 6 | P | N | P | N | N | P | N | F | 调用登录接口前未查完整规格。 |
| 7 | F | N | N | N | N | F | N | F | 忽略已取得的令牌，再次无令牌调用且未查规格。 |
| 8 | P | P | P | N | N | P | N | F | 成功取数，但调用前未查完整接口规格。 |
| 9 | P | P | P | N | N | N | N | F | 成功读取目标目录，但未查完整接口规格。 |
| 10 | F | N | F | F | N | N | N | F | 参数名错误，且尾斜杠使地点名解析为空。 |
| 11 | P | P | N | N | N | P | N | P |  |
| 12 | F | N | F | F | F | P | N | P | 发生路径冲突，地点名为空且压缩包目录错误。 |
| 13 | F | N | F | F | F | P | N | P | 地点名仍为空且目标目录错误，压缩操作失败。 |
| 14 | P | P | P | N | N | P | N | F | 成功核查目录状态，但未查该接口完整规格。 |
| 15 | P | P | P | N | N | P | N | F | 成功核查其余目录，但相关接口规格未查全。 |
| 16 | P | N | P | F | F | P | N | P | 压缩包被写到错误目录，并覆盖了已有文件。 |
| 17 | F | F | F | F | N | N | F | F | 无代码导致终止；错称完成且未调用complete_task。 |

## 相同输入独立重复调用

### 302c169_2__02（官方结果：成功）

I am going on a vacation. Move my wake-up phone alarm to 40 minutes earlier and disable the rest.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_repeat/302c169_2__02/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_repeat/302c169_2__02/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 未查规格且缺少令牌，查询返回401。 |
| 2 | F | N | N | N | N | P | N | F | 调用不存在且未查规格的接口，报无此API。 |
| 3 | P | P | P | N | N | P | N | F | 调用密码接口前未查其规格。 |
| 4 | F | N | F | F | N | N | N | F | 邮箱被误作手机号用户名，且调用前未查规格。 |
| 5 | P | P | N | N | N | P | N | P |  |
| 6 | P | P | P | P | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | F | 调用闹钟查询接口前未查其规格。 |
| 8 | P | P | P | P | N | N | N | P |  |
| 9 | P | N | P | P | N | N | N | P |  |
| 10 | P | N | P | P | P | N | N | F | 调用闹钟更新接口前未查其规格。 |
| 11 | P | N | P | N | N | N | P | F | 调用任务完成接口前未查完整规格。 |

### cf6abd2_2__01（官方结果：成功）

Mark "Taking a solo backpacking trip" in my Bucket List Simple Note as not done.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_repeat/cf6abd2_2__01/input.json) · [原始判断](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/runs/v3_repeat/cf6abd2_2__01/judgement.json)

| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | F | N | N | N | N | N | N | F | 未查规格且缺少令牌，搜索返回401。 |
| 4 | F | N | N | N | N | P | N | F | 未查规格且漏传用户名和密码，返回422。 |
| 5 | P | P | N | N | N | P | N | F | 未先查看账户密码接口的完整规格。 |
| 6 | F | N | N | N | N | P | N | F | 调用不存在的接口，且未先查看规格。 |
| 7 | F | N | N | N | N | F | N | F | 再次猜测不存在的接口，未据报错查规格。 |
| 8 | P | P | N | N | N | P | N | F | 未先查看个人资料接口的完整规格。 |
| 9 | P | P | P | P | N | P | N | F | 未先查看登录接口的完整规格。 |
| 10 | P | P | P | N | N | P | N | F | 未先查看搜索接口的完整规格。 |
| 11 | P | P | P | N | N | P | N | F | 未先查看搜索接口的完整规格。 |
| 12 | P | P | P | N | N | F | N | F | 无信息变化却重复相同查询，且未查接口规格。 |
| 13 | P | P | P | N | N | F | N | F | 已有候选笔记仍作无效重复搜索，且未查规格。 |
| 14 | P | P | P | N | N | F | N | F | 再次重复搜索已知候选笔记，且未查规格。 |
| 15 | P | P | P | P | N | P | N | F | 未先查看详情接口的完整规格。 |
| 16 | P | N | P | P | P | N | N | F | 未先查看更新接口的完整规格。 |
| 17 | P | N | P | N | N | N | P | F | 未先查看complete_task完整规格。 |

