"""Export final answer text only, excluding reasoning blocks and tool payloads."""
import hashlib
import json
from pathlib import Path
import sys

APP=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(APP/'scripts'))
from run_organization_pilot import read_trial_final
from v2_common import RUNTIME


def read(path):return json.loads(path.read_text())


def main():
    root=RUNTIME/'continuous-design';registry=read(root/'pilot/registry.json');rows=[]
    for entry in registry['trials']:
        final=read_trial_final(root/'pilot/trials'/entry['key'])
        trace=RUNTIME/'workbench/sessions'/entry['owner']/'trace.jsonl'
        messages=[e.get('message',{}) for e in map(json.loads,trace.read_text().splitlines())
            if e.get('type')=='message' and e.get('message',{}).get('role')=='assistant']
        message=messages[-1] if messages else {}
        has_tools=any(b.get('type') in ('toolCall','tool_call') for b in message.get('content',[]))
        text='\n'.join(b.get('text','') for b in message.get('content',[]) if b.get('type')=='text')
        rows.append({'trial':entry['key'],'owner':entry['owner'],'status':final['state']['status'],
            'current_system':final['metrics']['current_system'],'final_text':text,
            'text_sha256':hashlib.sha256(text.encode()).hexdigest(),
            'message_stop_reason':message.get('stopReason'),'has_tool_calls':has_tools,
            'complete_final_answer':bool(text) and not has_tools})
    destination=Path(__file__).parent/'results/public-final-answers.json'
    destination.write_text(json.dumps({'scope':'assistant final text blocks only','answers':rows},
        ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'answers':len(rows),'path':str(destination)}))


if __name__=='__main__':main()
