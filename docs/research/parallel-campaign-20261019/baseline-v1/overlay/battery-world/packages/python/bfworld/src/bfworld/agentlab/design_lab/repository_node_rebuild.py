"""Portable replay of this delivery's fixed target build; Python standard library."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def commands(bundle, sdk, compiler_bin, output):
    metadata=json.loads((bundle/'target-source/build-apparatus.json').read_text())
    roots=metadata['portable_roots']
    replacements=[(roots['bundle']+'/target',str(output)),(roots['bundle'],str(bundle)),
        (roots['sdk'],str(sdk)),(roots['compiler_bin'],str(compiler_bin))]
    def rebase(arg):
        for old,new in replacements:
            at=arg.find(old)
            if at>=0 and (at+len(old)==len(arg) or arg[at+len(old)]=='/'):
                return arg[:at]+new+arg[at+len(old):]
        return arg
    if digest(compiler_bin/'arm-none-eabi-gcc')!=metadata['compiler_sha256']:
        raise ValueError('COMPILER_DIGEST_MISMATCH')
    for path,expected in metadata['vendor_inputs_sha256'].items():
        if digest(sdk/path)!=expected: raise ValueError('SDK_SOURCE_MISMATCH:'+path)
    if digest(bundle/'nrf52832_s132.ld')!=metadata['linker_sha256']:
        raise ValueError('LINKER_DIGEST_MISMATCH')
    return [[rebase(arg) for arg in argv] for argv in metadata['command_argv']]


def main():
    parser=argparse.ArgumentParser(description='Rebuild application ELF/HEX using the pinned SDK and compiler. SoftDevice is provided separately in target/.')
    parser.add_argument('--sdk',type=Path,required=True,help='nRF5_SDK_17.1.0_ddde560 root')
    parser.add_argument('--compiler-bin',type=Path,required=True,help='GCC9 2020q2 bin directory')
    parser.add_argument('--output',type=Path,default=Path('rebuild-output'))
    parser.add_argument('--check-only',action='store_true')
    args=parser.parse_args();bundle=Path(__file__).resolve().parent
    sdk=args.sdk.resolve();compiler=args.compiler_bin.resolve();out=args.output.resolve()
    if out==bundle or out==bundle/'target': raise ValueError('USE_SEPARATE_BUILD_OUTPUT')
    argv=commands(bundle,sdk,compiler,out)
    if not args.check_only:
        (out/'objects').mkdir(parents=True,exist_ok=True)
        env={**os.environ,'PATH':str(compiler)+os.pathsep+os.environ.get('PATH','')}
        with (out/'build.log').open('w') as log:
            for command in argv:
                subprocess.run(command,cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
        equal=(out/'firmware.hex').read_bytes()==(bundle/'target/firmware.hex').read_bytes()
        (out/'rebuild-readback.json').write_text(json.dumps({'application_hex_equal':equal,'commands':len(argv)},indent=2))
        if not equal: raise ValueError('APPLICATION_HEX_DIFFERS')
    print(json.dumps({'checked':True,'compiled':not args.check_only,'commands':len(argv),'output':str(out)}))


if __name__=='__main__': main()
