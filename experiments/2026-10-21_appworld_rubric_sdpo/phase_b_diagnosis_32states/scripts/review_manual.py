"""Explicit, auditable post-hoc human review; not a new Codex judge or v7 ZeroFail label."""
from pathlib import Path
import json
D=Path(__file__).resolve().parents[1]
manifest=json.loads((D/'config/manifest.json').read_text())
# Main sampled failure/precondition addressed by an executable first action. Y is not all-rubric-P.
base_c2={
'R1_b011':('Y','取得真实账号凭据，为修复缺少认证提供必要前提。','仍未先读取凭据 API 完整规范；后续连续出现类型、缺少 username 和不存在 API 错误。'),
'R1_b012':('Y','首次查询 file_system API 列表，为修复 create_file 参数错误取得必要资料。','第 2 步才取得 create_file 完整规范；后续仍缺少认证。'),
'R1_b015':('N','仍用演示中的 dummy_spotify_pass 登录，实际返回 Invalid credentials。','不能把将 print(login_result) 改成 login 调用视为有效修复。'),
'R1_b016':('Y','查询凭据来源的 Supervisor 文档，补足未定义 passwords 的前提。','后续虽然成功取凭据并登录，但业务查询仍报错。'),
'R1_b021':('Y','读取此前缺失的 file_system.login 完整规范。','第 2 步成功登录，第 3 步成功读取目录；更后续还有错误。'),
'R1_b023':('Y','page_limit 从非法 50 改成合法 20，首步实际检索成功。','这一计数不证明后续遍历完整，也不等于 R8 已完全通过。'),
'R1_b025':('Y','从不存在的联系人 API 改为先发现 Phone 的真实 API。','后续实际业务调用仍失败。'),
'R1_b028':('Y','用真实 Phone 手机号代替错误 email 登录，认证成功。','后续能读取联系人与交易；不作完整任务成功结论。'),
'R6_b001':('N','首步依旧重复已获取的 Supervisor API 列表。','后续有进展不能倒推首步已修复。'),
'R6_b013':('N','增加一个新查询的同时，仍重复反馈明确禁止的 show_song_library 规范查询。','后续连续重复这两个文档查询。'),
'R6_b014':('Y','按反馈读取此前缺失的 create_transaction 规范。','后续用负数金额退款被拒绝，因此不能算业务纠正完成。'),
'R6_b018':('Y','从重复 API 列表切换到首次读取凭据接口完整规范。','后续取凭据、登录、分页读取 liked songs 都成功。'),
'R6_b031':('Y','从重复 search_albums 规范切换到执行真实相册检索并取得结果。','C0 也做出了相同首步，不能归因为反馈带来的独有提升；后续完整性另论。'),
'R6_b032':('Y','从重复凭据接口文档切换为真实执行该接口。','后续仍有重复取凭据和变量问题，首步进展不等于持续恢复。'),
'R6_b033':('N','尝试认证但依赖未定义 passwords，首步 NameError。','还存在布尔列表取 password 的类型错误风险。'),
'R6_b035':('N','尝试认证但依赖未定义 passwords，首步 NameError。','没有正确利用已执行历史中的变量命名。'),
'R8_b007':('Y','先读取缺失的 show_playlist 完整规范，第 2 步再读取 show_song 规范。','短续跑后来用错误 songs 字段，故补文档并不保证后续正确使用。'),
'R8_b008':('U','首步仅查找 label=Sleep 的闹钟并报告未找到，未实际调用更新接口。','对原来的多项身份/规则/协议问题是否构成有效首步修复存在歧义；后续又把 Wake Up 当作睡眠闹钟。'),
'R8_b009':('N','虽然改为浏览真实目录，但仍未先读目录 API 规范，主要 R8 问题没有修复。','“不再猜文件名”属于部分改善，不计为主要问题已修复。'),
'R8_b014':('Y','先读取缺失的 show_album 完整规范，下一步实际读取相册成功。','后续又用占位的 listening_count=0，不是可直接信任的完整解法。'),
'R8_b019':('Y','读取缺失的 show_directory 完整规范，后续实际目录检索成功。','第 4 步解析文件内容时出现类型错误。'),
'R8_b020':('U','新查询 Spotify API 列表，但尚未读取反馈要求的 search_playlists 完整规范。','仅属间接准备；后续继续使用不受支持的 134 首歌曲阈值。'),
'R8_b022':('N','首步依旧只读默认第一页，没有按反馈进行 page_index 迭代。','成功返回数据不代表分页协议修复。'),
'R8_b025':('Y','实际用 page_index 循环直到空页并保存联系人身份，首步执行成功。','是反馈改变实质代码逻辑的正例。'),
}
rows=[]
for item in manifest['states']:
 if item['stratum']=='clean':continue
 key=next(k for k in base_c2 if item['id'].startswith(k));label,reason,caution=base_c2[key]
 rows.append({'state_id':item['id'],'condition':'base_C2','targeted_first_step_repair':label,'reason':reason,'limitations_or_suffix':caution})
 rows.append({'state_id':item['id'],'condition':'base_C0','targeted_first_step_repair':'Y' if key in ['R1_b023','R6_b031'] else 'N','reason':'合法 page_limit=20，执行成功，但单页极值结论仍不可靠。' if key=='R1_b023' else ('执行真实 search_albums 检索，成功取得结果。' if key=='R6_b031' else '首步未修复主要反馈问题；参见保存的实际动作和环境反馈。'),'limitations_or_suffix':'此为主问题的局部诊断，不是全维度 ZeroFail 判定。'})
(D/'analysis/manual_first_step_review_base.json').write_text(json.dumps({'scope':'Post-hoc manual review by assistant, no new external Codex calls. Y means an executable first action addresses the primary sampled problem or a necessary prerequisite; not all v7 rules pass, not task success. U retained when partial/indirect repair is ambiguous.','rows':rows},ensure_ascii=False,indent=2)+'\n')
print('Saved 48 base-model first-action reviews')
