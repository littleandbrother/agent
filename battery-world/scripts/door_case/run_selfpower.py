"""Operator reference construction. Agent entry always requires confirmation."""
import argparse
import json
from pathlib import Path
from bfworld.agentlab.door_selfpower import contracts, pipeline


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--candidate',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--reference',type=Path)
    p.add_argument('--development',action='store_true',help='No half-step; result cannot qualify')
    a=p.parse_args()
    candidate=json.loads(a.candidate.read_text())
    design=contracts.verify_design(candidate) if candidate.get('schema_version') in contracts.SCHEMAS else contracts.normalize(candidate)
    result=pipeline.run(design,a.output,source_reference=a.reference,confirm=not a.development,authority='operator-reference')
    print(json.dumps(result,ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()
