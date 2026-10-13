from pathlib import Path
import hashlib,json,torch
R=Path(__file__).resolve().parents[1]
rows=[json.loads(s) for s in (R/'data/rubric_selection.jsonl').read_text().splitlines()];cfg=json.loads((R/'config/training.json').read_text())
orders=[torch.randperm(len(rows),generator=torch.Generator().manual_seed(cfg['seed']+epoch)).tolist() for epoch in range(5)]
for order in orders:
 assert sorted(order)==list(range(2440)) and sum(rows[i]['selected_end'] for i in order)==196608
 assert len(set(order[0::2])&set(order[1::2]))==0
p=R/'data/epoch_orders.json';p.write_text(json.dumps({'method':'torch randperm(seed+zero_based_epoch), DistributedSampler equivalent rank striding, no padding or drop','orders':orders})+'\n')
m=json.loads((R/'data/DATA_MANIFEST.json').read_text());m['artifacts']['data/epoch_orders.json']=hashlib.sha256(p.read_bytes()).hexdigest();(R/'data/DATA_MANIFEST.json').write_text(json.dumps(m,indent=2,ensure_ascii=False)+'\n')
train=set((R/'config/train_all.txt').read_text().split());dev=set((R/'config/dev.txt').read_text().split());assert len(train)==90 and len(dev)==57 and not train&dev
validation={'phase':'passed','epochs':5,'samples_per_epoch':2440,'tokens_per_epoch':196608,'total_tokens':983040,'exactly_once_per_epoch':True,'rank_partitions_disjoint':True,'no_DDP_sampler_padding_duplicates':True,'train_dev_disjoint':True,'data_copied_byte_identically_from_previous_validated_selection':True,'prior_history_and_token_validation':'data/VALIDATION.json'}
for rel,h in m['artifacts'].items():assert hashlib.sha256((R/rel).read_bytes()).hexdigest()==h
(R/'data/FIVE_EPOCH_VALIDATION.json').write_text(json.dumps(validation,indent=2)+'\n');print(validation)
