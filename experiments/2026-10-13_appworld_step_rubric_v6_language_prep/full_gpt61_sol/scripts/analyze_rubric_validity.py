"""CPU-only descriptive validity audit; leaves scoring and training artifacts unchanged.
Intervals: percentile bootstrap over task families (5000 replicates, seed 20261013).
P/F associations exclude U and N; never interpret N as failure.
"""
from pathlib import Path
import csv, json, itertools, collections
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'analysis/rubric_validity'
OUT.mkdir(exist_ok=True)
rows = list(csv.DictReader((ROOT/'analysis/step_labels.csv').open()))
tr = list(csv.DictReader((ROOT/'analysis/trajectory_metrics.csv').open()))
rs = [f'R{i}' for i in range(1,9)]
y = np.array([r['official_success']=='True' for r in rows])
lab = np.array([[r[k] for k in rs] for r in rows])
families = sorted({r['task_family'] for r in rows})
fi = np.array([families.index(r['task_family']) for r in rows])
rng = np.random.default_rng(20261013)
w = rng.multinomial(len(families), np.ones(len(families))/len(families), size=5000)
def phi(a):
    a,b,c,d = np.moveaxis(np.asarray(a,dtype=float),-1,0)
    den = np.sqrt((a+b)*(c+d)*(a+c)*(b+d))
    return np.divide(a*d-b*c,den,out=np.full_like(den,np.nan),where=den>0)
def ci(a):
    a=np.asarray(a); a=a[np.isfinite(a)]
    return np.quantile(a,[.025,.975]).tolist() if len(a) else [None,None]
def corr(x,y):
    return float(np.corrcoef(x,y)[0,1]) if len(x)>2 and np.std(x)>0 and np.std(y)>0 else None
summary=[]
for j,k in enumerate(rs):
    z=lab[:,j]; counts=collections.Counter(z)
    cells=np.array([[sum((fi==i)&y&(z=='P')),sum((fi==i)&(~y)&(z=='P')),sum((fi==i)&y&(z=='F')),sum((fi==i)&(~y)&(z=='F'))] for i in range(len(families))])
    a,b,c,d=cells.sum(0).tolist()
    boot=w@cells
    sd=boot[:,0]+boot[:,2]; fd=boot[:,1]+boot[:,3]
    diff=np.divide(boot[:,0],sd,out=np.full(5000,np.nan),where=sd>0)-np.divide(boot[:,1],fd,out=np.full(5000,np.nan),where=fd>0)
    app=[r for r in rows if r[k]!='N']
    succ_app=[r for r in app if r['official_success']=='True']
    vals=[]
    for r in tr:
        n=sum(int(r[f'{k}_{l}']) for l in 'PFU')
        if n: vals.append((r['task_id'],r['task_family'],r['official_success']=='True',int(r[f'{k}_P'])/n))
    matched=[]
    for task in sorted({v[0] for v in vals}):
        sv=[v[3] for v in vals if v[0]==task and v[2]]; fv=[v[3] for v in vals if v[0]==task and not v[2]]
        if sv and fv: matched.append((task.split('_')[0],float(np.mean(sv)-np.mean(fv))))
    gs=np.array([sum(d for f,d in matched if f==fam) for fam in families]); gn=np.array([sum(f==fam for f,d in matched) for fam in families])
    bn=w@gn; bs=w@gs
    bd=np.divide(bs,bn,out=np.full(5000,np.nan),where=bn>0)
    pf_ids={r['id'] for r in rows if r[k] in 'PF'}
    result={'rubric':k,'counts':dict(counts),'applicable_steps':len(app),'coverage':len(app)/len(rows),'applicable_trajectories':len({r['id'] for r in app}),'applicable_tasks':len({r['task_id'] for r in app}),'applicable_families':len({r['task_family'] for r in app}),'success_applicable_steps':len(succ_app),'success_applicable_trajectories':len({r['id'] for r in succ_app}),'pf_trajectories':len(pf_ids),'pf_cells_successP_failureP_successF_failureF':[a,b,c,d],'success_pass_P_over_PF':a/(a+c),'failure_pass_P_over_PF':b/(b+d),'phi_PF':float(phi(cells.sum(0))),'phi_family_bootstrap_ci':ci(phi(boot)),'phi_valid_bootstrap_replicates':int(np.isfinite(phi(boot)).sum()),'pass_difference_PF':a/(a+c)-b/(b+d),'pass_difference_family_bootstrap_ci':ci(diff),'success_pass_P_over_PFU':sum(r[k]=='P' for r in succ_app)/len(succ_app),'failure_pass_P_over_PFU':sum(r[k]=='P' and r['official_success']=='False' for r in app)/(len(app)-len(succ_app)),'trajectory_pass_fraction_corr':corr([v[3] for v in vals],[v[2] for v in vals]),'within_task_pass_difference':float(np.mean([v[1] for v in matched])) if matched else None,'within_task_difference_ci':ci(bd),'within_task_valid_bootstrap_replicates':int(np.isfinite(bd).sum()),'within_task_matched_tasks':len(matched)}
    summary.append(result)
pairs=[]
for j,l in itertools.combinations(range(8),2):
    mask=np.isin(lab[:,j],['P','F'])&np.isin(lab[:,l],['P','F'])
    pairs.append({'r1':rs[j],'r2':rs[l],'joint_PF_steps':int(mask.sum()),'phi':corr((lab[mask,j]=='P').astype(float),(lab[mask,l]=='P').astype(float))})
# Apply the SAME previously frozen mechanical eligibility pool to NEW labels.
WORKSPACE=ROOT.parents[2]
invpath=ROOT/'research/common_pool_inventory.jsonl'
inv=[json.loads(line) for line in invpath.read_text().splitlines()]
label_index={(r['id'],int(r['step'])):''.join(r[k] for k in rs) for r in rows}
common=[]
for item in inv:
    if item['common_pool']:
        row=dict(item)
        # Exact key mapping is verified against the input inventory below.
        key=(row.get('trajectory_id',row.get('id')),row.get('step',row.get('step_id')))
        if key[0] and key[0].startswith('base:'):key=(key[0][5:],key[1])
        key=(key[0],int(key[1]))
        row['labels']=label_index[key];common.append(row)
def gate(r,omit=None):
    z=r['labels']; return z[0]=='P' and z[6]=='N' and all(z[i] in 'PN' for i in range(1,6) if i!=omit)
selected=[r for r in common if gate(r)]
selection={'scope':'New labels on unchanged original common_pool eligibility; diagnostic only, not new training data.','steps':len(selected),'by_rubric':{k:dict(collections.Counter(r['labels'][j] for r in selected)) for j,k in enumerate(rs)},'R5P_R8P':sum(r['labels'][4]=='P' and r['labels'][7]=='P' for r in selected),'pool_base':len(selected),'pool_without_one_gate':{rs[i]:sum(gate(r,i) for r in common) for i in range(1,6)},'pool_plus_R8P':sum(gate(r) and r['labels'][7]=='P' for r in common),'pool_R5P':sum(gate(r) and r['labels'][4]=='P' for r in common),'pool_R5P_R8P':sum(gate(r) and r['labels'][4]=='P' and r['labels'][7]=='P' for r in common)}
allinfo={'methods':{'bootstrap_unit':'task_family','bootstrap_replicates':5000,'seed':20261013,'PF':'P vs F only; U and N excluded','within_task':'trajectory P/(P+F+U); success minus failure means within each task, then equally average tasks with both outcomes and applicable rubric; CI resamples families','limitations':['descriptive associations, not causal training benefit','post-outcome full-trajectory judge can create hindsight dependence','family bootstrap intervals exploratory, not multiple-testing adjusted','P/F subset may have outcome-dependent U missingness']},'dataset':{'steps':len(rows),'trajectories':len(tr),'tasks':len({r['task_id'] for r in rows}),'families':len(families),'success_trajectories':sum(r['official_success']=='True' for r in tr),'success_steps':int(y.sum()),'success_tasks':len({r['task_id'] for r in rows if r['official_success']=='True'}),'success_families':len({r['task_family'] for r in rows if r['official_success']=='True'})},'rubrics':summary,'pairwise':pairs,'selection':selection}
(OUT/'statistics.json').write_text(json.dumps(allinfo,indent=2,ensure_ascii=False)+'\n')
with (OUT/'rubric_metrics.csv').open('w') as f:
    writer=csv.DictWriter(f,fieldnames=list(summary[0])); writer.writeheader();writer.writerows(summary)
fig,axes=plt.subplots(1,2,figsize=(11,4.8),layout='constrained')
axes[0].barh(rs,[r['coverage']*100 for r in summary],color='#478eae')
for i,r in enumerate(summary):axes[0].text(r['coverage']*100+1,i,f"{r['applicable_steps']:,}",va='center',fontsize=9)
axes[0].set(xlabel='Applicable steps (%)',xlim=(0,121),title='Coverage (P + F + U; excludes N)')
for i,r in enumerate(summary):
    low,high=r['phi_family_bootstrap_ci'];axes[1].plot([low,high],[i,i],color='#478eae');axes[1].scatter([r['phi_PF']],[i],color='#245773')
axes[1].set(yticks=range(8),yticklabels=rs,xlabel='Phi(P vs F, official trajectory success)',title='Association with success; 95% family bootstrap CI')
axes[1].axvline(0,color='gray',linestyle='--',linewidth=1)
for a in axes:a.invert_yaxis();a.spines[['top','right']].set_visible(False)
fig.savefig(OUT/'coverage_association.png',dpi=170)
print(json.dumps(allinfo,ensure_ascii=False,indent=2))
