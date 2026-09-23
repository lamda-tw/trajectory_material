"""Static direct-API-call classification; never execute generated code."""
import ast,collections,json,re,warnings
from pathlib import Path
KINDS=['docs_without_other_api_call','other_api_call','python_without_direct_api_call','python_parse_error','no_python']
def dotted(node):
    if isinstance(node,ast.Name):return node.id
    if isinstance(node,ast.Attribute):
        base=dotted(node.value)
        return base+'.'+node.attr if base else None
    return None

def classify(content):
    blocks=re.findall(r'```python\s+(.+?)(?:```|$)',content or '',re.S)
    if not blocks:return 'no_python'
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore',SyntaxWarning)
            tree=ast.parse('\n'.join(blocks))
    except (SyntaxError,ValueError):return 'python_parse_error'
    calls=[dotted(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call)]
    docs=any(x and x.startswith('apis.api_docs.') for x in calls)
    other=any(x and x.startswith('apis.') and not x.startswith('apis.api_docs.') for x in calls)
    if other:return 'other_api_call'
    if docs:return 'docs_without_other_api_call'
    return 'python_without_direct_api_call'

def distribution(contents):
    counts=collections.Counter(classify(c) for c in contents);n=sum(counts.values())
    return {'normal_action_count':n,'counts':{k:counts[k] for k in KINDS},'percentages':{k:100*counts[k]/n if n else 0 for k in KINDS}}

def compare(train_json,roots,task_ids,output):
    def training():
        with Path(train_json).open() as f:
            for line in f:
                r=json.loads(line)
                yield '\n'.join(m['content'] for m in r['completion'] if m['role']=='assistant')
    result={'train90_teacher':distribution(training())}
    assert result['train90_teacher']['normal_action_count']==1170
    for name,root in roots.items():
        def contents():
            for task in task_ids:
                with (root/'experiments/outputs'/output/'tasks'/task/'logs/lm_calls.jsonl').open() as f:
                    for line in f:
                        r=json.loads(line)['output']
                        if not r.get('error'):yield r['choices'][0]['message'].get('content','')
        result[name]=distribution(contents())
    return {'distributions':result,'unit':'One normal assistant response/code action; training uses each of the 1170 supervised target responses once.',
        'notes':['Only static direct calls apis.<app>.<method> are classified. Aliases, dynamic calls and execution outcomes are not inferred.',
        'Documentation category may include local Python computation; it has at least one direct API-doc call and no direct non-doc API call.',
        'Other-API calls include reads, authentication, task submission and writes; they are not synonymous with successful state changes.',
        'Invalid/empty/error responses are distinguished; service error placeholders are excluded from the denominator.',
        'Different rollout states and lengths make this a descriptive policy comparison, not evidence for a unique training mechanism.']}
