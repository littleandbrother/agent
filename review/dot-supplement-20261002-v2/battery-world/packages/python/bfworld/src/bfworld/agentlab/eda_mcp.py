"""Bounded stdio MCP client for the pinned JLCEDA community adapter."""
import json
import hashlib
import os
from pathlib import Path
import queue
import shutil
import subprocess
import threading
import time

INSTALL = Path.home()/'.codex/tools/bf-jlceda/easyeda-pro-mcp'
SERVER = INSTALL/'src/eda-mcp-server.mjs'
REFERENCES = Path.home()/'.codex/skills/easyeda-api/references'


class MCPError(RuntimeError):
    pass


class MCPClient:
    def __init__(self, audit=None, command=None):
        self.audit = audit or (lambda value: None)
        self.command = command or [shutil.which('node') or '/opt/homebrew/bin/node', str(SERVER)]
        self.seq = 0
        self.process = None
        self.messages = queue.Queue()
        self.source_sha256 = None
        if command is None and SERVER.is_file():
            digests={str(p.relative_to(INSTALL)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(SERVER.parent.rglob('*.mjs'))}
            self.source_sha256=hashlib.sha256(json.dumps(digests,sort_keys=True).encode()).hexdigest()

    def __enter__(self):
        self.process = subprocess.Popen(self.command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL, text=True, bufsize=1,
                                        env={**os.environ, 'EDA_MCP_NO_AUTOSTART':'1', 'EDA_API_REFERENCES_DIR':str(REFERENCES)},
                                        start_new_session=True)
        def read():
            try:
                for line in self.process.stdout:
                    if len(line)>64*1024*1024: raise MCPError('MCP_RESPONSE_TOO_LARGE')
                    self.messages.put(json.loads(line))
            except Exception as exc: self.messages.put(exc)
            finally: self.messages.put(MCPError('MCP_DISCONNECTED'))
        threading.Thread(target=read,daemon=True).start()
        try:
            self.info=self.request('initialize',{'protocolVersion':'2025-06-18','capabilities':{},'clientInfo':{'name':'bf-agent-workbench','version':'1.0'}})
            self.process.stdin.write(json.dumps({'jsonrpc':'2.0','method':'notifications/initialized'})+'\n');self.process.stdin.flush()
        except BaseException:
            self.__exit__(None,None,None)
            raise
        return self

    def __exit__(self,*args):
        if self.process:
            self.process.terminate()
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:self.process.kill();self.process.wait()
            self.process.stdin.close();self.process.stdout.close()

    def request(self,method,params,timeout=30):
        self.seq+=1;now=time.time();req={'jsonrpc':'2.0','id':self.seq,'method':method,'params':params}
        receipt={'method':method,'request':req,'started':now,'transport':'mcp-stdio','server':'easyeda-pro-mcp','server_source_sha256':self.source_sha256}
        try:
            self.process.stdin.write(json.dumps(req)+'\n');self.process.stdin.flush()
            deadline=time.monotonic()+timeout
            while True:
                try:response=self.messages.get(timeout=max(.01,deadline-time.monotonic()))
                except queue.Empty:raise MCPError('MCP_TIMEOUT_RESULT_UNKNOWN')
                if isinstance(response,Exception):raise response
                if response.get('id')==self.seq:break
                if time.monotonic()>=deadline:raise MCPError('MCP_TIMEOUT_RESULT_UNKNOWN')
            receipt['response']=response
            if 'error' in response:raise MCPError(str(response['error']))
            result=response.get('result')
            if not isinstance(result,dict):raise MCPError('MCP_RESULT_INVALID')
            if result.get('isError'):raise MCPError('\n'.join(c.get('text','') for c in result.get('content',[])))
            receipt['status']='SUCCEEDED'
            return result
        except Exception as exc:
            receipt.update(status='FAILED',error=str(exc));raise
        finally:
            receipt['duration_ms']=round((time.time()-now)*1000,1);self.audit(receipt)

    def call(self,name,args=None,timeout=30):
        return self.request('tools/call',{'name':name,'arguments':args or {}},timeout)

    def execute(self,code,window,timeout=30):
        response=self.call('eda_execute',{'code':code,'windowId':window,'timeoutMs':int(timeout*1000)},timeout+5)
        # The upstream adapter prepends a human-readable scope line to JSON.
        text='\n'.join(c.get('text','') for c in response.get('content',[]) if c.get('type')=='text')
        if text.startswith('[') and '\n' in text and not text.startswith('[\n'):text=text.split('\n',1)[1]
        try:return json.loads(text)
        except (ValueError,TypeError):raise MCPError('EDA_JSON_RESULT_INVALID: '+text[:400])
