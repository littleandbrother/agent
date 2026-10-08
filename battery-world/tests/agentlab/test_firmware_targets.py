import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from bfworld.agentlab import firmware_targets
from bfworld.agentlab.runtime_config import GCC


@unittest.skipUnless(GCC.is_file(), 'ARM compiler unavailable')
class NRFBuild(unittest.TestCase):
    def compile(self, root, code):
        startup, linker=firmware_targets.prepare_nrf(root)
        (root/'main.c').write_text(code)
        result=subprocess.run([str(GCC),'-mcpu=cortex-m4','-mthumb','-mfloat-abi=soft',
            '-Os','-ffreestanding','-fno-builtin','-nostdlib','-T'+str(linker),str(startup),
            str(root/'main.c'),'-lgcc','-o',str(root/'firmware.elf')],capture_output=True,text=True)
        return result

    def test_native_image_vector_data_and_memory_readback(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            result=self.compile(root,'volatile int data=7; volatile int bss[12]; int main(void){bss[0]=data;return bss[0];}')
            self.assertEqual(0,result.returncode,result.stderr)
            subprocess.run([str(GCC).replace('gcc','objcopy'),'-O','binary',str(root/'firmware.elf'),str(root/'firmware.bin')],check=True)
            report=firmware_targets.inspect_nrf(root/'firmware.elf',root/'firmware.bin')
            self.assertTrue(report['memory_fit']);self.assertGreaterEqual(report['ram_static_bytes'],52)
            self.assertEqual(0x20010000,report['initial_sp']);self.assertFalse(report['radio_verified'])
            raw=bytearray((root/'firmware.bin').read_bytes());raw[:4]=b'\x00'*4;(root/'bad.bin').write_bytes(raw)
            with self.assertRaisesRegex(ValueError,'VECTOR_INVALID'):
                firmware_targets.inspect_nrf(root/'firmware.elf',root/'bad.bin')

    def test_linker_rejects_ram_that_consumes_reserved_stack(self):
        with tempfile.TemporaryDirectory() as temp:
            result=self.compile(Path(temp),'volatile char memory[64000];int main(void){memory[0]=1;return memory[0];}')
            self.assertNotEqual(0,result.returncode)
            self.assertIn('RAM_OVERFLOW_WITH_STACK',result.stderr)

if __name__=='__main__':unittest.main()
