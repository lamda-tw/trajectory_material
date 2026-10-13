"""Persist outcome-selected diagnostic notes; keep separate from the frozen sample."""
from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
records=[]
def note(sid,steps,finding,assessment):
 j={r[0]:r for r in read(f'runs/scoring/{sid}/judgement.json')['steps']}
 records.append({'id':sid,'steps':steps,'original_rows':[j[s] for s in steps],'finding':finding,'assessment':assessment})
note('34d9492_1__01',[15,16,17,18], 'step17 修复 move_file 参数后，观察显示13次正常移动，无执行异常；judge 给 R1=F，理由将分类范围错误混入执行契约。', 'step17 R1 应为 P；业务对象与覆盖问题另评。机械检查发现的唯一正常执行/R1 不一致，经局部上下文复核确认。')
for sid,write,last in [('ccb4494_1__03',5,6),('ccb4494_1__04',5,6),('ccb4494_2__01',5,6),('ccb4494_3__04',6,7)]:
 note(sid,[write-1,write,last],'用户只要求喜欢截至当前位置的歌曲；代码循环整个队列。队列存在于变量中但未打印，观察只显示执行成功，未显示当前位置。写入步 R4=F/R5=U，结束步 R7=P。','结束 R7 更应为 U：未解决的目标范围不确定性不能仅由 complete_task 成功消除。不能假定未打印变量不存在，也不能根据官方失败倒推每次写入必错。')
for sid,read_step,write,last in [('cf6abd2_1__00',11,12,13),('cf6abd2_1__05',7,8,9),('cf6abd2_2__00',9,10,11)]:
 note(sid,[read_step,write,last],'读取目标笔记后精确替换目标 checkbox；update_note 返回 Note updated。结束调用给了非空 answer，违反操作类任务的明确交付要求。最后 R7=P/R8=F，官方失败。','可见目标文本修改有依据；结束交付 R7=P 存在维度边界问题（R7要求核对规定交付）。官方摘要无失败断言，不能断言非空 answer 是唯一失败原因，更不能据此把前面正确局部写入改成 F。')
note('82e2fac_1__00',[1,2,3,4],'确实循环所有歌单，show_song 的 like_count/title 使用 get 默认值。中间返回和最终变量值均未打印，未见完整 show_song 规格，最后 R7=P；官方2项测试通过1项。','具体失败原因未确定；get 默认值可能掩盖字段缺失，max_likes=0 也没有处理所有值为0时的空答案。需要回放/返回值或测试明细才能确诊，不把官方失败作为某个 step 的直接金标签。')
note('6ea6792_3__00',[5,6,7],'完整读取26条 pending 请求后全部批准；未查 contacts 以确认朋友/同事。写入步 R2=F/R4=F/R5=U，结束 R7=P。','结束 R7 更应为 U：执行成功证明批准发生，不能证明26人均属于请求的关系集合。官方失败6项通过5项；摘要不能证明具体哪笔不合条件。')
d={'method':'评分后按机械异常或官方失败且末步 R7=P 定向复核；不属于预先冻结的12轨迹176步样本，不并入其质量率。由主助手复核，原始评分不修改。','records':records,'official_failure_R7_P_status_explanation':{'explicit_status_fail_ids':['692c77d_1__02','34d9492_1__00','229360a_2__00','c901732_2__01'],'basis':'AST 对实际末步 complete_task(status="fail") 分类；诚实报告失败可获 R7=P，不等于任务成功。','remaining_default_success_submissions':9},'raw_visibility':'原始 step 保存 text/prompt_ids/response_ids/old_logprobs/finish_reason/stop_reason/usage/elapsed_seconds/step/code/observation/history_assistant_text；没有独立 API 逐调用返回或数据库状态差分字段。对仅赋值未打印的返回，judge 输入只保留代码与实际 observation。','official_detail_limit':'读取本实验使用的源轨迹 official_evaluation，仅有 success、num_tests、num_passes、num_failures；本次未重新执行 AppWorld 或补造失败断言。'}
(R/'review/supplemental_review.json').write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
lines=['# 定向补充复核','',d['method'],'',d['raw_visibility'],'',d['official_detail_limit'],'']
for x in records:
 lines += [f"## {x['id']} / steps {x['steps']}",'',x['finding'],'',x['assessment'],'',f"原始输出：`{json.dumps(x['original_rows'],ensure_ascii=False)}`",'']
(R/'review/SUPPLEMENTAL_REVIEW.md').write_text('\n'.join(lines)+'\n')
print('Saved',len(records),'diagnostic records; original judgments unchanged.')
