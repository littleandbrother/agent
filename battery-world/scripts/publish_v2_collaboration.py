#!/usr/bin/env python3
"""Publish one isolated V2 execution profile and retain its A/B predecessor."""
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import sys
import urllib.request

from v2_common import RUNTIME, restart, action
from bf_v2_environment import SOURCE


def main():
    p = json.loads((RUNTIME/'profile.json').read_text())
    release = RUNTIME/'deployment/collaboration-v1'
    release.mkdir(parents=True, exist_ok=True)
    for path in [RUNTIME/'profile.json', RUNTIME/'runtime.json', SOURCE/'.bf-development-profile.json']:
        dest = release/('previous-'+path.name)
        if not dest.exists():shutil.copyfile(path,dest);dest.chmod(0o400)
    old = json.loads((Path('/Users/depengsu/.local/share/bf-agent-runtime')/'runtime.json').read_text())
    old_home = Path(old['paths']['HOME'])
    key_path = Path(p['paths']['PROVIDER_KEY_FILE']); key_path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    current_key = Path(old['paths'].get('PROVIDER_KEY_FILE',str(old_home/'secrets/deepseek.key')))
    if not key_path.exists():shutil.copyfile(current_key,key_path);key_path.chmod(0o600)
    key = key_path.read_text().strip()
    req = urllib.request.Request('https://api.deepseek.com/user/balance', headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(req,timeout=30) as response: balance = json.loads(response.read())
    req = urllib.request.Request('https://api.deepseek.com/models', headers={'Authorization':'Bearer '+key})
    with urllib.request.urlopen(req,timeout=30) as response: models = json.loads(response.read())
    receipt = {'time_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'balance':balance,
               'model_ids':[v['id'] for v in models['data']],'credential_recorded':False,'model_calls':0}
    (release/('provider-'+str(__import__('time').time_ns())+'.json')).write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
    if not balance['is_available'] or 'deepseek-flash' not in receipt['model_ids']:raise ValueError('PROVIDER_NOT_READY')
    p.update(stage='C–F',capabilities={'model':True,'agent':True,'native':False})
    def write(path,value):
        path.chmod(0o600);path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o400)
    write(RUNTIME/'profile.json',p)
    ref={'path':str(RUNTIME/'profile.json'),'sha256':hashlib.sha256((RUNTIME/'profile.json').read_bytes()).hexdigest()}
    cfg=json.loads((RUNTIME/'runtime.json').read_text());cfg['development_profile']=ref
    write(RUNTIME/'runtime.json',cfg);write(SOURCE/'.bf-development-profile.json',ref)
    restart()
    identity=json.loads((RUNTIME/'p01-project.json').read_text())
    auth=action(identity['owner'],'authorize',wall_authorization_text='持续运行 不设置时间限制',model_profile='engineering-reasoning-efficient-v5')
    output={'profile_sha256':ref['sha256'],'capabilities':p['capabilities'],'authority':auth,
            'baseline':p['baseline'],'original_runtime_untouched':True}
    (release/'release.json').write_text(json.dumps(output,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'published':True,'port':p['port'],'owner':identity['owner'],'model':'deepseek-flash','native':False}))


if __name__=='__main__':main()
