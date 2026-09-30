#!/usr/bin/env python3
"""Render the evidence-based offline review; no model or environment execution."""
from pathlib import Path
import collections,csv,datetime,hashlib,json,re
from inspect_saved_trajectories import ROOT,STAGE,load_task

# Human-readable judgments based on the already saved actions and observations.
NOTES={
'302c169_2':{
 'step':11,'label':'状态错误','secondary':['操作语义错误'],'confidence':'高','verdict':'可尝试单步修复','rank':2,
 'goal_zh':'把起床闹钟提前40分钟，并停用其他闹钟。',
 'failed_condition':'官方要求没有新增或删除闹钟；其他目标闹钟应只修改 enabled 状态。该题4/8测试项通过。',
 'finding':'第9步已经读到全部闹钟，第10步也同时看到了 update_alarm 的 enabled 参数和 delete_alarm 的删除语义。第11步正确把起床时间改为06:50，却用 delete_alarm 删除其他5个闹钟，并把删除结果命名为 disabled。环境明确返回 Alarm deleted successfully，后面直接提交，没有恢复被删除的记录。',
 'evidence_steps':[9,10,11,13],
 'key_code':"disable_results = [apis.phone.delete_alarm(alarm_id=alarm_id, access_token=phone_access_token) for alarm_id in other_alarm_ids]",
 'key_observation':'第11步：其他5个闹钟均返回 Alarm deleted successfully。',
 'direction':'保留起床闹钟提前40分钟的动作；对其他原本启用的闹钟调用更新接口，将 enabled 设为 false，不删除记录，也不改其他字段。',
 'earlier_error_note':'这不是接口报错：删除调用全部执行成功，但操作含义不符合用户要求。',
 'prefix_state':'替换第11步之前只有读取和登录，没有修改闹钟；必须从初始环境重放前10步，不能从已经删除闹钟的最终状态开始。',
 'why_rank':'要求、接口文档和错误动作直接对应；在第一次闹钟写入之前替换，修复范围清楚。',
 'remaining_uncertainty':'更新动作是否足够让原学生正确结束，仍须真实执行并官方评分。'},
'ccb4494_2':{
 'step':6,'label':'状态错误','secondary':['筛选条件错误'],'confidence':'高','verdict':'可尝试单步修复','rank':1,
 'goal_zh':'喜欢Spotify队列中已经播放过的歌曲，包括当前正在播放的歌曲。',
 'failed_condition':'新增喜欢记录对应的歌曲集合不符合任务要求；其余4/5测试项通过。',
 'finding':'第2步文档提供 position 和 is_current 字段。第6步却比较每首歌自己的 position <= 自己的 position，这个条件恒真，因而取出全部10首；第8步把这10首全部点赞，后面没有按当前歌曲位置重新筛选。',
 'evidence_steps':[2,6,8,10],
 'key_code':"played_song_ids = [song['song_id'] for song in song_queue if song['position'] <= song['position'] or song['is_current']]",
 'key_observation':'第6步打印 count=10；第8步对全部10个 song_id 返回 Song liked。',
 'direction':'先从队列中识别 is_current 对应的播放位置，再选择位置不晚于它的歌曲（含当前歌曲），把结果保存在后续会使用的 played_song_ids 中。不要只按变量名判断过滤是否正确。',
 'earlier_error_note':'关键条件没有触发异常，属于无报错但结果集合错误；不能靠Traceback搜索找到。',
 'prefix_state':'第6步之前完成文档查询和登录，还没有点赞写入；重放前5步即可到达目标决策位置。',
 'why_rank':'错误条件明确，前缀短，后续第8步直接使用同一变量，适合先验证局部替换能否传递到最终行为。',
 'remaining_uncertainty':'当前歌曲与队列状态必须通过重放和真实查询取得；未验证原学生接续是否成功。'},
'692c77d_1':{
 'step':19,'label':'恢复错误','secondary':['状态错误','评分值与review_id混淆'],'confidence':'高（问题存在）；低（单步足够）','verdict':'可能需要多步修复','rank':None,
 'goal_zh':'给自己的歌单中已经喜欢的歌曲打5星，已有较低评分则更新。',
 'failed_condition':'目标SongReview的新增、更新范围与评分未满足要求；最终1/7测试项通过，运行耗尽50步。',
 'finding':'第10步访问不存在的 song_review_id 后，第12步换接口取得评分，说明第一次KeyError已经被处理。随后第14步只按全部 liked_songs 建目标，未与歌单内容取交集，并把缺失评分默认设为1。第15步对已有评分创建记录触发409。第18步访问缺失键26，第19步仍按同一错误假设索引；后续反复出现KeyError和未定义变量，直到第50步。',
 'evidence_steps':[10,12,14,15,17,18,19,22,23,25,50],
 'key_code':"target_lower_ratings = {song_id: existing_ratings[song_id] for song_id in target_ids_lower}",
 'key_observation':'第18、19步均出现 KeyError: 26；第22步出现 target_lower_ratings 未定义，后续重复。',
 'direction':'若后续研究恢复，先在第19步停止对缺失键的重复索引，区分未评分和已有评分，并保存真正的review_id；同时必须重新核对歌单与喜欢歌曲的交集。不能只修打印或用默认值掩盖缺失。',
 'earlier_error_note':'首次KeyError不是唯一问题；第17步还把评分当review_id，打印set失败也只是后续现象。',
 'prefix_state':'前18步含查询和失败写入尝试；现有日志不能代替数据库核验，重放时需要检查失败调用是否产生状态变化。',
 'why_rank':'缺失值处理、目标集合和review_id三处问题互相牵连，暂不作为首批独立单步候选。',
 'remaining_uncertainty':'单改第19步可能仍对错误歌曲集合操作；没有证据证明一步能覆盖整个问题链。'},
'29caf6f_2':{
 'step':5,'label':'恢复错误','secondary':['状态错误','文本解析错误'],'confidence':'高（问题存在）；低（单步足够）','verdict':'可能需要多步修复','rank':None,
 'goal_zh':'读取Laura短信中的电影推荐请求，并从Simple Note选择符合要求的电影，用逗号分隔标题回复。',
 'failed_condition':'发送的短信缺少任务要求的电影标题；其余7/8测试项通过。',
 'finding':'第4步只取与联系人的最新消息并查找 recommendation，触发StopIteration。第5步仍设置 only_latest_per_contact=True，返回的是自己回复“稍后发”，没有读到请求。第6步又访问未定义的 request。第10步虽然找到了 Movie Recommendations 笔记，第11步却选取标题行和缩进元数据行，生成标题加大量空项；第12步再用空格拼接发送。',
 'evidence_steps':[4,5,6,10,11,12],
 'key_code':"query='recommendation', only_latest_per_contact=True",
 'key_observation':'第5步返回自己此前回复 I do, I\'ll send them over in a bit.；第11步 reply_text 只有标题和大量空项。',
 'direction':'优先在第5步修正恢复策略，读取对方此前的真实请求而不是只读最后一条回复；之后还需要按请求条件解析电影标题，并检查逗号分隔格式。',
 'earlier_error_note':'第9步读错笔记后，第10步已重新找到正确笔记；不能把第9步单独当成最终失败的充分解释。',
 'prefix_state':'第5步之前没有发出新短信；但补齐请求后，后续的标题解析和发送格式仍可能出错。',
 'why_rank':'缺少对方请求、标题解析、输出格式是多个独立问题，暂不排在单步验证首批。',
 'remaining_uncertainty':'只恢复读取请求，并不能保证第11–12步自动变正确。'},
'76f2c72_1':{
 'step':9,'label':'状态错误','secondary':['时间范围遗漏','文件格式处理'],'confidence':'高（范围与PDF遗漏）；待核对（金额口径）','verdict':'可能需要多步修复','rank':None,
 'goal_zh':'统计文件系统 ~/bills/ 中今年的电费账单总额。',
 'failed_condition':'最终数值答案不匹配；没有额外数据修改，1/2测试项通过。',
 'finding':'第7步列出的账单同时包含2022和2023年、TXT和PDF。第9步仅按 electricity 子串选文件，没有按今年筛选，直接用 show_file 读取；PDF反馈是 binary 占位内容。第10步只提取可见文本中的 Electricity Charges，得到884并提交。',
 'evidence_steps':[7,9,10,12],
 'key_code':"electricity_files = [path for path in bill_files if 'electricity' in path]",
 'key_observation':'第9步包含2022年账单，PDF项返回binary内容；第10步打印 total_electricity_cost=884.0。',
 'direction':'从环境获取当前年份后筛选今年电费账单，采用能读取PDF文本的已提供接口，核对费用字段口径后汇总。不要假设所有文件都是可直接读取的文本。',
 'earlier_error_note':'没有靠执行异常暴露的单一参数错误；官方答案不匹配只能证明最终统计错误，不能单凭该结果断言税费口径。',
 'prefix_state':'前8步是读取与登录，适合从此重新取得文件内容；但正确解析PDF和最终汇总需要额外动作。',
 'why_rank':'年份筛选、文件解析和金额口径需要分别核实，保留为多步问题样本。',
 'remaining_uncertainty':'金额应取何字段还需结合公开任务和账单内容确认；本次没有读取或写入参考答案。'},
'60d0b5b_1':{
 'step':14,'label':'参数错误','secondary':['对象筛选错误','错误恢复不完整'],'confidence':'高','verdict':'可尝试单步修复','rank':3,
 'goal_zh':'找出最近一次误向Robert发出的、已经被他批准的付款请求，把那笔钱退给他。',
 'failed_condition':'收款人和其他约束通过，新增转账金额不符；其余6/7测试项通过。',
 'finding':'第11步带query查询后返回的列表仍包含多个收款人。第12步对整个列表按created_at取最大，选中另一人的请求金额，再传错 user_email 参数。第13步查文档后，第14步虽然改为 receiver_email，仍沿用先前错误的 return_amount，随后提交。',
 'evidence_steps':[10,11,12,13,14,16],
 'key_code':"last_robert_request = max(robert_requests, key=lambda request: request['created_at'])",
 'key_observation':'第11步结果包含Kathryn、Robert、Jose等不同收款人；第12步Unexpected parameter user_email后，第14步转账成功，但官方金额条件失败。',
 'direction':'在第14步转账之前，按已确认的Robert邮箱精确过滤 receiver.email，从符合条件的已批准请求中按创建时间找最新一笔，再重新计算return_amount并使用receiver_email调用转账。金额必须来自该请求，不写死金额。',
 'earlier_error_note':'把 user_email 改为 receiver_email 的语法修复已经发生；真正未恢复的是错误金额的来源。',
 'prefix_state':'第12步在参数校验处失败，第13步读取文档。日志未显示此前成功转账；仍需环境重放核验，然后在首次成功转账之前替换。',
 'why_rank':'完整列表已在原历史里，正确联系人和接口格式也已可见；无需用评估参考金额，只需纠正这次调用的参数来源。',
 'remaining_uncertainty':'要验证失败请求确实未改变状态，并确认重算金额后原学生正确完成任务。'},
'd0b1f43_1':{
 'step':13,'label':'状态错误','secondary':['对象筛选错误','聚合方向与单位错误'],'confidence':'高（问题存在）；低（单步足够）','verdict':'可能需要多步修复','rank':None,
 'goal_zh':'统计今年1月1日以来通过Venmo发给室友的钱的总额。',
 'failed_condition':'最终数值答案不匹配；未修改业务数据，1/2测试项通过。',
 'finding':'第8步日期解析出错，但第9–10步已经取得2023年并继续。第11步文档查询参数出错后，第12步只看了一个标为parent/mother的联系人；第13步竟按parent和mother取联系人，并把他们放进roommates。第16步还按sender而非receiver聚合、作无依据单位变换；第17步提交所有聚合金额乘100。',
 'evidence_steps':[8,9,10,11,12,13,15,16,17],
 'key_code':"page = apis.phone.search_contacts(access_token=phone_access_token, relationship='parent', page_index=page_index, page_limit=20)",
 'key_observation':'第15步所谓roommate_emails实际是第12–13步看到的父母联系人邮箱；第16步因字典答案触发422，最后只改成数字提交。',
 'direction':'第13步应依据真实联系人关系取得室友；同时还要按转账receiver精确筛选并在原金额单位求和。仅把字典转换成数字不解决对象和聚合问题。',
 'earlier_error_note':'最早的日期异常已被后续恢复；最终422也不是金额错误的全部原因。',
 'prefix_state':'前12步主要为查询与登录；后续存在独立的聚合错误，因此不能把修好联系人集合等同于修好整题。',
 'why_rank':'联系人筛选、收付款方向、数值单位均错误，暂不作为首批单步验证。',
 'remaining_uncertainty':'需要确认一次替换是否会让后续策略自行纠正其余问题；当前没有这种证据。'},
'b0a8eae_3':{
 'step':6,'label':'状态错误','secondary':['检索结果核验不足','无依据默认值'],'confidence':'高（问题存在）；低（单步足够）','verdict':'可能需要多步修复','rank':None,
 'goal_zh':'按Simple Note里的今日锻炼计划，播放一张时长足够覆盖整个锻炼的Spotify歌单。',
 'failed_condition':'最终播放队列的歌曲集合不是任务要求的足够长歌单；其余4/5测试项通过。',
 'finding':'第5步把workout搜索的首个结果当作计划，读到Inspirational Quotes Collection。第6步却按这个无关标题继续查，第8步再读同一篇语录；第10步直接假定锻炼1800秒。第12步虽统计歌单时长，却未取到真实锻炼计划，第14步还直接使用playlist_id=2播放。',
 'evidence_steps':[5,6,8,10,12,14],
 'key_code':"query='Inspirational Quotes Collection'",
 'key_observation':'第5、6、8步内容都是励志语录；第10步把30分钟作为common default，非任务给定信息。',
 'direction':'在第6步停止追随无关的首条搜索结果，核验标题与内容，读到真正的今日锻炼计划；随后按真实时长和返回的playlist_id选择歌单。',
 'earlier_error_note':'没有一个足够解释全题的接口报错；主要是无关搜索结果、猜测时长和未依据查询结果选歌单。',
 'prefix_state':'前5步尚未播放音乐，适合改正读取方向；但后续时长和歌单ID选择仍可能独立出错。',
 'why_rank':'存在多个未经证实的决策，单步能否引导学生完成后续规划不明确。',
 'remaining_uncertainty':'还未从有效笔记取得真实锻炼要求，不能仅凭候选歌单时长宣布应该播放哪一张。'},
'22cc237_3':{
 'step':18,'label':'状态错误','secondary':['收款与付款语义混淆'],'confidence':'高（动作方向）；中（整体单步足够）','verdict':'可尝试单步修复','rank':5,
 'goal_zh':'对昨日同事聚餐尚未还款的人，按笔记金额发起备注为Dinner with Colleagues的付款请求。',
 'failed_condition':'最终模型变更不是要求的PaymentRequest/Notification，付款请求的人员与金额集合也不符；2/4测试项通过。',
 'finding':'第8步拿到份额笔记，第12步已有5名还款者的记录，第13步得到4名待付款者。第15步用虚构邮箱转账失败，随后第17步找到了真实邮箱；第18步却继续用create_transaction，向4个人各转出钱。API返回Sent money，第20步也没有检查到新建的目标付款请求。',
 'evidence_steps':[8,11,12,13,15,17,18,20],
 'key_code':"result = apis.venmo.create_transaction(access_token=venmo_token, receiver_email=exact_venmo_emails[name], amount=amount, description=\"Dinner with Colleagues\")",
 'key_observation':'第18步4条返回都是Sent money和transaction_id，而非payment_request_id。',
 'direction':'在第18步第一次成功资金写入前，核对并调用发起付款请求的接口，使用已有真实身份、金额和要求的备注；不能继续给欠款人转钱。',
 'earlier_error_note':'第11步漏导入timedelta已在第12步补上，第15步虚构邮箱也在第17步得到修正，但业务动作方向未被修正。',
 'prefix_state':'第15步首个虚构收款人失败，日志未显示此前成功资金写入；重放时仍需检查副作用。目标前缀已含真实邮箱，但尚未读到付款请求接口的完整参数文档。',
 'why_rank':'方向错误很明确；但付款请求接口文档、身份核验和先前日期边界还需确认，因此排在备选2。',
 'remaining_uncertainty':'第12步min/max使用同一时间串却返回了当日记录，不能仅看代码猜测实际过滤语义；应根据可见返回逐项核对，而非拿最终答案倒推。'},
'34d9492_2':{
 'step':13,'label':'状态错误','secondary':['年份条件遗漏'],'confidence':'高','verdict':'可尝试单步修复','rank':4,
 'goal_zh':'按创建时间整理照片：今年3月去Rome、今年4月去Santorini，其他去Berlin，保留原文件名。',
 'failed_condition':'文件最终路径与内容对应关系不符合要求；其余4/5测试项通过。',
 'finding':'第9步元数据明确同时有2022年4月和2023年3/4月。第13步判断的是current_year == 2023，而不是每个文件创建年份是否等于当前年份，只用文件的month分类，把上一年4月的照片也搬到了Santorini。反馈显示Berlin为空，后续检查也没有纠正。',
 'evidence_steps':[9,11,12,13,14,16],
 'key_code':"current_year == 2023 and datetime.fromisoformat(item['created_at']).month == 4",
 'key_observation':'第9步包含2022-04-20创建的文件；第13步移动结果中Berlin为空，旧年4月文件进入Santorini。',
 'direction':'第13步对每个文件同时检查created_at的year与month，年份要与环境当前年份比较；今年3/4月分别归Rome/Santorini，其他统一归Berlin，沿用原文件名和保留日期设置。',
 'earlier_error_note':'移动API执行成功，错误是分类条件少了文件年份；不应等移动完后再补救。',
 'prefix_state':'前12步已创建3个目标目录，但尚未搬动照片；这些目录是任务要求的状态，重放时保留，随后在首次移动前替换。',
 'why_rank':'局部条件错误清晰，列为备选1；首批前三优先覆盖队列筛选、闹钟操作和退款参数三个应用场景。',
 'remaining_uncertainty':'原学生在新移动结果下是否会正确结束仍待验证，静态条件检查不等于官方成功。'}
}

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def main():
    split=json.loads((STAGE/'task_split.json').read_text())
    queue=list(csv.DictReader((STAGE/'review_queue.csv').open()))
    initial=[r for r in queue if r['batch']=='initial_10']
    assert {r['task_id'] for r in initial}==set(NOTES)
    baseline=json.loads((ROOT/'evaluations/train.json').read_text())['individual']
    records=[]
    for row in initial:
        task=row['task_id'];note=NOTES[task]
        path,calls,steps=load_task(task);n=note['step'];call=calls[n-1]
        assert task in split['source_task_ids'] and not baseline[task]['success']
        assert len(calls)==len(steps)
        for c,st in zip(calls,steps):
            match=re.search(r'```python\n(.*?)```',c['output']['choices'][0]['message'].get('content') or '',re.S)
            assert match and match.group(1).strip()==st['code'].strip(),(task,st['step'])
        messages=call['input']['messages']
        tokens=int(call['output']['usage']['prompt_tokens'])
        record={
            'task_id':task,'family_id':row['scenario_id'],'difficulty':int(row['difficulty']),
            'review_order':int(row['review_order']), 'source_only':True,
            'task_instruction':calls[0]['input']['messages'][-1]['content'].split('Task:',1)[1].strip(),
            'task_summary_zh':note['goal_zh'],'baseline_official_success':False,
            'baseline_passed_tests':len(baseline[task]['passes']),'baseline_total_tests':baseline[task]['num_tests'],
            'official_failure_summary_zh':note['failed_condition'],
            'primary_label':note['label'],'secondary_labels':note['secondary'],
            'diagnosis_confidence':note['confidence'],'single_step_assessment':note['verdict'],
            'hypothesis':note['finding'],'repair_direction':note['direction'],'earlier_error_note':note['earlier_error_note'],
            'prefix_state_assessment':note['prefix_state'],'remaining_uncertainty':note['remaining_uncertainty'],
            'candidate_rank':note['rank'],'ranking_reason':note['why_rank'],
            'replace_action_index_1based':n,'lm_call_line_1based':n,
            'environment_header_line':steps[n-1]['line'],'prefix_action_count':n-1,
            'remaining_actions_including_replacement':51-n,'remaining_student_actions_after_replacement':50-n,
            'original_prompt_tokens':tokens,'reserved_completion_tokens':3000,'context_limit':32000,
            'original_input_fits_protocol':tokens+3000<=32000,
            'input_messages_sha256':hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'prefix_contains_server_log_noise':bool(re.search(r'APIServer pid|EngineCore_DP|Avg prompt throughput',json.dumps(messages))),
            'original_action':steps[n-1]['code'],
            'evidence':[{'action_index_1based':k,'environment_header_line':steps[k-1]['line'],'environment_io_path':str(path)} for k in note['evidence_steps']],
            'key_code_excerpt':note['key_code'],'key_observation_summary':note['key_observation'],
            'paths':{'lm_calls':str(path.parent/'lm_calls.jsonl'),'environment_io':str(path),'api_calls':str(path.parent/'api_calls.jsonl'),'logger':str(path.parent/'logger.jsonl'),'official_report':str(path.parent.parent/'evaluation/report.md')},
            'source_hashes':{name:sha(f) for name,f in [('lm_calls',path.parent/'lm_calls.jsonl'),('environment_io',path),('official_report',path.parent.parent/'evaluation/report.md')]},
            'prefix_replay_validated':False,'repair_attempted':False,'repair_success':None,
            'teacher_completion':None,'official_score_after_repair':None,
            'review_metadata_is_not_teacher_input':True,
        }
        records.append(record)
    with (STAGE/'review_annotations.jsonl').open('w') as f:
        for r in records:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    candidates=sorted((r for r in records if r['candidate_rank'] is not None),key=lambda r:r['candidate_rank'])
    with (STAGE/'repair_candidates.jsonl').open('w') as f:
        for r in candidates:
            fields=['task_id','family_id','primary_label','candidate_rank','replace_action_index_1based','lm_call_line_1based','environment_header_line','prefix_action_count','remaining_actions_including_replacement','remaining_student_actions_after_replacement','original_prompt_tokens','context_limit','reserved_completion_tokens','original_input_fits_protocol','input_messages_sha256','paths','source_hashes','repair_direction','ranking_reason','prefix_state_assessment','remaining_uncertainty','prefix_replay_validated','repair_attempted','repair_success','teacher_completion','official_score_after_repair','review_metadata_is_not_teacher_input']
            out={k:r[k] for k in fields};out['selection']='primary' if r['candidate_rank']<=3 else 'backup'
            f.write(json.dumps(out,ensure_ascii=False)+'\n')
    counts=dict(collections.Counter(r['primary_label'] for r in records))
    summary={'status':'completed_offline_review','reviewed_tasks':len(records),'reviewed_families':len({r['family_id'] for r in records}),
       'reviewed_difficulty':dict(collections.Counter(str(r['difficulty']) for r in records)),
       'source_summary':split['source_summary'],'check_summary':split['check_summary'],
       'tentative_primary_labels':counts,'single_step_candidate_count':len(candidates),
       'primary_candidates':[{'task_id':r['task_id'],'action':r['replace_action_index_1based'],'label':r['primary_label']} for r in candidates[:3]],
       'backup_candidates':[{'task_id':r['task_id'],'action':r['replace_action_index_1based'],'label':r['primary_label']} for r in candidates[3:]],
       'deferred_multistep_cases':[r['task_id'] for r in records if r['candidate_rank'] is None],
       'candidate_prefixes_fit_original_context':all(r['original_input_fits_protocol'] for r in candidates),
       'model_inference_runs':0,'teacher_calls':0,'environment_replays':0,'training_runs':0,'verified_successful_repairs':0,
       'next_gate':'Actual one-step replacement plus original-student continuation must pass official evaluation on 3 samples before expanding or training.',
       'completed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
    dump(STAGE/'summary.json',summary)
    md=['# 第2步失败审查：10个案例与修复候选','',
        '**状态：只读审查已完成；实际修复验证未开始。下面的候选不是成功修复样本。**','',
        '## 1. 固定划分与审查范围','',
        '采用种子20260928，按难度分层、整族划分，60题来源与30题检查无任务或任务族交叉。没有依据成功率重抽划分。','',
        '| 分组 | 任务 / 任务族 | 成功 | 失败 | 其中上下文限制 | 未超限失败 |',
        '| --- | --- | --- | --- | --- | --- |',
        '| 修复来源 | 60 / 20 | 29 | 31 | 8 | 23 |',
        '| 效果检查 | 30 / 10 | 17 | 13 | 1 | 12 |','',
        '首批审查10例均来自来源侧、未超限、分属10个任务族；难度1/2/3分别为1/6/3。检查侧只做分组统计，没有读取其轨迹作修复分析。','',
        '## 2. 先验证哪些候选','',
        '| 验证优先序 | 题号 / 动作 | 疑似关键错误 | 原始输入tokens | 替换后学生剩余动作 |',
        '| --- | --- | --- | --- | --- |']
    for r in candidates:
        note=NOTES[r['task_id']]
        md.append(f"| {r['candidate_rank']}（{'首选' if r['candidate_rank']<=3 else '备选'}） | {r['task_id']} / 第{r['replace_action_index_1based']}步 | {note['goal_zh']}：{r['primary_label']} | {r['original_prompt_tokens']} | {r['remaining_student_actions_after_replacement']} |")
    md += ['',
       '前三依次是：队列条件恒真、把停用写成删除、修正参数名称后仍沿用错误退款金额。照片年份筛选为备选1，付款请求误写成转账为备选2。排序依据是可见证据、局部可改程度和前置状态，不依据修复效果——本次没有修复效果可供排序。','',
       '所有候选原始输入加预留3000输出tokens都不超过32000，但这不保证改动后的整条续跑不会超限。剩余预算已计入之前动作和那一次替换，整题仍最多50步。','',
       '10例暂定主标签为：状态7、恢复2、参数1；其中5例具备局部尝试方向，5例暂列可能多步问题。前三不包含恢复类，不为凑三类而选择证据较弱的例子。这是诊断样本的工作标签，不能推断整个数据集的错误分布或独立能力结构。','',
       '## 3. 逐案证据','']
    for r in records:
        task=r['task_id'];n=NOTES[task]
        md += [f"### {r['review_order']}. {task}：{r['task_summary_zh']}",'',
          f"**难度{r['difficulty']}；暂定主类：{r['primary_label']}；判断：{r['single_step_assessment']}。**",'',
          f"**官方结果：** {r['official_failure_summary_zh']}",'',
          f"**读到的行为：** {r['hypothesis']}",'',
          '**关键代码片段（原学生输出，未执行）：**','', '```python',r['key_code_excerpt'],'```','',
          f"**关键反馈：** {r['key_observation_summary']}",'',
          f"**为什么不直接改第一次报错：** {r['earlier_error_note']}",'',
          f"**疑似替换点与方向：** 第{r['replace_action_index_1based']}个动作。{r['repair_direction']}",'',
          f"**前置状态：** {r['prefix_state_assessment']}",'',
          f"**输入与预算：** 对应原始模型请求第{r['lm_call_line_1based']}行，输入{r['original_prompt_tokens']} tokens；重放前{r['prefix_action_count']}个动作，再替换1步，学生最多还可执行{r['remaining_student_actions_after_replacement']}步。",'',
          f"**置信度与限制：** {r['diagnosis_confidence']}。{r['remaining_uncertainty']}",'',
          f"**排序决定：** {r['ranking_reason']}",'',
          '**证据位置：** '+ '；'.join(f"[动作{e['action_index_1based']}]({e['environment_io_path']}:{e['environment_header_line']})" for e in r['evidence'])+
          f"；[候选处原始请求]({r['paths']['lm_calls']}:{r['lm_call_line_1based']})；[官方报告]({r['paths']['official_report']})。",'',
          '**验证状态：未重放、未替换、未续跑；修复是否成功为未验证。**','']
    md += ['## 4. 下一步怎样使用这些产物','',
       '后续获准实际验证时，按候选优先序尝试。每题从干净初始环境重放原前缀，核对可见反馈及数据库/执行变量；只替换指定动作，随后由同一Qwen3-8B LoRA epoch5接手，在原预算内运行并官方评分。失败留档并进入下一个备选，不把候选直接计作成功样本。','',
       '教师输入只能来自候选处原始messages及单步修复要求。审查文件中的官方失败条件、后续轨迹和评估报告是分析证据，不能拼进教师输入。候选JSON是定位元数据，不是可直接发给教师的完整提示词。','',
       '进入扩大采集或训练之前，仍需实际取得3条官方成功修复。当前 verified_successful_repairs=0。本次按最新指令停在只读分析，不启动Qwen3-8B、教师调用或训练。','']
    (STAGE/'failure_review.md').write_text('\n'.join(md))
    manifest={'stage':'step02_error_analysis','status':'completed_offline_review','scope':'Latest user instruction: frozen split and offline review only; no Qwen rerun, teacher repair, or training.',
      'split_file_sha256':sha(STAGE/'task_split.json'),'review_queue_sha256':sha(STAGE/'review_queue.csv'),
      'review_order_frozen_before_annotation':True,'primary_candidates':summary['primary_candidates'],
      'model_inference_runs':0,'teacher_calls':0,'training_runs':0,'environment_replays':0,'verified_successful_repairs':0,
      'completed_at_utc':summary['completed_at_utc']}
    dump(STAGE/'manifest.json',manifest)
    print(json.dumps(summary,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
