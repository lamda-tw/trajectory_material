"""Record this aborted baseline launch; no rubric judgment or reward is fabricated."""
from datetime import datetime,timezone
import json,sys
from pathlib import Path
from zoneinfo import ZoneInfo
sys.dont_write_bytecode=True
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import common
import baseline_newtasks as base

out=base.OUT;root=base.ROOT;now=datetime.now(timezone.utc);cfg=common.load_config();m,rows,rules=base.prepare(cfg)
summary=base.summarize(cfg,m,rows,rules)
assert summary['scored_trajectories']==0
failures=[]
for folder in sorted((out/'judgements').iterdir()):
    for path in sorted(folder.glob('events_*.jsonl')):
        events=[json.loads(s) for s in path.read_text().splitlines() if s.strip()]
        ended=[e for e in events if e.get('type')=='turn.failed']
        failures.append({'trajectory_id':folder.name,'stream':str(path),'turn_failed':bool(ended),'missing_auth_401':any('401' in json.dumps(e) and 'Missing bearer or basic authentication' in json.dumps(e) for e in events),'usage_reported':any(e.get('type')=='turn.completed' and e.get('usage') for e in events)})
assert len(failures)==6 and all(f['turn_failed'] and f['missing_auth_401'] for f in failures)
summary.update(status='blocked_authentication',evidence_review='not_run_no_judgments',failure_attempt_streams=len(failures),recorded_attempt_streams=len(failures),zero_rewards_assigned_to_failures=False)
common.atomic_json(out/'summary.json',summary)
state={'status':'blocked_authentication','updated_at_utc':now.isoformat(),'prepared_trajectories':18,'scored_trajectories':0,'accepted_verdicts':0,'started_trajectory_jobs':4,'completed_failed_attempt_streams':6,'additional_inflight_requests':'terminated; no complete event stream captured','active_experiment_processes':0,'no_failures_converted_to_NA_or_zero_reward':True,'new_rollouts':0,'optimizer_updates':0,'dev_rollouts':0}
common.atomic_json(out/'status.json',state)
common.atomic_json(out/'authentication_diagnostic.json',{'at_utc':now.isoformat(),'codex_login_status':'Not logged in','login_status_exit_code':1,'auth_file_exists':False,'credential_environment_variables_present':False,'observed_error':'401 Unauthorized: Missing bearer or basic authentication in header','completed_attempts':failures,'credentials_read_or_exposed':False,'credential_store_modified':False,'official_auth_reference':'https://learn.chatgpt.com/docs/auth'})
report=f'''# DRACO 静态基线：新题 smoke 准备与启动记录

更新：{now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')}。

**已退回仅含必要协议适配的原始静态基线，18 条新题输入已准备。实际启动遇到服务器 CLI 认证缺失，已停止；有效评分 0/18，不能给出新 reward 或复核结论。**

## 当前实际使用的评分方式

与原始 `smoke_v2` 相同：21 条官方规则原文、官方评分正文、PASS/FAIL/NA 编码、组内过滤和 reward 公式保持不变。只保留 Python fence / 自动结束协议、示范与实际步骤边界、JSON 顶层对象等本地接口适配。

`smoke_v3_calibrated` 中额外的规则边界说明、默认条款优先说明，以及 R19 禁止 NA 的语义校验均未进入当前调用。现仅检查输出结构完整、21 项标题顺序正确、分数为 -1/0/+1、证据和解释非空。R19 的合法 NA 返回不会被额外拒绝，也不会被本地改写为 PASS。

这不是否认先前发现的误判，而是将复现基线与改进 judge 分开。v2/v3 的原始响应、奖励和报告均保留。新题不用于逐题调整提示，评分误差会按实际证据记录。总体决策与后续安排只写在 plans。

## 已冻结的输入和检查

按原排序 `sha256("static-score-v1:20261009:" + task_id)` 取第 3–5 题；全部来自 train，每题六条既有 LoRA 轨迹。

| 题目 | 公开任务概述 | 轨迹数 |
| --- | --- | --- |
| afc0fce_1 | 给最近五天收到的同事 Venmo 付款评论 Thank you! 并点赞 | 6 |
| e85d92a_3 | 查询 Jasper Skye 播放次数最多的 Spotify 歌曲标题 | 6 |
| 7d7fbf6_3 | 将各度假地点的图片目录压缩到指定路径并删除原子目录 | 6 |

选题没有读取 success 标签来筛选；没有重采样。评分前按固定 hash 每题抽出 10 个轨迹—规则对，共 30 项，已写入 analysis_spec.json，但没有可供复核的新判定。

离线验证通过：18 条轨迹 hash 与原采样记录匹配；没有使用 dev；规则和官方评分正文未变；judge 配置等于 v2；同一旧输入构建出的完整 prompt 与 v2 保存文本逐字节一致；隐藏评价与模型元信息的 canary 不影响输入。只有这些离线检查已通过，实际评分链路本次未完成。

## 本次调用实际发生了什么

2026-10-09 15:33（Asia/Shanghai）启动两路并发，使用服务器独立 Codex CLI，请求原配置 `gpt-5.6-sol` / high。没有使用当前聊天助手代填评分，也没有启动本地 Qwen 推理。

前四条轨迹开始过调用；已落盘的 6 个尝试事件流均记录 `401 Unauthorized: Missing bearer or basic authentication in header`，没有完成的模型输出或 usage。另有未完成调用被停止，不能把落盘事件数当成全部网络重连次数，也不能推断精确计费 token。

只读排查显示 `codex login status` 返回 Not logged in，默认凭据文件不存在，常用认证环境变量未设置。没有修改用户登录配置、查找其他账户密钥、替换 judge 模型或打印凭据。认证检查参考 [OpenAI 官方认证说明](https://learn.chatgpt.com/docs/auth)。

本实验的评分主进程及其子进程已停止。数据状态为 **0 个有效判定、0 个完整评分组、无新 reward**；认证失败没有记成模型 FAIL、NA 或 reward=0。原先采样的官方成败数据也没有变化。

## 已准备的恢复入口与产物

恢复入口 `python stages/step02_static_scores/resume_baseline_newtasks.py --execute` 已完成离线检查，当前没有执行评分恢复。它先检查 CLI 登录；可用后将失败目录另行归档，先完成一条请求，再保持最多两条在途任务。发生调用失败时不继续提交其余题目。它只改运行调度，不改 prompt、规则、judge 配置或 reward。

- [冻结清单]({out/'manifest.json'})、[离线验证]({out/'offline_validation.json'})、[预先固定的抽查项]({out/'analysis_spec.json'})。
- [认证诊断]({out/'authentication_diagnostic.json'})、[运行日志]({out/'run.log'})、[当前状态]({out/'status.json'})。
- [原始基线入口]({root/'stages/step02_static_scores/baseline_newtasks.py'})、[恢复入口]({root/'stages/step02_static_scores/resume_baseline_newtasks.py'})、[结果分析脚本]({root/'stages/step02_static_scores/analyze_baseline_newtasks.py'})。

阶段 fingerprint：`{m['fingerprint']}`。原采样源码、模型、540 条轨迹以及 v2/v3 的冻结文件均未修改。本次没有运行全量评分、GRPO 或新 dev。
'''
(out/'SMOKE_REPORT.md').write_text(report)
p=root/'RUBRIC_GRPO_EXPERIMENT_REPORT.md';text=p.read_text()
a=text.index('## 当前完成状态');b=text.index('## 第一步：完整训练集采样')
text=text[:a]+f'''## 当前完成状态

原始 Qwen3-8B 与 SFT LoRA 各完成 train90 × 6，共 1,080 条轨迹；LoRA 的原始 12 条 smoke 与同批校准重测已完成。当前按用户要求回到官方静态基线，只保留必要协议适配，v3 校准结果作为历史记录保留。

另三个新 train 题的 18 条评分输入已经冻结，但启动遇到独立 Codex CLI 未认证，已停止，尚无新分数。详见 [当前启动记录]({out/'SMOKE_REPORT.md'})。本系列尚无 GRPO 更新或新 dev 评测结果。

本报告只记录实际执行；总体安排见 [当前待办]({root.parents[1]/'plans/2026-10-08_rubric_research/README.md'}) 和 [实验计划]({root.parents[1]/'plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md'})。以下历史记录按发生顺序保留。

'''+text[b:]
start='<!-- DRACO_BASELINE_NEWTASKS_START -->';end='<!-- DRACO_BASELINE_NEWTASKS_END -->'
assert start not in text
text=text.rstrip()+'\n\n'+start+'\n'+report.replace('# DRACO 静态基线：新题 smoke 准备与启动记录','## 2026-10-09：回到原始 DRACO 静态基线，新题启动遇到认证问题',1)+'\n'+end+'\n';p.write_text(text)
print(json.dumps(state,ensure_ascii=False,indent=2))
