"""Versioned wrapper + one explicit rubric contract; never changes a verdict."""
import copy
from pathlib import Path
import sys
import common
import judge as original
from judge_compat import audit_events

ROOT=Path(__file__).resolve().parents[2]
CAL=Path(__file__).with_name('calibration_v3')
STRUCTURAL_VALIDATOR=common.validate_judgement


def load_config():
    config=copy.deepcopy(common.load_config())
    settings=common.read_json(CAL/'calibration.json')
    config['judge']['wrapper']=settings['wrapper']
    config['judge']['calibration_version']=settings['version']
    config['judge']['semantic_validator_sha256']=common.file_sha(Path(__file__))
    return config


def validate_judgement(value, rules):
    rows=STRUCTURAL_VALIDATOR(value,rules)
    matching=[i for i,r in enumerate(rules) if r['title']=='Recovers from failures']
    if len(matching)!=1:
        raise ValueError('Expected exactly one recovery rubric; re-audit the contract.')
    i=matching[0]
    if 'If no meaningful failure occurs, give +1.' not in rules[i]['evaluator_instruction']:
        raise ValueError('Recovery rubric changed; re-audit the semantic contract.')
    if rows[i]['score']==0:
        raise ValueError('Semantic contract violation: Recovers from failures cannot be NA; its specific instruction assigns +1 when no meaningful failure occurs. No score was assigned or modified.')
    return rows


original.audit_events=audit_events
original.validate_judgement=validate_judgement
build_prompt=original.build_prompt
score=original.score
