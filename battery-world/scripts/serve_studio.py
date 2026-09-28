#!/usr/bin/env python3
"""Serve only the Studio distribution on loopback, never the repository."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
import argparse
import json
import sys
from urllib.parse import urlparse,parse_qs

REPO=Path(__file__).resolve().parents[1]
ROOT = REPO / 'apps/world-studio/dist'
sys.path.insert(0,str(REPO/'packages/python/bfworld/src'))
from bfworld.control.broker import Broker
class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=str(ROOT),**kwargs)
    def end_headers(self):
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Cache-Control','no-cache')
        super().end_headers()
    def list_directory(self,path):
        self.send_error(404)
    def json_response(self,value,status=200):
        body=json.dumps(value,allow_nan=False).encode()
        self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
    def same_host(self):
        port=self.server.server_port
        return self.headers.get('Host') in (f'127.0.0.1:{port}',f'localhost:{port}')
    def do_GET(self):
        if not self.same_host():self.send_error(403);return
        parsed=urlparse(self.path)
        try:
            if parsed.path=='/api/status':self.json_response(self.server.broker.status());return
            if parsed.path=='/api/experiment':self.json_response(self.server.broker.read(parse_qs(parsed.query)['id'][0]));return
        except (ValueError,KeyError) as exc:self.json_response({'error':str(exc)},400);return
        super().do_GET()
    def do_POST(self):
        expected=f'http://{self.headers.get("Host")}'
        if not self.same_host() or self.headers.get('Origin') not in (None,expected):self.send_error(403);return
        if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.send_error(415);return
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=65536:raise ValueError('invalid request length')
            payload=json.loads(self.rfile.read(length))
            if self.path=='/api/experiment':result=self.server.broker.request(payload)
            elif self.path=='/api/recover':result=self.server.broker.recover()
            elif self.path=='/api/submit':result=self.server.broker.submit(payload['experiment_id'],payload['content_hash'])
            else:self.send_error(404);return
            self.json_response(result)
        except (ValueError,KeyError,TypeError) as exc:self.json_response({'error':str(exc)},400)

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--state',type=Path,default=REPO/'.bfworld/studio-control')
    parser.add_argument('--budget',type=int,default=100)
    args=parser.parse_args()
    if not (ROOT/'index.html').exists():
        raise SystemExit('Build Studio first: corepack pnpm run build:studio')
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.broker=Broker(args.state,budget=args.budget)
    print(f'Battery World Studio: http://127.0.0.1:{server.server_port}',flush=True)
    server.serve_forever()
