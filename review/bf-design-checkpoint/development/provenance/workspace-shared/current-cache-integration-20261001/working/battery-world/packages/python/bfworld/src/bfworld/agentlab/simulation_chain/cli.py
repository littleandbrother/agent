import argparse
import json
from pathlib import Path
from .pipeline import submit_candidate

def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path,required=True)
    a=p.parse_args();data=json.loads(a.input.read_text());params=data.get('parameters',data)
    r=submit_candidate(params.get('candidate',{}),a.output,a.cache,confirm=params.get('confirmation',True))
    print(json.dumps({'run_status':r['run_status'],'design_status':r['design_status'],'error':r.get('error')},ensure_ascii=False))

if __name__=='__main__':main()
