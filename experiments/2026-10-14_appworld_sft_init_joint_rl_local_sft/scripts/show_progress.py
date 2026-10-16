"""Read-only, standard-library progress viewer. No CUDA initialization or training imports."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import argparse,json,re,time
ROOT=Path(__file__).resolve().parents[1]

def read(path):
    try:return json.loads(path.read_text())
    except (FileNotFoundError,json.JSONDecodeError):return {}

def alive(pid):
    if not pid:return False
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except (FileNotFoundError,ProcessLookupError):return False

def committed(directory):
    return sorted(p for p in directory.glob('step_*') if re.fullmatch(r'step_\d{5}',p.name) and (p/'manifest.json').exists())

def snapshot():
    state=read(ROOT/'STATUS.json');heart=read(ROOT/'runtime/round1_run/heartbeat.json');phase=state.get('phase','unknown')
    final_eval=read(ROOT/'evaluation/round_01_final/STATUS.json')
    current_pool=bool(state.get('stop_after_current_pool')) or (ROOT/'runtime/finish_current_pool.json').exists()
    cfg=read(ROOT/'config/training_config.json')
    trial=phase.startswith('full_pool_trial_');tag=phase.rsplit('_',1)[-1] if trial else None
    if not cfg:cfg=read(ROOT/f'config/round1_trial_{tag or "15"}.json')
    total=cfg.get('schedule_candidate',{}).get('batches_per_round')
    lines=[f"查询时间：{datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d %H:%M:%S')} 北京时间",'设备限制：仅物理 GPU1',
           f"阶段：{phase}",f"监督进程：{'运行中' if alive(state.get('pipeline_pid')) else '已退出'}（PID {state.get('pipeline_pid','—')}）"]
    formal_dirs=sorted((ROOT/'training').glob('round_*'));formal_updates=sum(len(committed(p)) for p in formal_dirs)
    if current_pool:lines.append('本次目标：第一轮模型已保留；按新增指令进行DEV57评测，不启动后续训练' if final_eval else '本次目标：完成当前第 1 轮，保留最终模型后结束；不重复训练或自动评测')
    else:lines.append(f'正式训练累计已提交更新：{formal_updates}；本次自动链止于第 1 轮评测')
    if trial or phase in ('formal_round_01','finish_current_pool','round01_model_export','round01_model_complete','current_pool_error'):
        out=Path(state.get('active_training_output',str(ROOT/'smoke/full_pool_15'))) if current_pool else (ROOT/f'smoke/full_pool_{tag}' if trial else ROOT/'training/round_01')
        progress=read(out/'progress.json');refs=read(ROOT/'cache/round_01_A0_reference/progress.json');done=len(committed(out))
        label='第 1 轮（保留当前试跑模型）' if current_pool else ('工程试跑（不计正式轮次）' if trial else '正式训练')
        lines.append(f"{label}：已提交 {done}/{total or '?'} 批更新")
        lines.append(f"A0 参考概率缓存：{refs.get('reference_episodes_done',0)}/{refs.get('total',540)} 条轨迹")
        if 'batch' in progress:
            batch=progress['batch'];branch=progress.get('branch');status=progress.get('state')
            lines.append(f"最近批进度：第 {batch}/{total or '?'} 批"+('，更新已原子提交' if status=='UPDATE_COMMITTED' else '，尚在累积梯度'))
            if branch=='rl':
                count=cfg.get('schedule_candidate',{}).get('tasks_per_batch',0)*cfg.get('schedule_candidate',{}).get('rollouts_per_task',6)
                lines.append(f"RL 分支：轨迹 {progress['item']+1}/{count or '?'}，已处理该轨迹第 {progress['action']+1} 个动作")
            elif branch=='sft':
                # Mirrors only the step-count allocation; no training module imports.
                q,r=divmod(2623,total);sizes=[q+(i<r) for i in range(total)]
                lines.append(f"SFT 分支：步骤 {progress['item']+1}/{sizes[batch-1]}")
            if 'elapsed' in progress:lines.append(f"本批已用时：{progress['elapsed']/60:.1f} 分钟（最近心跳时）")
            lines.append(f"批进度更新时间：{progress.get('at','—')}")
        else:lines.append('尚未进入梯度累积 batch；正在准备参考概率/检查输入。')
    elif phase in ('baseline_dev57','round01_dev57'):
        label='initial' if phase=='baseline_dev57' else 'round_01';ev=read(ROOT/f'evaluation/{label}/STATUS.json')
        lines.append(f"{'初始基线' if label=='initial' else '第 1 轮模型'} DEV57：{ev.get('tasks_done',0)}/{ev.get('total',57)} 题")
    elif phase=='round01_complete':lines.append('第 1 轮训练及评测已完成；第 2 轮尚未启动。')
    elif phase=='round01_pipeline_error':lines.append('执行已停止：'+state.get('error','见 runtime/round1_run/ERROR.json'))
    if phase=='round01_model_complete':lines.append('最终模型已保存，训练已结束：'+state.get('final_adapter',''))
    if phase=='current_pool_error':lines.append('异常：'+state.get('error','见 runtime/round1_run/ERROR.json'))
    if heart:
        lines.append(f"监督心跳：{heart.get('at','—')}；当前子进程 {'运行中' if alive(heart.get('child_pid')) else '已退出'}")
    if state.get('active_log'):lines.append('当前日志：'+state['active_log'])
    if final_eval:
        lines.append(f"新增 DEV57 评测：{final_eval['phase']}；已完成 {final_eval['tasks_done']}/{final_eval['total']} 题；成功 {final_eval['successes']} 题")
        lines.append(f"评测进程：{'运行中' if alive(final_eval.get('pid')) else '已退出'}（PID {final_eval.get('pid','—')}）")
        lines.append('逐题结果：'+str(ROOT/'evaluation/round_01_final/RESULTS.md'))
        lines.append('评测日志：'+str(ROOT/'logs/dev57_round_01_final.log'))
    trend=read(ROOT/'evaluation/historical_protocol_trend/STATUS.json')
    if trend:
        lines.append('')
        lines.append(f"同历史协议的五点评测：{trend['phase']}；当前 step {trend.get('current_step')}；总进度 {trend['tasks_done']}/285")
        lines.append(f"五点评测进程：{'运行中' if alive(trend.get('pid')) else '已退出'}（PID {trend.get('pid')}）")
        for point in trend['points']:
            summary=point.get('summary',{})
            score=f"；TGC={summary['successes']}/57，SGC={summary['successful_scenarios']}/19" if summary else ''
            lines.append(f"  step {point['step']}：{point['tasks_done']}/57{score}")
        if trend.get('error'):lines.append('五点评测异常：'+trend['error'])
        lines.append('五点结果：'+str(ROOT/'evaluation/historical_protocol_trend/RESULTS.md'))
        lines.append('五点日志：'+str(ROOT/'logs/historical_dev57_trend.log'))
    return '\n'.join(lines)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--watch',type=float,metavar='SECONDS',help='定时刷新，例如 --watch 5')
    args=parser.parse_args()
    if args.watch is not None and args.watch<1:parser.error('--watch must be at least 1 second')
    try:
        while True:
            if args.watch:print('\033[2J\033[H',end='')
            print(snapshot(),flush=True)
            if not args.watch:break
            time.sleep(args.watch)
    except KeyboardInterrupt:pass
if __name__=='__main__':main()
