# 已完成任务即时官方评分与接口审计

- 已完成并评分：168/168
- 官方成功：12
- 官方失败：156
- evaluator 错误：0
- LM 调用：2859
- 真实 AppWorld API 调用：6926
- `message.content=null`：80（涉及 45 题）
- 其中纯 reasoning 长度截断：80（涉及 45 题）
- 无法由长度截断解释的 `content=null`：0（涉及 0 题）
- `finish_reason=length`：110（涉及 58 题）
- 响应格式异常跨 scenario 数：3；系统性故障判定：是
- `message.content` 空字符串：3（涉及 3 题）
- `No code available to execute`：1025（涉及 76 题）
- 含 `complete_task` action：144 题
- 含 Python 执行错误：143 题

| task | 官方结果 | 条件通过 | LM | content=null | 纯reasoning截断 | 无法解释null | no-code | API | complete_task |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 3d9a636_1 | failed | 2/5 | 12 | 0 | 0 | 0 | 0 | 35 | 3 |
| 3d9a636_2 | failed | 2/5 | 19 | 0 | 0 | 0 | 0 | 76 | 1 |
| 3d9a636_3 | failed | 1/5 | 6 | 0 | 0 | 0 | 0 | 6 | 1 |
| fd1f8fa_1 | failed | 1/5 | 3 | 0 | 0 | 0 | 0 | 8 | 1 |
| fd1f8fa_2 | failed | 3/5 | 50 | 0 | 0 | 0 | 46 | 27 | 0 |
| fd1f8fa_3 | failed | 0/5 | 4 | 0 | 0 | 0 | 0 | 8 | 1 |
| 325d6ec_1 | failed | 1/5 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 325d6ec_2 | failed | 3/5 | 50 | 0 | 0 | 0 | 18 | 1043 | 0 |
| 325d6ec_3 | failed | 1/5 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 29a7b7e_1 | success | 4/4 | 16 | 0 | 0 | 0 | 2 | 66 | 1 |
| 29a7b7e_2 | failed | 3/4 | 31 | 14 | 14 | 0 | 15 | 64 | 1 |
| 29a7b7e_3 | failed | 1/4 | 8 | 2 | 2 | 0 | 2 | 6 | 1 |
| 21abae1_1 | failed | 1/2 | 9 | 0 | 0 | 0 | 0 | 7 | 1 |
| 21abae1_2 | success | 2/2 | 7 | 0 | 0 | 0 | 0 | 9 | 1 |
| 21abae1_3 | failed | 1/2 | 50 | 0 | 0 | 0 | 36 | 94 | 0 |
| 634f342_1 | failed | 0/7 | 34 | 0 | 0 | 0 | 0 | 56 | 61 |
| 634f342_2 | failed | 0/7 | 50 | 0 | 0 | 0 | 50 | 0 | 0 |
| 634f342_3 | failed | 1/7 | 6 | 0 | 0 | 0 | 0 | 6 | 1 |
| 8749218_1 | failed | 1/6 | 3 | 0 | 0 | 0 | 0 | 5 | 1 |
| 8749218_2 | failed | 2/6 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 8749218_3 | failed | 1/6 | 4 | 0 | 0 | 0 | 0 | 10 | 3 |
| 2d9f728_1 | failed | 1/10 | 16 | 1 | 1 | 0 | 4 | 20 | 1 |
| 2d9f728_2 | failed | 2/10 | 10 | 3 | 3 | 0 | 4 | 4 | 1 |
| 2d9f728_3 | failed | 4/10 | 50 | 3 | 3 | 0 | 31 | 86 | 0 |
| 6f4b9a5_1 | failed | 1/8 | 50 | 2 | 2 | 0 | 44 | 6 | 0 |
| 6f4b9a5_2 | failed | 2/8 | 9 | 0 | 0 | 0 | 0 | 5 | 3 |
| 6f4b9a5_3 | failed | 2/8 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| d6ac34d_1 | failed | 3/9 | 12 | 1 | 1 | 0 | 1 | 22 | 1 |
| d6ac34d_2 | failed | 7/9 | 14 | 0 | 0 | 0 | 0 | 13 | 1 |
| d6ac34d_3 | failed | 7/9 | 9 | 0 | 0 | 0 | 0 | 10 | 1 |
| 0d01c76_1 | failed | 2/6 | 8 | 0 | 0 | 0 | 0 | 11 | 1 |
| 0d01c76_2 | failed | 5/6 | 14 | 0 | 0 | 0 | 0 | 67 | 3 |
| 0d01c76_3 | failed | 2/6 | 13 | 1 | 1 | 0 | 1 | 10 | 1 |
| ff58e36_1 | failed | 2/6 | 4 | 0 | 0 | 0 | 0 | 3 | 1 |
| ff58e36_2 | failed | 1/6 | 7 | 0 | 0 | 0 | 0 | 7 | 3 |
| ff58e36_3 | failed | 2/6 | 18 | 2 | 2 | 0 | 2 | 25 | 1 |
| d18139b_1 | failed | 2/7 | 14 | 0 | 0 | 0 | 0 | 36 | 1 |
| d18139b_2 | failed | 1/7 | 33 | 0 | 0 | 0 | 0 | 687 | 0 |
| d18139b_3 | failed | 5/7 | 13 | 0 | 0 | 0 | 0 | 41 | 1 |
| 5a83b05_1 | failed | 1/3 | 18 | 1 | 1 | 0 | 1 | 16 | 1 |
| 5a83b05_2 | failed | 2/3 | 13 | 2 | 2 | 0 | 2 | 49 | 1 |
| 5a83b05_3 | success | 3/3 | 14 | 1 | 1 | 0 | 1 | 94 | 1 |
| 042a9fc_1 | failed | 1/5 | 6 | 0 | 0 | 0 | 0 | 3 | 1 |
| 042a9fc_2 | failed | 0/5 | 50 | 1 | 1 | 0 | 36 | 16 | 0 |
| 042a9fc_3 | failed | 1/5 | 11 | 0 | 0 | 0 | 0 | 13 | 1 |
| cef9191_1 | failed | 1/2 | 2 | 0 | 0 | 0 | 0 | 2 | 1 |
| cef9191_2 | failed | 1/2 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| cef9191_3 | failed | 1/2 | 2 | 1 | 1 | 0 | 1 | 1 | 1 |
| 3b8fb7a_1 | failed | 3/7 | 4 | 0 | 0 | 0 | 0 | 4 | 1 |
| 3b8fb7a_2 | failed | 3/7 | 29 | 1 | 1 | 0 | 3 | 27 | 3 |
| 3b8fb7a_3 | failed | 3/7 | 12 | 2 | 2 | 0 | 2 | 10 | 1 |
| afc4005_1 | failed | 1/2 | 27 | 0 | 0 | 0 | 11 | 63 | 1 |
| afc4005_2 | failed | 1/2 | 12 | 0 | 0 | 0 | 0 | 21 | 1 |
| afc4005_3 | failed | 1/2 | 12 | 0 | 0 | 0 | 3 | 24 | 1 |
| 9dabbc9_1 | failed | 1/9 | 8 | 1 | 1 | 0 | 1 | 15 | 1 |
| 9dabbc9_2 | failed | 2/9 | 12 | 1 | 1 | 0 | 1 | 11 | 2 |
| 9dabbc9_3 | failed | 1/9 | 7 | 2 | 2 | 0 | 2 | 4 | 1 |
| 425a494_1 | failed | 1/2 | 2 | 1 | 1 | 0 | 1 | 1 | 1 |
| 425a494_2 | failed | 1/2 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 425a494_3 | failed | 1/2 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| a30375d_1 | failed | 1/3 | 11 | 0 | 0 | 0 | 6 | 19 | 1 |
| a30375d_2 | failed | 1/3 | 9 | 0 | 0 | 0 | 3 | 14 | 1 |
| a30375d_3 | failed | 1/3 | 12 | 0 | 0 | 0 | 7 | 10 | 1 |
| 09b0ee6_1 | failed | 1/2 | 50 | 0 | 0 | 0 | 47 | 27 | 0 |
| 09b0ee6_2 | failed | 1/2 | 21 | 2 | 2 | 0 | 19 | 1 | 3 |
| 09b0ee6_3 | success | 2/2 | 11 | 0 | 0 | 0 | 1 | 12 | 1 |
| d194965_1 | failed | 2/6 | 2 | 0 | 0 | 0 | 0 | 2 | 1 |
| d194965_2 | failed | 2/6 | 2 | 0 | 0 | 0 | 0 | 2 | 1 |
| d194965_3 | failed | 3/6 | 9 | 0 | 0 | 0 | 0 | 15 | 1 |
| 7847649_1 | success | 2/2 | 9 | 0 | 0 | 0 | 1 | 6 | 1 |
| 7847649_2 | failed | 1/2 | 6 | 0 | 0 | 0 | 0 | 9 | 1 |
| 7847649_3 | success | 2/2 | 8 | 0 | 0 | 0 | 0 | 8 | 1 |
| 552869a_1 | failed | 1/2 | 7 | 0 | 0 | 0 | 1 | 13 | 1 |
| 552869a_2 | failed | 1/2 | 10 | 0 | 0 | 0 | 0 | 56 | 1 |
| 552869a_3 | failed | 1/2 | 9 | 0 | 0 | 0 | 1 | 13 | 1 |
| 652485c_1 | failed | 5/11 | 15 | 1 | 1 | 0 | 2 | 1159 | 12 |
| 652485c_2 | failed | 3/11 | 11 | 0 | 0 | 0 | 0 | 8 | 3 |
| 652485c_3 | failed | 3/11 | 2 | 0 | 0 | 0 | 0 | 3 | 2 |
| ccf4b82_1 | failed | 6/11 | 17 | 0 | 0 | 0 | 0 | 82 | 1 |
| ccf4b82_2 | failed | 5/11 | 19 | 2 | 2 | 0 | 2 | 21 | 2 |
| ccf4b82_3 | failed | 2/11 | 50 | 2 | 2 | 0 | 18 | 100 | 0 |
| 522e5e5_1 | failed | 2/4 | 11 | 0 | 0 | 0 | 1 | 8 | 1 |
| 522e5e5_2 | success | 4/4 | 9 | 0 | 0 | 0 | 0 | 23 | 3 |
| 522e5e5_3 | failed | 3/4 | 50 | 1 | 1 | 0 | 42 | 11 | 0 |
| 0de03ea_1 | failed | 2/5 | 9 | 0 | 0 | 0 | 2 | 15 | 1 |
| 0de03ea_2 | failed | 2/5 | 2 | 0 | 0 | 0 | 0 | 6 | 1 |
| 0de03ea_3 | failed | 2/5 | 50 | 0 | 0 | 0 | 49 | 5 | 0 |
| 2c544f9_1 | failed | 2/6 | 7 | 0 | 0 | 0 | 0 | 7 | 1 |
| 2c544f9_2 | failed | 1/6 | 11 | 1 | 1 | 0 | 1 | 9 | 1 |
| 2c544f9_3 | failed | 1/6 | 16 | 0 | 0 | 0 | 0 | 65 | 1 |
| 270f1ff_1 | failed | 1/11 | 5 | 0 | 0 | 0 | 0 | 5 | 1 |
| 270f1ff_2 | failed | 1/11 | 18 | 2 | 2 | 0 | 2 | 23 | 1 |
| 270f1ff_3 | failed | 1/11 | 10 | 1 | 1 | 0 | 6 | 3 | 1 |
| 024c982_1 | failed | 0/7 | 15 | 0 | 0 | 0 | 0 | 14 | 1 |
| 024c982_2 | failed | 1/7 | 12 | 0 | 0 | 0 | 0 | 11 | 1 |
| 024c982_3 | failed | 6/7 | 13 | 0 | 0 | 0 | 0 | 11 | 1 |
| 9ef798c_1 | failed | 5/6 | 14 | 0 | 0 | 0 | 0 | 13 | 1 |
| 9ef798c_2 | failed | 0/6 | 3 | 0 | 0 | 0 | 0 | 5 | 1 |
| 9ef798c_3 | failed | 3/6 | 13 | 0 | 0 | 0 | 0 | 25 | 1 |
| b9c5c9a_1 | failed | 1/7 | 34 | 0 | 0 | 0 | 0 | 91 | 1 |
| b9c5c9a_2 | failed | 2/7 | 4 | 0 | 0 | 0 | 0 | 3 | 1 |
| b9c5c9a_3 | failed | 1/7 | 19 | 0 | 0 | 0 | 0 | 15 | 1 |
| 90adc3f_1 | failed | 2/7 | 7 | 0 | 0 | 0 | 0 | 16 | 2 |
| 90adc3f_2 | failed | 2/7 | 11 | 0 | 0 | 0 | 0 | 36 | 9 |
| 90adc3f_3 | failed | 2/7 | 11 | 0 | 0 | 0 | 0 | 29 | 5 |
| c77c005_1 | failed | 2/5 | 11 | 0 | 0 | 0 | 0 | 9 | 3 |
| c77c005_2 | failed | 3/5 | 20 | 0 | 0 | 0 | 0 | 36 | 5 |
| c77c005_3 | failed | 3/5 | 16 | 0 | 0 | 0 | 0 | 33 | 1 |
| f323bae_1 | failed | 3/9 | 8 | 1 | 1 | 0 | 1 | 19 | 5 |
| f323bae_2 | failed | 3/9 | 12 | 0 | 0 | 0 | 0 | 162 | 1 |
| f323bae_3 | failed | 2/9 | 33 | 0 | 0 | 0 | 2 | 204 | 1 |
| 13547f5_1 | success | 6/6 | 8 | 0 | 0 | 0 | 0 | 11 | 1 |
| 13547f5_2 | success | 6/6 | 10 | 2 | 2 | 0 | 2 | 14 | 1 |
| 13547f5_3 | failed | 2/6 | 8 | 0 | 0 | 0 | 0 | 7 | 1 |
| 1150ed6_1 | failed | 0/6 | 50 | 0 | 0 | 0 | 42 | 27 | 0 |
| 1150ed6_2 | failed | 0/6 | 50 | 0 | 0 | 0 | 43 | 20 | 0 |
| 1150ed6_3 | failed | 1/6 | 2 | 0 | 0 | 0 | 0 | 1 | 1 |
| 31dc501_1 | failed | 5/6 | 50 | 0 | 0 | 0 | 44 | 8 | 0 |
| 31dc501_2 | failed | 5/6 | 9 | 0 | 0 | 0 | 0 | 11 | 1 |
| 31dc501_3 | failed | 5/6 | 50 | 0 | 0 | 0 | 44 | 10 | 0 |
| 59fae45_1 | failed | 2/6 | 7 | 0 | 0 | 0 | 0 | 7 | 1 |
| 59fae45_2 | failed | 2/6 | 1 | 0 | 0 | 0 | 0 | 1 | 1 |
| 59fae45_3 | failed | 2/6 | 3 | 1 | 1 | 0 | 1 | 6 | 1 |
| b6d1104_1 | failed | 3/10 | 18 | 1 | 1 | 0 | 2 | 44 | 1 |
| b6d1104_2 | failed | 1/10 | 20 | 1 | 1 | 0 | 1 | 104 | 3 |
| b6d1104_3 | failed | 0/10 | 50 | 0 | 0 | 0 | 41 | 25 | 0 |
| f861c32_1 | failed | 2/8 | 50 | 0 | 0 | 0 | 42 | 8 | 2 |
| f861c32_2 | failed | 2/8 | 20 | 0 | 0 | 0 | 0 | 15 | 3 |
| f861c32_3 | failed | 3/8 | 19 | 0 | 0 | 0 | 0 | 22 | 5 |
| 0a9d82a_1 | failed | 1/2 | 5 | 0 | 0 | 0 | 0 | 11 | 3 |
| 0a9d82a_2 | failed | 1/2 | 9 | 0 | 0 | 0 | 0 | 18 | 1 |
| 0a9d82a_3 | failed | 1/2 | 5 | 0 | 0 | 0 | 0 | 5 | 1 |
| 166f4ff_1 | success | 2/2 | 28 | 3 | 3 | 0 | 3 | 30 | 17 |
| 166f4ff_2 | failed | 1/2 | 36 | 0 | 0 | 0 | 28 | 29 | 1 |
| 166f4ff_3 | failed | 1/2 | 7 | 0 | 0 | 0 | 0 | 12 | 1 |
| 9016950_1 | failed | 3/7 | 10 | 0 | 0 | 0 | 0 | 8 | 3 |
| 9016950_2 | failed | 4/7 | 15 | 0 | 0 | 0 | 0 | 22 | 3 |
| 9016950_3 | failed | 3/7 | 8 | 2 | 2 | 0 | 2 | 4 | 3 |
| dac78d9_1 | failed | 1/2 | 10 | 0 | 0 | 0 | 0 | 24 | 1 |
| dac78d9_2 | failed | 1/2 | 42 | 1 | 1 | 0 | 1 | 47 | 1 |
| dac78d9_3 | success | 2/2 | 5 | 0 | 0 | 0 | 0 | 9 | 1 |
| f3f60f0_1 | failed | 2/8 | 50 | 0 | 0 | 0 | 0 | 101 | 0 |
| f3f60f0_2 | failed | 3/8 | 2 | 1 | 1 | 0 | 1 | 1 | 1 |
| f3f60f0_3 | success | 8/8 | 27 | 0 | 0 | 0 | 22 | 54 | 1 |
| ffe6d5e_1 | failed | 7/8 | 18 | 0 | 0 | 0 | 0 | 18 | 1 |
| ffe6d5e_2 | failed | 6/8 | 10 | 0 | 0 | 0 | 0 | 12 | 1 |
| ffe6d5e_3 | failed | 1/8 | 50 | 1 | 1 | 0 | 45 | 13 | 0 |
| 8ce6779_1 | failed | 3/9 | 10 | 0 | 0 | 0 | 0 | 27 | 19 |
| 8ce6779_2 | failed | 2/9 | 7 | 0 | 0 | 0 | 0 | 7 | 1 |
| 8ce6779_3 | failed | 3/9 | 17 | 1 | 1 | 0 | 1 | 11 | 1 |
| 83a7951_1 | failed | 3/10 | 26 | 0 | 0 | 0 | 4 | 21 | 1 |
| 83a7951_2 | failed | 3/10 | 33 | 3 | 3 | 0 | 4 | 153 | 0 |
| 83a7951_3 | failed | 4/10 | 7 | 0 | 0 | 0 | 0 | 48 | 4 |
| 3aa1a22_1 | failed | 3/7 | 14 | 1 | 1 | 0 | 2 | 11 | 4 |
| 3aa1a22_2 | failed | 2/7 | 50 | 2 | 2 | 0 | 35 | 14 | 0 |
| 3aa1a22_3 | failed | 3/7 | 4 | 0 | 0 | 0 | 0 | 2 | 1 |
| 32616b5_1 | failed | 4/10 | 7 | 0 | 0 | 0 | 0 | 7 | 1 |
| 32616b5_2 | failed | 3/10 | 50 | 0 | 0 | 0 | 32 | 104 | 0 |
| 32616b5_3 | failed | 3/10 | 50 | 0 | 0 | 0 | 36 | 24 | 0 |
| 986aa4e_1 | failed | 3/10 | 4 | 0 | 0 | 0 | 0 | 6 | 11 |
| 986aa4e_2 | failed | 5/10 | 31 | 1 | 1 | 0 | 7 | 19 | 1 |
| 986aa4e_3 | failed | 2/10 | 3 | 0 | 0 | 0 | 0 | 3 | 1 |
| 6b6ca61_1 | failed | 8/19 | 9 | 0 | 0 | 0 | 0 | 7 | 7 |
| 6b6ca61_2 | failed | 7/19 | 8 | 0 | 0 | 0 | 0 | 7 | 1 |
| 6b6ca61_3 | failed | 8/19 | 24 | 0 | 0 | 0 | 2 | 62 | 1 |
| bde252e_1 | failed | 0/9 | 50 | 2 | 2 | 0 | 2 | 62 | 0 |
| bde252e_2 | failed | 1/9 | 15 | 1 | 1 | 0 | 1 | 45 | 1 |
| bde252e_3 | failed | 0/9 | 30 | 0 | 0 | 0 | 0 | 75 | 1 |

## 重复 evaluator 失败 requirement

| requirement | 任务数 |
|---|---:|
| assert answers match. | 90 |
| assert model changes match spotify.MusicPlayer. | 13 |
| assert model changes match simple_note.Note. | 7 |
| assert model changes match spotify.Playlist, spotify.PlaylistSong. | 6 |
| assert the updated music player is in the playing state. | 6 |
| obtain added, updated, removed venmo.Transaction records using models.changed_records, and assert 1 was added, 0 were updated or removed. | 6 |
| assert model changes match venmo.Friendship | 5 |
| assert model changes match file_system.File. | 5 |
| obtain added, updated, removed spotify.MusicPlayer records using models.changed_records, and assert 1 has been updated, and 0 have been added or removed. | 4 |
| assert model changes match venmo.Notification, venmo.PaymentRequest | 4 |
| obtain added, deleted friendships using models.changed_records and assert friend_ids of the added ones match private_data.to_befriend_venmo_user_ids (ignore_order) | 3 |
| assert friend_ids of the deleted ones match private_data.to_unfriend_venmo_user_ids (ignore_order) | 3 |
| assert all main_user's friends on venmo match private_data.all_friends_venmo_user_ids in the end state (ignore_order) | 3 |
| assert song_ids in the end state of the music player's queue match private_data.expected_queue_song_ids, ignoring order. | 3 |
| assert music player's cursor is on the song with private_data.target_song_id. | 3 |
| obtain added, updated, deleted spotify.Playlist records using models.changed_records, and assert 1 has been added, 0 have been updated or deleted. | 3 |
| assert the added playlist's title is public_data.playlist_title. | 3 |
| obtain added, deleted spotify.PlaylistSong records using models.changed_records, and assert set of added song ids match to set of private_data.to_archive_song_ids. | 3 |
| assert set of deleted song ids also match to set of private_data.to_archive_song_ids. | 3 |
| assert playlist_id_to_song_ids of deleted_playlist_songs match private_data.to_archive_playlist_id_to_song_ids (ignore_order) | 3 |
