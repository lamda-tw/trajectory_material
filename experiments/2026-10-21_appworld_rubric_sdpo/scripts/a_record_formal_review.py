"""Record the assistant's post-run evidence review separately from automatic labels."""
from a_formal_review_tables import R, OUT, read
import csv, json, collections, datetime, hashlib

# Entries follow C0 repeat 0/1, C1 repeat 0/1, C2 repeat 0/1, C3 repeat 0/1;
# clean controls contain C0 0/1, C2 0/1 only. These are assistant annotations.
# D: relevant new documentation/discovery; P: useful local prerequisite/read;
# W: task-related write (does not imply protocol compliance or final success);
# R: redundant/no clear evidence gain; E: execution failure; U: unsupported/unresolved.
NOTES = {
 'state_dc419026d17908a4': ('RRREDREU', 'C2 一次查询新的 create_transaction 规范，找到退款方向；另一次重复 Venmo API 列表。C3 一次继续提交已被拒绝的 status 参数，一次错误地把更新交易当作退款方向。没有实际退款。'),
 'state_892f4749a5dc63b7': ('PPEUDDDP', 'C2 两次读取新的 show_playlist 规范，C3 一次读规范、一次打印已有字典确认结构。C0 继续无规范读取下一歌单；C1 一次报错，一次把字典键拼入列表。跨三个音乐库找最早发行歌曲仍未完成。'),
 'state_74151614143520ad': ('EEEEPPEE', 'C2 两次使用真实 token 字符串与 page_limit=20，得到交易数据，修复认证。但年份仍硬编码，未验证同事身份或求和；LR 不能解释为原业务逻辑全部修复。C3 继续错误 token 或虚构 get_contacts。'),
 'state_e2fc9bd28f016c8a': ('DDRRRDDD', 'C2 一次重复 API 列表，一次补查 song/album library 的完整规范；C0/C3 也有合理的首次规范查询。没有执行音乐库清理。'),
 'state_126d6a707faa9c5f': ('EERRDDDD', 'C2/C3 补查 file_system.login 规范；C0 重复无 token 401，C1 重复不能提供 token 的 profile 查询。只解决下一步认证方向，未计算账单。'),
 'state_9ac003937b88afdd': ('EEEEPPPP', '明确代码级修复：C0/C1 将布尔比较列表元素当字典取 password，持续 TypeError；C2/C3 正确筛选 account_name=phone 的记录并取 password。未继续登录或请求付款。'),
 'state_51a62b7ec69c62de': ('DDEEDDDD', 'C0/C2/C3 都能查询 phone.login 的新规范；C1 仍无凭据调用或虚构凭据。规范提供手机号格式，不等于已分摊账单。'),
 'state_1abe92d466de6d33': ('EPREPPPP', 'C2/C3 获取凭据是有用的前置动作，但跳过 supervisor.show_account_passwords 规范，全部仍有 R8=F。修复原 NameError 方向不能保证不引入其他违规。'),
 'state_a29c86f563a8f8b8': ('RRDRRRRD', 'C2 两次无视反馈继续检查已知 keys；C3 一次重复列表、一次补查 show_song。C1 repeat1 重复第3步已有 Spotify API 列表，却得 LR=1，是助手指出的评分疑点；不覆盖标签。'),
 'state_e444490e2ca9ab14': ('RRRRDDDD', 'C0/C1 重复已知 phone API 列表；C2/C3 转为首次 phone.login 完整规范查询，是合理认证前置进展。'),
 'state_f3cf405e62270b6a': ('EEREDDDE', 'C2 两次首次查询 Spotify API 列表以发现 song-detail endpoint，真实前缀没有该列表调用；C3 一次同样查询、一次继续把 library summary 当 playlist details 而 KeyError。未执行关注。'),
 'state_76557df73339f33c': ('DERRRRRR', 'C2 repeat0 重复第2步已读 show_song_library 规范却得 LR=1；另一次重复第8步已完成的库读取。C3 重复规范被判 F。C0 首次 show_song 查询伴随虚构说明/额外代码块，仍不合规。历史 recovery 分层在新 v7 下仅 R8=F。'),
 'state_78e1b25f5e740f15': ('REDRDDDD', 'C2/C3 补查 supervisor.show_account_passwords 规范；C0 再次选首条密码而非 Venmo 项并登录失败。没有验证或批准付款请求。'),
 'state_02ecfd5cd01cbfc8': ('DDDPDDDD', '第1步的 API 发现/规范查询都是合理准备；C1 repeat1 已拿到凭据并登录但违反先读规范的要求。所有结果都未求出最少播放歌曲。'),
 'state_3c52e9b960dc800d': ('PPPPDDDD', 'C0/C1 语音消息读取能返回数据，但缺规范、部分说明夸大文本删除覆盖。C2/C3 补查 search_voice_messages 完整规范；没有执行后续删除。'),
 'state_f740d80012bc085e': ('WEWEDDWW', 'C2 两次先读 create_playlist 规范。C3 两次照搬创建代码并确实创建播放列表，但仍 R8=F；C0/C1 各一次创建成功、一次缺参数失败。更高 LR 与立即产生业务写入是不同指标。'),
 'state_7bc3a64991ff9ad7': ('PPEP', '干净对照：C0 两次完整分页读出4个歌单；中性 C2 一次擅自 page_limit=100 报错，一次仍成功。是上下文扰动造成退化的具体例子，尚不能推断训练遗忘。'),
 'state_3c45df53edc6afe1': ('DDDD', '干净对照：四次都是新的 phone.login 规范查询，均合理，未删除任何消息。'),
 'state_72440e05db6e6e74': ('EEPE', '干净对照：C0 两次错误；中性 C2 一次正确筛选 Spotify 凭据并登录，一次布尔下标错误。中性上下文也可能偶然改善，不能只选退化样本。'),
 'state_384f3e43f6c5a2a7': ('RRDD', '干净对照：C0 repeat1 重读初始参考已给的 Spotify login 规范，虽然自动通过但新信息有限；中性 C2 两次查询 Supervisor API 列表为找凭据准备。'),
}


def main():
    now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    selected = list(csv.DictReader((R / 'phase_a/config/manual_audit_states.csv').open()))
    index = read(R / 'phase_a/config/formal_blind_index.json')
    metrics = {r['id']: r for r in csv.DictReader((OUT / 'candidate_metrics.csv').open())}
    annotations = []
    states = []
    for s in selected:
        sid = s['public_state_id']; codes, note = NOTES[sid]
        items = sorted((x for x in index if x['state_id'] == sid), key=lambda x:(x['arm'],x['repeat']))
        assert len(codes) == len(items)
        states.append({'state_id': sid, 'panel': s['panel'], 'historical_stratum': s['stratum'], 'note': note, 'candidate_ids': [x['id'] for x in items]})
        for code, x in zip(codes, items):
            r = metrics[x['id']]
            annotations.append({'id': x['id'], 'state_id': sid, 'arm': x['arm'], 'repeat': x['repeat'], 'panel': s['panel'],
                                'automatic_labels': r['labels_v7'], 'automatic_LR': int(r['LR']), 'assistant_evidence_category': code,
                                'candidate_public_evidence': x['judge_input'], 'scope': 'A single action; no claim of completed task or gold rubric correction.'})
    c2 = [a for a in annotations if a['panel'] == 'formal_fail' and a['arm'] == 'C2_feedback']
    result = {'reviewed_at': now, 'reviewer': 'current Codex assistant', 'independent_human_review_completed': False,
              'reviewer_blinded_to_conditions': False, 'automatic_labels_modified': False,
              'selection': 'Prespecified 20 states, all eligible, no replacements; all 144 target actions reviewed with source feedback, code, observations, rubric labels and relevant prefix/reference evidence. This is an assistant evidence audit, not the preregistered independent blinded human audit.',
              'states_reviewed': len(states), 'candidates_reviewed': len(annotations),
              'categories': {'D': 'Relevant new documentation/discovery', 'P': 'Useful local prerequisite/read; may still violate a rubric', 'W': 'Task-related write; protocol and task correctness not guaranteed', 'R': 'Redundant or no clear evidence gain', 'E': 'Execution failure', 'U': 'Unsupported or unresolved action'},
              'C2_fixed_FAIL_audit': {'candidates': len(c2), 'automatic_LR_success': sum(a['automatic_LR'] for a in c2),
                                    'LR_success_with_relevant_local_progress': sum(a['automatic_LR'] and a['assistant_evidence_category'] in 'DPW' for a in c2),
                                    'LR_success_with_redundant_action': sum(a['automatic_LR'] and a['assistant_evidence_category'] == 'R' for a in c2)},
              'states': states, 'candidates': annotations}
    (OUT / 'assistant_review.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
    with (OUT / 'assistant_review_candidates.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(annotations[0]));w.writeheader();w.writerows(annotations)
    repairs=[]
    for cid in ['candidate_49679da4989935173eed3621','candidate_b1619c0a03424a5262e8132b']:
        folder=R/'phase_a/judging/candidate_formal'/cid/'base'
        before=read(folder/'attempt_01/response.json');after=read(folder/'judgement.json')
        labels_before={s[0]:''.join(s[1].split()) for s in before['steps']};labels_after={s[0]:s[1] for s in after['steps']}
        repairs.append({'candidate_id':cid,'normalized_all_step_labels_unchanged':labels_before==labels_after,'steps':len(labels_after)})
    assert all(r['normalized_all_step_labels_unchanged'] for r in repairs)
    (OUT/'format_repair_verification.json').write_text(json.dumps(repairs,indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ['states','candidates']},ensure_ascii=False,indent=2))
    print('FORMAT_REPAIR',repairs)


if __name__ == '__main__':
    main()
