# 预先抽定12条完整轨迹：原始评分

本文件只展示原始标签与短依据；不输出凭据或完整观察。

## 287e338_1__04

Name the artist most recommended to me on Spotify.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/287e338_1__04/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/287e338_1__04/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | P | N | N | N | N | F | 未先查看show_account_passwords接口完整规格。 |
| 2 | P | F | F | F | N | N | N | P | 将播放列表所有者误当艺术家，证据与统计规则均错误。 |
| 3 | F | N | F | F | N | P | N | F | 把歌曲ID列表当单个ID并调用不存在且未查规格的接口。 |
| 4 | P | F | F | F | N | F | N | P | 已知所有者不是艺术家仍重复同一错误推断。 |
| 5 | P | P | U | N | N | P | N | P | 未核实是否有推荐接口即称无直接推荐数据。 |
| 6 | P | P | N | N | N | P | N | F | 调用show_recommendations前未查看完整接口规格。 |
| 7 | P | F | F | F | N | N | N | P | 只统计每首歌首位艺术家，遗漏可见的合作艺术家。 |
| 8 | P | F | P | P | N | N | P | F | 交付依据遗漏合作艺术家，且未查看完成接口规格。 |

## aa8502b_3__00

Follow all the artists who have sung at least one song I have liked on Spotify.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/aa8502b_3__00/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/aa8502b_3__00/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | P | N | N | N | N | F | 调用账户密码接口前未查完整规格。 |
| 3 | P | P | P | N | N | N | N | P |  |
| 4 | P | P | N | N | N | N | N | P |  |
| 5 | P | P | N | N | N | N | N | P |  |
| 6 | P | P | P | N | N | N | N | P |  |
| 7 | P | P | F | P | N | N | N | P | 文本捏造的艺人名单与实际输出不符。 |
| 8 | P | P | N | N | N | N | N | P |  |
| 9 | P | P | N | N | N | N | N | P |  |
| 10 | P | P | P | P | N | N | N | P |  |
| 11 | F | N | P | P | P | N | N | P | 首个重复关注引发异常，循环提前终止。 |
| 12 | F | F | F | F | P | F | N | P | 错误用粉丝数判断关注状态，并重复已知失败操作。 |
| 13 | F | F | F | F | P | F | N | F | 未查接口规格且错误判定关注状态，操作再次失败。 |
| 14 | P | P | N | N | N | F | N | P | 重复查询已知接口列表，未获得恢复所需新信息。 |
| 15 | F | F | F | F | P | F | N | F | 仍未查接口规格并重复相同的错误关注判断。 |
| 16 | F | N | F | F | P | F | N | P | 明知存在重复关注仍原样重试，首项再次失败。 |
| 17 | F | F | F | F | P | F | N | F | 未查列表接口规格，以失败查询推断未关注。 |
| 18 | F | N | N | P | P | P | N | P | 异常对象无所用属性，处理分支再次报错。 |
| 19 | P | P | P | P | P | P | N | P |  |
| 20 | P | N | P | N | N | N | P | F | 调用完成接口前未查完整规格。 |

## e85d92a_1__00

What is the title of the most played song by Velvet Echo on Spotify.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/e85d92a_1__00/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/e85d92a_1__00/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | F | N | N | N | N | F | 使用捏造密码登录并触发401，且违反禁止猜测值。 |
| 2 | P | P | P | N | N | P | N | F | 未查show_account_passwords完整规格便调用。 |
| 3 | P | N | P | N | N | P | N | P |  |
| 4 | F | N | P | N | N | N | N | F | search_songs参数不受支持，且未先查完整规格。 |
| 5 | P | P | P | N | N | P | N | P |  |
| 6 | P | P | P | N | N | P | N | F | 未查search_artists规格，且未遍历分页结果。 |
| 7 | P | F | P | N | N | N | N | F | show_artist未返回歌曲，且调用前未查完整规格。 |
| 8 | P | P | P | N | N | P | N | F | 未查search_songs完整规格，也未遍历分页。 |
| 9 | P | U | U | F | N | N | N | N | 仅据首屏且只认首位艺人，无法确定全局最高。 |
| 10 | P | U | U | F | N | N | F | F | 未分页仍提交全局答案，且未查complete_task规格。 |

## 6ea6792_1__03

Accept all pending Venmo payment requests from my roommates and coworkers.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/6ea6792_1__03/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/6ea6792_1__03/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | P | N | N | N | N | P |  |
| 3 | P | P | P | N | N | N | N | P |  |
| 4 | P | P | P | N | N | N | N | P |  |
| 5 | P | P | P | N | N | N | N | F | 调用前未查看该接口完整规格。 |
| 6 | P | P | P | N | N | N | N | F | 调用登录接口前未查看完整规格。 |
| 7 | P | P | P | N | N | N | N | P |  |
| 8 | F | U | P | F | F | N | N | F | 未核实人员关系和分页，且审批缺少令牌并失败。 |
| 9 | P | F | N | N | N | F | N | P | 重印旧登录结果无法验证令牌，也未处理缺参反馈。 |
| 10 | P | U | P | F | U | P | N | F | 未核实联系人关系及后续分页，审批范围证据不足。 |
| 11 | P | U | U | N | N | N | F | F | 未完成联系人和分页核验却宣称完成，且未查接口规格。 |

## ce359b5_1__00

Remove all songs from my Spotify song library and playlists that were released before 2021 year.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/ce359b5_1__00/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/ce359b5_1__00/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | P | N | N | N | N | F | 调用Supervisor接口前未查完整规格。 |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | P | F | F | N | N | N | N | F | 误将播放列表对象按歌曲列表展开，且未查接口规格。 |
| 4 | F | N | U | U | N | N | N | P | 歌曲对象结构无依据，代码因字符串无get方法失败。 |
| 5 | P | P | P | N | N | P | N | F | 有效检查返回结构，但调用前仍未查接口规格。 |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | N | N | N | P | N | P |  |
| 8 | F | N | F | P | N | F | N | P | 已知all_songs结构错误仍复用，字符串索引再次失败。 |
| 9 | P | P | F | N | N | F | N | F | 混淆字符串元素与接口返回对象，并重复无新信息的查询。 |
| 10 | F | N | F | P | N | F | N | P | 忽略刚确认的数据结构，原样重复已知失败代码。 |
| 11 | P | P | F | N | N | F | N | F | 再次混淆对象并重复相同查询，未产生新信息。 |
| 12 | F | N | F | P | N | F | N | P | 再次原样运行已知会失败的错误循环。 |
| 13 | P | P | F | N | N | F | N | F | 再次混淆对象并重复相同查询，未产生新信息。 |
| 14 | F | N | F | P | N | F | N | P | 再次原样运行已知会失败的错误循环。 |
| 15 | P | P | F | N | N | F | N | F | 再次混淆对象并重复相同查询，未产生新信息。 |
| 16 | F | N | F | P | N | F | N | P | 再次原样运行已知会失败的错误循环。 |
| 17 | P | P | P | N | N | P | N | F | 修复了歌曲收集结构，但调用前未查接口规格。 |
| 18 | F | F | F | N | N | N | F | F | 未执行任何删除或complete_task，却宣称全部完成。 |

## afc0fce_1__01

Add a comment, "Thank you!", to all the venmo payments I received from my coworkers in the last 5 days (including today), and like those payments.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/afc0fce_1__01/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/afc0fce_1__01/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | F | N | N | N | F | 接口不存在，且五天范围未按完整自然日计算。 |
| 2 | P | P | N | N | N | P | N | P |  |
| 3 | P | P | N | N | N | P | N | P |  |
| 4 | F | N | N | F | N | P | N | P | 访问令牌未定义，且时间范围多含一天。 |
| 5 | F | N | N | N | N | P | N | F | 密码变量未定义，且调用登录前未查接口规格。 |
| 6 | P | P | P | N | N | P | N | F | 调用凭据接口前未查完整规格。 |
| 7 | P | N | P | N | N | P | N | F | 调用登录接口前未查完整规格。 |
| 8 | P | U | P | F | N | P | N | P | 未遍历分页，且时间范围多含一天。 |
| 9 | P | F | U | F | U | N | N | F | 未核实同事身份或写接口，修改对象及效果不明。 |
| 10 | P | N | F | N | N | N | F | F | 同事筛选和分页均未完成，却宣称成功并结束。 |

## 229360a_3__02

I need to cleanup my Spotify libraries. Keep only those songs and albums in my song and album library, respectively, that I have liked or downloaded, and remove the rest. An album is downloaded if all songs in it are downloaded. Keep my playlist library as is for now.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/229360a_3__02/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/229360a_3__02/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | F | N | N | N | P | 计划仅按下载保留相册，遗漏已点赞相册。 |
| 2 | P | P | P | N | N | N | N | F | 调用Supervisor接口前未查看完整规格。 |
| 3 | P | N | P | N | N | N | N | P |  |
| 4 | P | U | P | N | N | N | N | F | 未先查歌曲库接口规格，完整库覆盖无法确认。 |
| 5 | P | P | N | N | N | N | N | P |  |
| 6 | P | P | N | N | N | N | N | P |  |
| 7 | P | U | P | N | N | N | N | F | 仅取默认首5条点赞歌曲，未按协议遍历分页。 |
| 8 | P | U | P | N | N | N | N | F | 仅取默认首5条下载歌曲，未按协议遍历分页。 |
| 9 | P | U | P | F | N | N | N | P | 列表未翻页，且相册规则漏保留已点赞相册。 |
| 10 | F | F | F | N | N | N | F | F | 无代码和执行证据却伪造结果并称任务完成。 |

## 27e1026_2__00

What is the title of the newest released song in my Spotify account from across my song, album and playlist libraries?

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/27e1026_2__00/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/27e1026_2__00/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | P | N | N | N | N | F | 未查Supervisor密码接口的完整规格。 |
| 2 | P | P | P | N | N | N | N | P |  |
| 3 | P | P | P | N | N | N | N | P |  |
| 4 | F | N | F | P | N | N | N | P | 规格不支持release_date排序，且页限超过20。 |
| 5 | F | N | N | P | N | P | N | P | 虽修复页限，仍使用规格不支持的排序参数。 |
| 6 | F | N | F | F | N | F | N | P | 已知release_date排序无效却原样重试，并错误筛选newest。 |
| 7 | P | P | P | N | N | P | N | P |  |
| 8 | F | N | F | P | N | F | N | P | 再次使用已确认无效的release_date排序。 |
| 9 | P | F | N | F | N | P | N | F | 仅查全局搜索首20项，未覆盖三类库及全部分页。 |
| 10 | P | F | F | P | N | N | N | P | 声称最新为10月29日与结果中的11月8日矛盾，且范围不全。 |
| 11 | P | F | F | U | N | N | N | P | 仅对不完整搜索取最大值，却称检查了全部歌曲。 |
| 12 | P | F | U | U | N | N | F | F | 以未覆盖三类库的未证答案完成，且未查完成接口规格。 |

## c901732_2__01

Play the most listened to song on Spotify from my Woodstock Reimagined: Festival Vibes playlist.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/c901732_2__01/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/c901732_2__01/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | F | 调用监督接口前未查完整规格。 |
| 2 | P | N | P | N | N | N | N | P |  |
| 3 | P | P | P | N | N | N | N | F | 分页接口仅读取默认第一页，违反全量遍历协议。 |
| 4 | P | P | P | N | N | N | N | F | 调用 show_playlist 前未查完整接口规格。 |
| 5 | F | F | F | F | N | N | N | F | 未查规格并调用不存在接口；擅用时长代替收听量，且最长曲目也算错。 |
| 6 | F | N | P | F | N | F | N | F | 未查规格又猜测不存在的接口，且改为播放整张歌单。 |
| 7 | F | N | U | F | N | F | N | F | 再次猜测不存在的接口，曲目为最常听也无证据。 |
| 8 | P | N | F | F | N | F | P | F | 未查接口目录即断言无法播放并提前失败，且未查完成接口规格。 |

## ccb4494_1__02

Like all the songs played so far in my spotify music player queue, including the current one.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/ccb4494_1__02/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/ccb4494_1__02/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | F | N | N | N | N | N | N | P | 访问令牌变量未定义，触发NameError。 |
| 4 | F | N | F | N | N | F | N | F | 捏造占位密码导致登录失败，且未有效恢复。 |
| 5 | P | P | P | N | N | P | N | F | 调用Supervisor接口前未查询完整规格。 |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | P | P | N | N | N | N | P |  |
| 8 | P | P | P | F | F | N | N | F | 错误点赞当前曲目之后的歌曲，且未查点赞接口规格。 |
| 9 | P | N | N | N | N | N | F | F | 已知点赞范围错误仍称完成，且未查完成接口规格。 |

## e3d6c94_3__05

Add all spotify-recommended R&B songs released in this year to a new "R&B Recommendation" playlist.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/e3d6c94_3__05/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/e3d6c94_3__05/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | P | P | N | N | N | N | N | P |  |
| 2 | P | P | N | N | N | N | N | P |  |
| 3 | F | N | N | N | N | N | N | P | 访问令牌变量未定义，执行以NameError终止。 |
| 4 | F | N | N | N | N | P | N | F | 擅自使用虚构密码，登录返回无效凭据。 |
| 5 | P | P | P | N | N | P | N | F | 调用前未查看Supervisor密码接口规格。 |
| 6 | P | P | P | N | N | P | N | P |  |
| 7 | P | F | U | F | N | N | N | P | 结果缺少流派和发行年份，无法认定均符合条件。 |
| 8 | F | N | U | N | F | N | N | F | 参数名错误且未查规格，播放列表未创建。 |
| 9 | P | N | P | N | P | P | N | F | 仅依据报错修正，仍未查看创建接口完整规格。 |
| 10 | P | F | U | F | U | N | N | F | 未核验流派和年份便添加全部推荐，且未查接口规格。 |
| 11 | P | N | U | N | N | N | U | F | 缺少歌曲条件核验和当前年份证据，仍宣称完成。 |

## 3c13f5a_2__04

I paid for our last month's internet bill. Its amount is supposed to be shared equally among my roommates and me. Make venmo requests to my roommates, with a description note, "internet bill for the last month.". The bill receipt is in my file system.

[完整输入](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/3c13f5a_2__04/input.json) · [原始评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/runs/scoring/3c13f5a_2__04/judgement.json)

| step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 原始依据 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | F | N | N | N | N | N | N | F | 调用不存在的接口，且未先查完整规格。 |
| 2 | F | N | P | N | N | F | N | F | 再次猜测不存在的接口，未依据反馈查规格。 |
| 3 | P | P | P | N | N | P | N | P |  |
| 4 | F | N | F | N | N | F | N | F | 忽略可列目录的接口并猜测文件名，参数也错误。 |
| 5 | F | N | P | N | N | P | N | F | 修正参数但缺少认证，且仍未查完整规格。 |
| 6 | F | N | F | N | N | F | N | F | 使用捏造密码登录失败，未先获取真实凭据。 |
| 7 | P | P | P | N | N | P | N | F | 未先查看账户密码接口的完整规格。 |
| 8 | P | N | P | N | N | P | N | F | 登录成功，但未先查看登录接口完整规格。 |
| 9 | P | P | P | N | N | P | N | F | 文件检查成功，但未先查看接口完整规格。 |
| 10 | P | P | P | N | N | P | N | F | 目录读取成功，但未先查看接口完整规格。 |
| 11 | P | P | P | U | N | F | N | F | 未取当前日期，且重复读取已展示的同一目录内容。 |
| 12 | P | P | P | U | N | N | N | F | 未取当前日期，无法确认该文件确为上月账单。 |
| 13 | P | P | P | U | N | N | N | P | 虽确认文件金额，但缺少当前日期以确认目标月份。 |
| 14 | F | N | F | N | N | N | N | F | 参数错误且使用捏造令牌，未先查完整规格。 |
| 15 | F | N | F | N | N | P | N | F | 修正查询参数后仍使用已知无效的虚构令牌。 |
| 16 | P | P | P | N | N | P | N | F | 成功取得密码，但未先查看接口完整规格。 |
| 17 | F | N | U | N | N | P | N | F | 登录失败，用户名格式是否正确尚无规格证据。 |
| 18 | P | P | P | N | N | F | N | F | 重复读取相同密码，未处理已知登录失败原因。 |
| 19 | F | N | U | N | N | F | N | F | 原样重复已失败的凭据组合，未获得新信息。 |
| 20 | P | P | P | N | N | F | N | F | 再次重复读取同一密码，未推进故障定位。 |
| 21 | F | N | U | N | N | F | N | F | 原样重复已失败的登录调用。 |
| 22 | P | P | P | N | N | F | N | F | 再次重复读取同一密码，未推进故障定位。 |
| 23 | F | N | U | N | N | F | N | F | 原样重复已失败的登录调用。 |
| 24 | P | P | P | N | N | F | N | F | 再次重复读取同一密码，未推进故障定位。 |
| 25 | F | N | U | N | N | F | N | F | 原样重复已失败的登录调用。 |
| 26 | F | N | F | N | N | P | N | F | 使用错误参数和虚构令牌，但尝试了新的排查路径。 |
| 27 | F | N | F | N | N | P | N | F | 修正号码参数后仍传入接口不接受的虚构令牌。 |
| 28 | P | P | P | N | N | P | N | F | 资料读取成功，但未先查看接口完整规格。 |
| 29 | F | N | P | N | N | F | N | F | 已知联系人查询需认证却再次省略令牌。 |
| 30 | P | P | P | N | N | F | N | F | 重复读取同一密码，未处理登录失败原因。 |
| 31 | F | N | U | N | N | F | N | F | 再次原样提交已知失败的登录凭据。 |
| 32 | P | F | P | N | N | F | N | F | 重复公开资料查询不能验证登录用户名或认证问题。 |
| 33 | F | N | F | N | N | F | N | F | 把密码当访问令牌，混淆凭据字段并重复已知错误。 |
| 34 | P | F | P | N | N | F | N | F | 重复公开资料查询，未提供解决认证问题的新证据。 |
| 35 | F | N | F | N | N | F | N | F | 再次把密码当访问令牌，重复已知错误。 |
| 36 | F | N | U | N | N | F | N | F | 再次原样提交已知失败的登录凭据。 |
| 37 | P | P | P | N | N | F | N | F | 再次重复读取同一密码，未推进故障定位。 |
| 38 | F | N | U | N | N | F | N | F | 再次原样提交已知失败的登录凭据。 |
| 39 | P | F | P | N | N | F | N | F | 重复公开资料查询，未提供解决认证问题的新证据。 |
| 40 | F | N | F | N | N | F | N | F | 再次把密码当访问令牌，重复已知错误。 |
| 41 | F | F | F | F | N | F | N | F | 把本人号码臆认作室友并拟发送全额付款，接口也不存在。 |
| 42 | P | P | P | N | N | P | N | P |  |
| 43 | F | F | F | F | N | F | N | F | 仍臆认本人为室友，选择付款而非请求且金额未均分。 |
| 44 | F | F | F | F | N | P | N | F | 用本人号码搜索室友无依据，且未认证或查看完整规格。 |
| 45 | P | P | P | N | N | P | N | F | 成功取得Venmo密码，但未先查看接口完整规格。 |
| 46 | P | N | P | N | N | P | N | F | 登录成功，但未先查看登录接口完整规格。 |
| 47 | P | F | F | N | N | P | N | F | 用本人号码所得用户不能证明是室友，且未处理分页。 |
| 48 | P | F | F | F | F | N | N | F | 向任意三人各发送182美元付款，既非请求也未均分。 |
| 49 | P | F | F | F | N | N | F | F | 实际发送的是错误付款而非均分请求，却宣称完成。 |

