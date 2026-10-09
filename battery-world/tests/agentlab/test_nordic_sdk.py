import tempfile,unittest,json,hashlib
from pathlib import Path
from bfworld.agentlab.nordic_sdk import ihex,validate_memory,merged_hex,validate_interface,verify_vendor_pin

def record(address,kind,body):
    q=bytes([len(body)])+address.to_bytes(2,'big')+bytes([kind])+body
    return ':'+(q+bytes([-sum(q)&255])).hex().upper()+'\n'

class NordicMemoryChecks(unittest.TestCase):
    def test_valid_linear_hex(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.hex';p.write_text(record(0,4,b'\0\2')+record(0x6000,0,b'abc')+record(0,1,b''))
            self.assertEqual(ihex(p),{0x26000:97,0x26001:98,0x26002:99})

    def test_bad_checksum_and_trailing_data(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.hex';p.write_text(':0100000001FF\n:00000001FF\n')
            with self.assertRaisesRegex(ValueError,'CHECKSUM'):ihex(p)
            p.write_text(record(0,0,b'a')+record(0,1,b'')+record(1,0,b'b'))
            with self.assertRaisesRegex(ValueError,'RECORD'):ihex(p)

    def test_conflicting_address(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'a.hex';p.write_text(record(0,0,b'a')+record(0,0,b'b')+record(0,1,b''))
            with self.assertRaisesRegex(ValueError,'CONFLICT'):ihex(p)

    def test_wrong_app_or_stack_regions(self):
        with self.assertRaisesRegex(ValueError,'APP_FLASH'):validate_memory({0:1},{})
        app={0x26000+i:b for i,b in enumerate(bytes.fromhex('0000012009600200')+b'\0\0')}
        with self.assertRaisesRegex(ValueError,'SOFTDEVICE_REGION'):validate_memory(app,{0x26000:0})

    def test_merge_readback_and_correct_interface(self):
        with tempfile.TemporaryDirectory() as d:
            app={0x26000+i:b for i,b in enumerate(bytes.fromhex('0000012009600200')+b'\0\0')};soft={0:1,0x10001014:2}
            p=Path(d)/'merged.hex';merged_hex(app,soft,p);self.assertEqual(ihex(p),{**app,**soft})
        validate_interface({'target':'nRF52832-QFAA','sdk':'17.1.0_ddde560','softdevice':'S132-7.2.0','board':'CUSTOM'})
        with self.assertRaisesRegex(ValueError,'IDENTITY'):validate_interface({'target':'STM32L432'})

    def test_changed_or_symlink_vendor_dependency_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);source=root/'header.h';source.write_text('vendor definition')
            pin=root/'pin.json';pin.write_text(json.dumps({'root':str(root),'files':{'header.h':hashlib.sha256(source.read_bytes()).hexdigest()}}))
            verify_vendor_pin(pin);source.write_text('changed')
            with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):verify_vendor_pin(pin)
            source.unlink();target=root/'other.h';target.write_text('vendor definition');source.symlink_to(target)
            with self.assertRaisesRegex(ValueError,'PIN_MISMATCH'):verify_vendor_pin(pin)

if __name__=='__main__':unittest.main()
