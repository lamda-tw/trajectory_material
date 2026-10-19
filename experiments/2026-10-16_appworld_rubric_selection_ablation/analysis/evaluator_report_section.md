## 1.1 官方 evaluator 检查项对比（2026-10-19 补充）

此前报告主要统计整题全通过，只在个别轨迹案例中列出测试通过数；这里补充全部正式运行的逐检查项比较。数据来自保存的官方 `evaluation/report.md`，不是训练用 R1–R8 rubric，也不是重新生成的评分。分析核对了 15 次微调评测和 1 次原始模型评测的 912 份报告，与轨迹 SHA256、官方通过数、整题成功状态和 SUMMARY 的平均通过比例逐一一致；同一题在所有运行中的检查项集合也一致。

**口径。** Macro 是先算每题通过检查数/总检查数，再对 57 题和三个 seed 等权平均；Micro 是全部通过检查数/全部检查数，会给检查较多的题更大权重。下表逐 seed 使用 Macro。检查项属于终态要求，彼此相关，不当作独立样本做显著性检验；通过率不是官方整题成功率，也不一定等于业务完成百分比。Base 只有一次评测，不复制成三个 seed。

| 组别 | seed 20261015 | seed 20261016 | seed 20261017 | Macro | 对 Random | Micro（通过/总数） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Random | 41.58% | 42.03% | 38.64% | 40.75% | +0.00 pp | 35.28%（308/873） |
| Net3 | 35.13% | 38.11% | 43.05% | 38.76% | -1.99 pp | 33.68%（294/873） |
| Pass4 | 40.72% | 38.69% | 48.49% | 42.63% | +1.88 pp | 37.34%（326/873） |
| ZeroFail3 | 51.91% | 47.33% | 53.91% | 51.05% | +10.29 pp | 46.51%（406/873） |
| HighFail3 | 33.87% | 33.83% | 36.13% | 34.61% | -6.14 pp | 27.95%（244/873） |
| Base | — | — | — | 43.53% | +2.78 pp | 41.24%（120/291） |

每次 DEV57 包含 291 条检查（不同题为 2–10 条），三次共 873 条检查结果。以下按同 seed、同题、规范化空白后的同一 requirement 文本配对；新增通过与丢失通过可以发生在同一道题中，净增不等于新增通过。`4fab96f` 家族有两条官方描述相同的检查，分别核验消息映射和 payment_request_id 映射；已用报告内失败代码区分身份，48 份报告中这两条均失败，未按通过/失败展示顺序硬配对。

| 对 Random | 新增通过检查 | 丢失通过检查 | 净增 | 两组都失败的题数 | 这些题内净增检查 | 这些题的平均通过率差 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Net3 | 83 | 97 | -14 | 146/171 | -18 | -2.58 pp |
| Pass4 | 108 | 90 | +18 | 141/171 | +3 | +0.49 pp |
| ZeroFail3 | 174 | 76 | +98 | 133/171 | +36 | +4.44 pp |
| HighFail3 | 55 | 119 | -64 | 149/171 | -47 | -5.36 pp |

“两组都失败”是各比较事后形成的不同子集，只用于描述整题指标隐藏的进退，不能跨组当作共同测试集排名。完整的逐 seed、逐题新增/丢失检查保存在配对 CSV。

### 部分通过和家族分布

| 组别 | 零检查通过 | 部分检查通过 | 全部通过 |
| --- | ---: | ---: | ---: |
| Random | 16 | 141 | 14 |
| Net3 | 19 | 138 | 14 |
| Pass4 | 12 | 141 | 18 |
| ZeroFail3 | 16 | 125 | 30 |
| HighFail3 | 21 | 141 | 9 |
| Base | 3 | 53 | 1 |

微调各组分母为 171 个题次，Base 为 57。下表列出全部 19 个家族的 Macro 检查通过率，每个微调单元含 3 题 × 3 seed，Base 含 3 题。最后一列是 ZeroFail3 对 Random 的检查通过数净增。

| 家族 | Random | Net3 | Pass4 | ZeroFail3 | HighFail3 | Base | ZeroFail3 差值 | 净增检查 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| d4e9306 | 27.8% | 20.4% | 16.7% | 90.7% | 27.8% | 55.6% | +62.96 pp | +34 |
| 0d8a4ee | 26.7% | 33.3% | 46.7% | 57.8% | 20.0% | 20.0% | +31.11 pp | +14 |
| 6171bbc | 31.7% | 20.6% | 42.9% | 52.4% | 39.7% | 47.6% | +20.63 pp | +13 |
| b119b1f | 48.1% | 59.3% | 63.0% | 68.5% | 33.3% | 88.9% | +20.37 pp | +11 |
| 68ee2c9 | 26.7% | 26.7% | 33.3% | 46.7% | 28.9% | 53.3% | +20.00 pp | +9 |
| df61dc5 | 39.7% | 47.6% | 47.6% | 55.6% | 28.6% | 42.9% | +15.87 pp | +10 |
| 37a8675 | 0.0% | 7.4% | 3.7% | 13.0% | 0.0% | 33.3% | +12.96 pp | +7 |
| 23cf851 | 72.2% | 72.2% | 72.2% | 83.3% | 66.7% | 50.0% | +11.11 pp | +2 |
| 6bdbc26 | 66.7% | 72.2% | 77.8% | 77.8% | 61.1% | 50.0% | +11.11 pp | +2 |
| 4fab96f | 13.9% | 16.7% | 18.1% | 22.2% | 25.0% | 16.7% | +8.33 pp | +6 |
| fac291d | 61.1% | 50.0% | 50.0% | 66.7% | 66.7% | 50.0% | +5.56 pp | +1 |
| 530b157 | 26.7% | 37.8% | 21.1% | 30.0% | 11.1% | 30.0% | +3.33 pp | +3 |
| 383cbac | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | +0.00 pp | +0 |
| 4ec8de5 | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | +0.00 pp | +0 |
| 50e1ac9 | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | 50.0% | +0.00 pp | +0 |
| 6c2c621 | 43.1% | 37.5% | 38.9% | 43.1% | 29.2% | 50.0% | +0.00 pp | +0 |
| 3ab5b8b | 48.1% | 40.7% | 38.9% | 40.7% | 38.9% | 38.9% | -7.41 pp | -4 |
| 396c5a2 | 29.6% | 1.9% | 42.6% | 20.4% | 1.9% | 16.7% | -9.26 pp | -5 |
| 57c3486 | 62.2% | 42.2% | 46.7% | 51.1% | 28.9% | 33.3% | -11.11 pp | -5 |

### 具体是哪条检查改变了

以下分别列出 ZeroFail3 相对 Random 净增最多和净减最多的 5 条家族内 requirement（并列按家族和文本排序）。同族的不同题只有 requirement 文本相同时才合并；每个单元为通过次数/检查次数。完整 CSV 包含所有组及所有 requirement。

| 家族 | 官方 requirement | Random | ZeroFail3 | 净增 |
| --- | --- | ---: | ---: | ---: |
| d4e9306 | assert artist_ids from added artists match union of private_data.to_be_followed_artist_ids_by_songs and private_data.to_be_followed_artist_ids_by_albums. | 0/9 | 8/9 | +8 |
| d4e9306 | assert private_data.to_be_followed_artist_ids_by_albums artists have been newly followed. | 0/9 | 8/9 | +8 |
| d4e9306 | assert private_data.to_be_followed_artist_ids_by_songs artists have been newly followed. | 0/9 | 8/9 | +8 |
| 0d8a4ee | assert all added global text messages have message public_data.message_text (normalize_text=True). | 1/9 | 6/9 | +5 |
| 0d8a4ee | assert model changes match phone.GlobalTextMessage, phone.UserTextMessage | 1/9 | 6/9 | +5 |
| 57c3486 | assert model changes match spotify.Song, spotify.SongLike. | 9/9 | 5/9 | -4 |
| 396c5a2 | assert answers match. | 4/9 | 1/9 | -3 |
| 3ab5b8b | assert all added downloaded song_ids are in private_data.liked_song_ids | 4/9 | 2/9 | -2 |
| 3ab5b8b | assert model changes match spotify.UserDownloadedSong. | 8/9 | 6/9 | -2 |
| 57c3486 | assert all newly song likes are from artists that main_user follows via models.changed_records | 6/9 | 4/9 | -2 |

**这层证据如何改变解释：**

1. ZeroFail3 的 Macro 从 Random 的 40.75% 升至 51.05%（+10.29 pp），Micro 从 35.28% 升至 46.51%（+11.23 pp），三个 seed 的 Macro 都更高。新增通过 174 条、丢失 76 条，净增 98 条；两组都失败的 133 个题次内仍净增 36 条、平均通过率高 4.44 pp。因此收益不仅体现为少数题跨过“全通过”门槛，也包括未完成任务中的部分要求改善。
2. Net3 虽然整题成功率与 Random 相同，Macro 低 1.99 pp、净少通过 14 条，提示整题指标掩盖了部分完成度下降。Pass4 只有 +1.88 pp，逐 seed 为两次低于 Random、一次高于 Random，仍不稳定。
3. HighFail3 的 Macro 为 34.61%，低于 Random 的 40.75%，也低于 Base 的 43.53%；Micro 同样低于二者。原报告“整题成功率未低于原始模型”的观察仍成立，但不能据此推断细粒度能力未退化。事实上，除 ZeroFail3 外，其余微调组的平均 Macro 和 Micro 均低于这次 Base；Base 只有一次运行，该比较仍是描述性的。
4. ZeroFail3 在 12/19 个家族的 Macro 上升、4 个持平、3 个下降。d4e9306 贡献 34/98（34.7%）的净增检查，仍有集中性，但其余家族合计也净增 64 条。该家族三个关键业务要求——按歌曲关注、按专辑关注、关注集合恰好为二者并集——均由 0/9 升至 8/9；说明改善确实触及业务终态覆盖。另一方面，57c3486 的改动的数据类型检查由 9/9 降至 5/9，且 3ab5b8b 的下载歌曲范围检查也退化，不能说 ZeroFail3 对所有业务要求都更好。
5. 部分通过不必然代表推进了业务。例如 383cbac、4ec8de5、50e1ac9 在所有组中均为 50%：不修改数据库的要求通过，答案检查全部失败。必须结合具体 requirement 理解通过率，不能把这 50% 当作完成了一半业务；本分析也未证明每条通过检查是模型行动带来的新增进展。

可复核文件：[汇总](analysis/evaluator_summary.json)、[逐题部分完成度](analysis/evaluator_tasks.csv)、[逐条检查及原始报告路径](analysis/evaluator_checks.csv)、[同 seed 配对得失](analysis/evaluator_pairs.csv)、[全部家族](analysis/evaluator_families.csv)、[全部 requirement](analysis/evaluator_requirements.csv)。复现：依次运行 `python scripts/analyze_evaluators.py`、`python scripts/analyze_evaluator_rubric_links.py`、`python scripts/write_final_report.py`（工作目录为本实验目录）。只做本地 CPU 分析，不重跑模型或 evaluator。
