"""Operator scripts for the one isolated V2 service, never production Workbench."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import urllib.error
import urllib.request

from bf_v2_environment import SOURCE, environment, launch

RUNTIME=Path('/Users/depengsu/.local/share/bf-agent-architecture-v2')


def request(method,path,body=None,token=None):
    profile,_=environment(RUNTIME)
    token=token or (Path(profile['home'])/'state/operator.token').read_text().strip()
    req=urllib.request.Request(f"http://127.0.0.1:{profile['port']}"+path,method=method,
        data=json.dumps(body,ensure_ascii=False).encode() if body is not None else None,
        headers={'Authorization':'Bearer '+token,'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=30) as response:return json.loads(response.read())
    except urllib.error.HTTPError as error:
        value=json.loads(error.read());raise ValueError(str(value.get('error',value))) from None


def action(owner,action,**parameters):
    return request('POST','/api/design-lab',{'session_id':owner,'action':action,**parameters})


def restart():
    p,_=environment(RUNTIME);active=Path(p['home'])/'state/active-runtime.json'
    if active.exists():
        state=json.loads(active.read_text())
        command=subprocess.run(['ps','-p',str(state['pid']),'-o','command='],capture_output=True,text=True).stdout
        if command:
            if state['port']!=p['port'] or str(Path(p['home'])/'state') not in command or not state['provider_file'].startswith(str(SOURCE)+os.sep):
                raise ValueError('V2_RESTART_IDENTITY_MISMATCH')
            os.kill(state['pid'],signal.SIGTERM)
            stop=time.monotonic()+10
            while subprocess.run(['ps','-p',str(state['pid']),'-o','stat='],capture_output=True,text=True).stdout.strip().strip('Z'):
                if time.monotonic()>stop:raise ValueError('V2_STOP_TIMEOUT')
                time.sleep(.1)
    result=launch(RUNTIME,background=True)
    stop=time.monotonic()+20
    while True:
        try:request('GET','/api/health');break
        except (OSError,urllib.error.URLError):
            if time.monotonic()>stop:raise
            time.sleep(.1)
    return result


def create_pi(title,operation,folder=None):
    return request('POST','/api/conversations',{'text':title,'operation_id':operation,
        'task_id':None,'folder_id':folder,'defer_dispatch':True})
