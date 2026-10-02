"""Independent synthetic RAW parser checks. No vendor simulation or runtime."""
from pathlib import Path
import sys,unittest,tempfile,struct,math,stat,os
from types import SimpleNamespace
from unittest.mock import patch
KIT_ROOT=Path(os.environ.get('NATIVE_OBSERVATION_KIT_ROOT',str(Path(__file__).resolve().parents[1]/'native-observation-kit-v1-20261001')))
sys.path.insert(0,str(KIT_ROOT/'src'))
from retained_raw import read_raw,require_columns,require_finished_log,EvidenceError

def make_raw(times=(0,.1), *, double=True, types=('voltage','device_current'), duplicate='', ascii_mode=False):
 flags='real forward'+(' double' if double else '')
 head='Title: SYNTHETIC REVIEW FIXTURE ONLY\nPlotname: Transient Analysis\nFlags: '+flags+'\nNo. Variables: 3\nNo. Points: '+str(len(times))+'\n'+duplicate+'Variables:\n0 time time\n1 V(vin) '+types[0]+'\n2 I(Vdrive) '+types[1]+'\n'+('Values:\n' if ascii_mode else 'Binary:\n')
 if ascii_mode:payload=''.join(f'{j}\t{t}\n\t{1+j}\n\t{-0.1-j}\n' for j,t in enumerate(times)).encode('utf-16-le')
 else:payload=b''.join(struct.pack('<ddd' if double else '<dff',t,1+j,-.1-j) for j,t in enumerate(times))
 return head.encode('utf-16-le')+payload

class ReaderReview(unittest.TestCase):
 def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
 def tearDown(self):self.tmp.cleanup()
 def read(self,data):p=self.root/'test.raw';p.write_bytes(data);return read_raw(p)
 def test_double_binary(self):
  r=self.read(make_raw());self.assertEqual(list(r.time),[0,.1]);self.assertFalse(r.metadata['native_execution_authenticated']);require_columns(r,['V(vin)','I(Vdrive)'])
 def test_float_binary(self):self.assertAlmostEqual(self.read(make_raw(double=False)).columns['i(vdrive)'][0],-.1,7)
 def test_ascii(self):self.assertAlmostEqual(self.read(make_raw(ascii_mode=True)).columns['v(vin)'][1],2)
 def test_missing_channel_rejected(self):
  with self.assertRaises(EvidenceError):require_columns(self.read(make_raw()),['v(out)'])
 def test_negative_time_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw(times=(-.1,.1)))
 def test_duplicate_time_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw(times=(0,0)))
 def test_nan_time_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw(times=(0,float('nan'))))
 def test_truncated_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw()[:-1])
 def test_extra_payload_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw()+b'x')
 def test_duplicate_points_field_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw(duplicate='No. Points: 2\n'))
 def test_wrong_voltage_type_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw(types=('current','device_current')))
 def test_wrong_current_type_rejected(self):
  with self.assertRaises(EvidenceError):self.read(make_raw(types=('voltage','voltage')))
 def test_complete_numeric_measure(self):
  p=self.root/'test.log';p.write_text('Total elapsed time: 0.1 seconds\nvin_peak: MAX(V(vin))=1e-3 FROM 0 TO 2\n');self.assertEqual(require_finished_log(p,['vin_peak'])['measures']['vin_peak'],.001)
 def test_malformed_measure_rejected(self):
  p=self.root/'test.log';p.write_text('Total elapsed time: 0.1 seconds\nvin_peak: MAX(V(vin))=1.#INF FROM 0 TO 2\n')
  with self.assertRaises(EvidenceError):require_finished_log(p,['vin_peak'])
 def test_size_guard_before_loading(self):
  p=self.root/'large.raw';p.touch()
  with patch.object(Path,'stat',return_value=SimpleNamespace(st_mode=stat.S_IFREG,st_size=(1<<30)+1)),patch.object(Path,'read_bytes',side_effect=AssertionError('size limit not checked before loading')):
   with self.assertRaises(EvidenceError):read_raw(p)

if __name__=='__main__':unittest.main(verbosity=2)
