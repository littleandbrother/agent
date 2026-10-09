import struct,unittest
from bfworld.agentlab.stm32_l432 import validate_hex,validate_interface,FLASH,FLASH_END,RAM_END

class STM32TargetChecks(unittest.TestCase):
    def valid(self):return {FLASH+i:b for i,b in enumerate(struct.pack('<II',RAM_END,FLASH+9)+b'\x00\x00')}
    def test_exact_target(self):
        validate_interface({'target':'STM32L432KCU6','units':'SI'})
        with self.assertRaisesRegex(ValueError,'TARGET'):validate_interface({'target':'STM32L031K6T6','units':'SI'})
    def test_vector_thumb_and_stack(self):
        self.assertEqual(validate_hex(self.valid()),(RAM_END,FLASH+9))
        for changed in [struct.pack('<II',RAM_END-1,FLASH+9),struct.pack('<II',RAM_END,FLASH+8)]:
            q=self.valid();q.update({FLASH+i:b for i,b in enumerate(changed)})
            with self.assertRaisesRegex(ValueError,'VECTOR_INVALID'):validate_hex(q)
    def test_outside_flash_and_missing_vector(self):
        q=self.valid();q[FLASH_END]=1
        with self.assertRaisesRegex(ValueError,'FLASH_REGION'):validate_hex(q)
        q=self.valid();del q[FLASH+3]
        with self.assertRaisesRegex(ValueError,'VECTOR_MISSING'):validate_hex(q)

if __name__=='__main__':unittest.main()
