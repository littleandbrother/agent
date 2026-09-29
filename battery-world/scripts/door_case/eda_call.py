"""Recorded calls to the existing local official EDA API Gateway."""
import argparse, json, sys, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'packages/python/bfworld/src'))
from bfworld.agentlab.eda_mcp import MCPClient

def main():
 p=argparse.ArgumentParser();p.add_argument('script',type=Path);p.add_argument('output',type=Path);a=p.parse_args()
 receipt=[]
 with MCPClient(receipt.append) as c:
  result=c.execute(a.script.read_text(),'4c249666-ce38-45a8-892f-10180607b75c',120)
 a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2))
 a.output.with_suffix('.receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2))
 print(str(a.output))
if __name__=='__main__':main()
