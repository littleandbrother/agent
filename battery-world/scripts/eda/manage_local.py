#!/usr/bin/env python3
"""Manage one loopback typed EDA daemon. No GUI, login or engineering changes."""
import argparse
import hashlib
import json
import os
import plistlib
import shutil
import subprocess
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('status', 'install', 'restart'))
    parser.add_argument('--cli', type=Path, default=Path.home()/'.local/bin/easyeda')
    parser.add_argument('--runtime', type=Path, default=Path.home()/'.local/share/bf-agent-runtime')
    args = parser.parse_args()
    cli = args.cli.expanduser().resolve(strict=True)
    label = 'com.bf-agent.easyeda'
    domain = 'gui/'+str(os.getuid())
    target = domain+'/'+label
    plist = Path.home()/'Library/LaunchAgents'/(label+'.plist')
    base = args.runtime/'deployment/easyeda-desktop'
    logs = base/'logs'
    def run(command):
        return subprocess.run(command, capture_output=True, text=True, timeout=15)
    def health():
        result = run([str(cli), 'health'])
        return json.loads(result.stdout) if result.returncode == 0 else {'error':result.stderr[-1500:]}
    if args.action == 'status':
        result = run(['launchctl','print',target])
        print(json.dumps({'installed':plist.is_file(), 'loaded':result.returncode==0,
                          'cli':str(cli),'cli_sha256':hashlib.sha256(cli.read_bytes()).hexdigest(),
                          'health':health()},ensure_ascii=False,indent=2))
        return
    logs.mkdir(parents=True,exist_ok=True)
    spec = {'Label':label,'ProgramArguments':[str(cli),'daemon','start','--auto-update-skill=false'],
            'WorkingDirectory':str(base),'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':5,
            'StandardOutPath':str(logs/'daemon.stdout.log'), 'StandardErrorPath':str(logs/'daemon.stderr.log')}
    payload = plistlib.dumps(spec)
    loaded = run(['launchctl','print',target]).returncode == 0
    if args.action == 'install':
        plist.parent.mkdir(parents=True,exist_ok=True)
        if plist.is_file() and plist.read_bytes()!=payload:
            backup=base/('previous-launchagent-'+str(time.time_ns())+'.plist')
            shutil.copyfile(plist,backup)
        if not plist.is_file() or plist.read_bytes()!=payload:
            if loaded: run(['launchctl','bootout',target]);loaded=False
            tmp=plist.with_suffix('.plist.tmp');tmp.write_bytes(payload);tmp.chmod(0o600);tmp.replace(plist)
        if not loaded:
            # Refuse a foreign listener; daemon start itself also enforces one port.
            current=health().get('found',{}).get('raw',{})
            if current and current.get('service')!='easyeda-agent': raise RuntimeError('FOREIGN_DAEMON_LISTENER')
            if current: run([str(cli),'daemon','stop'])
            result=run(['launchctl','bootstrap',domain,str(plist)])
            if result.returncode: raise RuntimeError(result.stderr.strip())
    else:
        if not loaded: raise RuntimeError('LOCAL_EDA_LAUNCHAGENT_NOT_INSTALLED')
        result=run(['launchctl','kickstart','-k',target])
        if result.returncode: raise RuntimeError(result.stderr.strip())
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        current=health()
        if current.get('found',{}).get('raw',{}).get('status')=='ok':
            print(json.dumps({'installed':True,'loaded':True,'plist':str(plist),'health':current},ensure_ascii=False,indent=2));return
        time.sleep(0.25)
    raise RuntimeError('LOCAL_EDA_DAEMON_START_TIMEOUT')


if __name__ == '__main__': main()
