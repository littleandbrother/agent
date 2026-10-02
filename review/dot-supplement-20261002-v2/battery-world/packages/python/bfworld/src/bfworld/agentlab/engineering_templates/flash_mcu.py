"""Source-bound CubeProgrammer plan and explicit operator flash/verify command."""
import argparse,hashlib,json,re,subprocess,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent
DEFAULT='/opt/ST/STM32CubeCLT_1.19.0/STM32CubeProgrammer/bin/STM32_Programmer_CLI'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser();p.add_argument('--programmer',default=DEFAULT);p.add_argument('--serial');p.add_argument('--expected-device-id');p.add_argument('--execute',action='store_true');p.add_argument('--list',action='store_true');args=p.parse_args()
    if args.list:
        subprocess.run([args.programmer,'-l','stlink'],check=True,timeout=30);return
    manifest=json.loads((ROOT/'deployment-manifest.json').read_text())
    for name,digest in manifest['files'].items():
        path=(ROOT/name).resolve()
        if not path.is_relative_to(ROOT) or not path.is_file() or sha(path)!=digest:raise SystemExit('DEPLOYMENT_FILE_CHANGED: '+name)
    binary=ROOT/'firmware.bin'
    command=[args.programmer,'-c','port=SWD','sn='+str(args.serial or '<probe-serial>'),'-w',str(binary),'0x08000000','-v','-rst']
    if not args.execute:
        print(json.dumps({'mode':'plan-only','target':manifest['target'],'binary_sha256':sha(binary),'command':command,'flashed':False,'required':'Confirm board target and wiring; execute only with --serial and --expected-device-id. Flash overwrites the selected MCU program.','documentation':'https://www.st.com/resource/en/user_manual/dm00403500-stm32cubeprogrammer-stmicroelectronics.pdf'},indent=2));return
    if not args.serial or not re.fullmatch(r'[A-Za-z0-9]+',args.serial) or not args.expected_device_id or not re.fullmatch(r'0x[0-9a-fA-F]+',args.expected_device_id):raise SystemExit('Explicit probe serial and expected device ID are required')
    probe=subprocess.run([args.programmer,'-c','port=SWD','sn='+args.serial,'mode=HOTPLUG'],capture_output=True,text=True,timeout=30)
    found=re.search(r'Device\s+ID\s*:\s*(0x[0-9a-fA-F]+)',probe.stdout+probe.stderr,re.I)
    if probe.returncode or not found or int(found.group(1),16)!=int(args.expected_device_id,16):raise SystemExit('BOARD_ID_NOT_CONFIRMED; no write executed\n'+probe.stdout+probe.stderr)
    result=subprocess.run(command,capture_output=True,text=True,timeout=60)
    receipt={'schema_version':'bf-mcu-flash-receipt-v1','time':time.time(),'target':manifest['target'],'probe_serial':args.serial,'device_id':found.group(1),'manifest_sha256':sha(ROOT/'deployment-manifest.json'),'binary_sha256':sha(binary),'argv':command,'exit_code':result.returncode,'stdout':result.stdout,'stderr':result.stderr,'flash_and_verify_command_succeeded':result.returncode==0,'functional_test_passed':False,'power_latency_measured':False}
    out=ROOT/('flash-receipt-'+str(time.time_ns())+'.json');out.write_text(json.dumps(receipt,indent=2));print(out);result.check_returncode()
if __name__=='__main__':main()
