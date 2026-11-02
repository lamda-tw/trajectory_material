"""Fix the 20-state later audit panel without consulting any scoring results."""
from common import *
import io

SEED="20261021:rubric_sdpo_A:v1:manual_audit"

def main():
    samples=rows()
    selected=[]
    for group in ["semantic","execution","recovery","protocol_only","good_control"]:
        candidates=[x for x in samples if x["panel"]!="calibration_fail" and x["stratum"]==group]
        selected.extend(sorted(candidates,key=lambda x:digest([SEED,x["public_state_id"]]))[:4])
    assert len(selected)==len({x["public_state_id"] for x in selected})==20
    fields=["public_state_id","panel","stratum","task_id","trajectory_id","step"]
    buffer=io.StringIO(newline="");writer=csv.DictWriter(buffer,fieldnames=fields,extrasaction="ignore",lineterminator="\n")
    writer.writeheader();writer.writerows(selected)
    path=R/"phase_a/config/manual_audit_states.csv"
    if path.exists():assert path.read_text()==buffer.getvalue()
    else:path.write_text(buffer.getvalue())
    frozen_json(R/"phase_a/config/manual_audit_selection.json",{"seed":SEED,"states":20,
        "per_historical_stratum":4,"source":"frozen original selection CSVs only; no new labels/feedback/model output consulted",
        "sha256":sha(path),"not_replaced_if_later_ineligible":True,"candidate_audit_performed":False})
    print(json.dumps({"audit_states_fixed":20,"candidate_outputs_seen":0}))

if __name__=="__main__":main()
