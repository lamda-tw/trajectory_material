"""Prespecified task/source-balanced paired descriptive estimates and family bootstrap."""
from collections import defaultdict,Counter
import random,statistics
GROUPS=['random','net3','zerofail3'];SEEDS=[20261015,20261016,20261017]
PRIMARY={'focus_A':'relevant_gap_reduced','focus_B':'grounded_application','focus_C':'coverage_progress'}
OPPORTUNITY={'relevant_gap_reduced':'A_opportunity','grounded_application':'B_opportunity','coverage_progress':'C_opportunity'}

def eligible(row,metric):return row.get(OPPORTUNITY.get(metric,''),'yes')=='yes'
def units(rows,metric,mode):
 groups=defaultdict(list);family={}
 for row in rows:
  if not eligible(row,metric):continue
  cell=() if mode=='anchor' else (row['source_group'],) if mode=='focused' else (row['mechanical_stage'],row['source_group'])
  key=cell+(row['task_id'],);groups[key].append(row[metric]);family[key]=row['family']
 return [(key[:-1],key[-1],family[key],statistics.mean(v)) for key,v in groups.items()]

def estimate_units(values,mode,weights=None):
 if not values:return None
 accum=defaultdict(lambda:[0.,0.])
 for cell,task,family,value in values:
  w=1 if weights is None else weights.get(family,0)
  accum[cell][0]+=w*value;accum[cell][1]+=w
 if mode=='anchor':expected=[()]
 elif mode=='focused':expected=[(g,) for g in GROUPS]
 elif mode=='continuation':expected=[(stage,g) for stage in 'ABC' for g in GROUPS]
 else:raise ValueError(mode)
 if any(accum[cell][1]==0 for cell in expected):return None
 return statistics.mean(accum[cell][0]/accum[cell][1] for cell in expected)

def estimate(rows,metric,mode):return estimate_units(units(rows,metric,mode),mode)

def pair_rows(rows,arm,baseline,metric):
 # Receiver is a policy stratum, not an extra independent training seed.
 def key(r):return (r['seed'],r['state_id'],r.get('receiver',''))
 lookup={key(r):r for r in rows if r['group']==baseline};out=[]
 for r in rows:
  if r['group']!=arm or not eligible(r,metric):continue
  b=lookup[key(r)];assert eligible(b,metric),'Candidate-dependent eligibility'
  for k in ['source_group','task_id','family','mechanical_stage']:assert r[k]==b[k]
  out.append(dict(r,**{metric:r[metric]-b[metric]}))
 return out

def bootstrap(rows,arm,baseline,metric,mode,iterations=5000):
 values=units(pair_rows(rows,arm,baseline,metric),metric,mode);center=estimate_units(values,mode)
 if center is None:return {'estimate':None,'low':None,'high':None,'valid_replicates':0,'attempted_replicates':0}
 families=sorted({v[2] for v in values});rng=random.Random(20261020);samples=[];attempts=0
 while len(samples)<iterations and attempts<iterations*30:
  attempts+=1;draw=Counter(rng.choices(families,k=len(families)));v=estimate_units(values,mode,draw)
  if v is not None:samples.append(v)
 samples.sort()
 return {'estimate':center,'low':samples[int(.025*len(samples))] if samples else None,'high':samples[min(len(samples)-1,int(.975*len(samples)))] if samples else None,'valid_replicates':len(samples),'attempted_replicates':attempts,'families':len(families),'interpretation':'Descriptive family-cluster resampling conditional on nonempty prespecified source/stage cells; training seeds and receiver policies fixed.'}
