# 第一轮最终 LoRA：DEV57 评测

更新时间：2026-10-16T09:35:05.858177+08:00

状态：complete；进度：57/57；TGC=20/57=35.09%；SGC=2/19=10.53%。

与用户指定的训练前历史基线相比，TGC 下降5.26个百分点，SGC下降10.53个百分点。详见 [逐题得失、场景统计及协议差异](BASELINE_COMPARISON.md)。

协议：每题1条轨迹，temperature=0，seed=100，最多50步，每动作最多3000 token，上下文32000，thinking=False。仅物理GPU1。

模型 SHA-256：`c8f268b58dea9fc79ae53cfc362dede13edd965b604a4e702c2b6966ddf211d9`。

官方任务失败计入分母；仅基础设施故障重试。此次没有运行初始模型对照，不据此声称相对提升。

| 题目 | 官方成功 | 测试通过数 | 步数 | 结束原因 | 生成token |
| --- | --- | --- | ---: | --- | ---: |
| [50e1ac9_1](trajectories/50e1ac9_1.json) | FAIL | 1/2 | 12 | completion_api | 954 |
| [50e1ac9_2](trajectories/50e1ac9_2.json) | FAIL | 1/2 | 19 | completion_api | 1494 |
| [50e1ac9_3](trajectories/50e1ac9_3.json) | PASS | 2/2 | 14 | completion_api | 1957 |
| [fac291d_1](trajectories/fac291d_1.json) | PASS | 2/2 | 11 | completion_api | 851 |
| [fac291d_2](trajectories/fac291d_2.json) | PASS | 2/2 | 11 | completion_api | 831 |
| [fac291d_3](trajectories/fac291d_3.json) | PASS | 2/2 | 9 | completion_api | 723 |
| [530b157_1](trajectories/530b157_1.json) | FAIL | 9/10 | 16 | completion_api | 1201 |
| [530b157_2](trajectories/530b157_2.json) | FAIL | 3/10 | 26 | completion_api | 2704 |
| [530b157_3](trajectories/530b157_3.json) | FAIL | 9/10 | 21 | completion_api | 1635 |
| [4ec8de5_1](trajectories/4ec8de5_1.json) | FAIL | 1/2 | 13 | completion_api | 1611 |
| [4ec8de5_2](trajectories/4ec8de5_2.json) | FAIL | 1/2 | 15 | completion_api | 1558 |
| [4ec8de5_3](trajectories/4ec8de5_3.json) | FAIL | 1/2 | 12 | completion_api | 966 |
| [b119b1f_1](trajectories/b119b1f_1.json) | PASS | 6/6 | 13 | completion_api | 957 |
| [b119b1f_2](trajectories/b119b1f_2.json) | FAIL | 5/6 | 12 | completion_api | 766 |
| [b119b1f_3](trajectories/b119b1f_3.json) | FAIL | 4/6 | 10 | completion_api | 550 |
| [d4e9306_1](trajectories/d4e9306_1.json) | PASS | 6/6 | 14 | completion_api | 1680 |
| [d4e9306_2](trajectories/d4e9306_2.json) | FAIL | 2/6 | 13 | completion_api | 1107 |
| [d4e9306_3](trajectories/d4e9306_3.json) | PASS | 6/6 | 11 | completion_api | 979 |
| [0d8a4ee_1](trajectories/0d8a4ee_1.json) | FAIL | 4/5 | 11 | completion_api | 652 |
| [0d8a4ee_2](trajectories/0d8a4ee_2.json) | FAIL | 4/5 | 13 | completion_api | 775 |
| [0d8a4ee_3](trajectories/0d8a4ee_3.json) | FAIL | 4/5 | 13 | completion_api | 709 |
| [37a8675_1](trajectories/37a8675_1.json) | FAIL | 0/6 | 20 | completion_api | 1579 |
| [37a8675_2](trajectories/37a8675_2.json) | FAIL | 0/6 | 44 | completion_api | 3224 |
| [37a8675_3](trajectories/37a8675_3.json) | FAIL | 1/6 | 23 | completion_api | 1660 |
| [3ab5b8b_1](trajectories/3ab5b8b_1.json) | FAIL | 3/6 | 10 | completion_api | 647 |
| [3ab5b8b_2](trajectories/3ab5b8b_2.json) | FAIL | 4/6 | 14 | completion_api | 1131 |
| [3ab5b8b_3](trajectories/3ab5b8b_3.json) | PASS | 6/6 | 16 | completion_api | 1417 |
| [df61dc5_1](trajectories/df61dc5_1.json) | PASS | 7/7 | 18 | completion_api | 1595 |
| [df61dc5_2](trajectories/df61dc5_2.json) | FAIL | 2/7 | 25 | context_limit | 13661 |
| [df61dc5_3](trajectories/df61dc5_3.json) | FAIL | 2/7 | 23 | context_limit | 12794 |
| [383cbac_1](trajectories/383cbac_1.json) | FAIL | 1/2 | 23 | context_limit | 16896 |
| [383cbac_2](trajectories/383cbac_2.json) | FAIL | 1/2 | 19 | completion_api | 5562 |
| [383cbac_3](trajectories/383cbac_3.json) | FAIL | 1/2 | 28 | context_limit | 14078 |
| [23cf851_1](trajectories/23cf851_1.json) | FAIL | 1/2 | 8 | completion_api | 565 |
| [23cf851_2](trajectories/23cf851_2.json) | FAIL | 0/2 | 38 | context_limit | 4069 |
| [23cf851_3](trajectories/23cf851_3.json) | PASS | 2/2 | 11 | completion_api | 1138 |
| [57c3486_1](trajectories/57c3486_1.json) | FAIL | 1/5 | 13 | context_limit | 858 |
| [57c3486_2](trajectories/57c3486_2.json) | PASS | 5/5 | 14 | completion_api | 825 |
| [57c3486_3](trajectories/57c3486_3.json) | PASS | 5/5 | 27 | completion_api | 2654 |
| [68ee2c9_1](trajectories/68ee2c9_1.json) | PASS | 5/5 | 24 | completion_api | 2321 |
| [68ee2c9_2](trajectories/68ee2c9_2.json) | FAIL | 3/5 | 19 | completion_api | 1655 |
| [68ee2c9_3](trajectories/68ee2c9_3.json) | FAIL | 3/5 | 21 | completion_api | 2308 |
| [6bdbc26_1](trajectories/6bdbc26_1.json) | FAIL | 1/2 | 17 | completion_api | 1251 |
| [6bdbc26_2](trajectories/6bdbc26_2.json) | FAIL | 1/2 | 10 | completion_api | 578 |
| [6bdbc26_3](trajectories/6bdbc26_3.json) | PASS | 2/2 | 12 | completion_api | 627 |
| [6171bbc_1](trajectories/6171bbc_1.json) | PASS | 7/7 | 17 | completion_api | 1354 |
| [6171bbc_2](trajectories/6171bbc_2.json) | FAIL | 3/7 | 44 | context_limit | 19919 |
| [6171bbc_3](trajectories/6171bbc_3.json) | FAIL | 1/7 | 45 | context_limit | 12188 |
| [6c2c621_1](trajectories/6c2c621_1.json) | PASS | 8/8 | 11 | completion_api | 1085 |
| [6c2c621_2](trajectories/6c2c621_2.json) | FAIL | 1/8 | 28 | context_limit | 14291 |
| [6c2c621_3](trajectories/6c2c621_3.json) | PASS | 8/8 | 18 | completion_api | 1563 |
| [396c5a2_1](trajectories/396c5a2_1.json) | PASS | 6/6 | 10 | completion_api | 647 |
| [396c5a2_2](trajectories/396c5a2_2.json) | PASS | 6/6 | 11 | completion_api | 690 |
| [396c5a2_3](trajectories/396c5a2_3.json) | PASS | 6/6 | 11 | completion_api | 689 |
| [4fab96f_1](trajectories/4fab96f_1.json) | FAIL | 2/8 | 18 | completion_api | 1387 |
| [4fab96f_2](trajectories/4fab96f_2.json) | FAIL | 2/8 | 25 | completion_api | 2507 |
| [4fab96f_3](trajectories/4fab96f_3.json) | FAIL | 2/8 | 22 | completion_api | 1573 |
