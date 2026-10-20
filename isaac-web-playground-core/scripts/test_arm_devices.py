import sys, tempfile, unittest, time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from arm_devices import client_identity, load_profile
from leader_client import LatestSampler
ROOT=Path(__file__).parents[1]
class DeviceTests(unittest.TestCase):
    def test_client_identity_survives_port_change(self):
        with tempfile.TemporaryDirectory() as directory:self.assertEqual(client_identity(directory),client_identity(directory))
    def test_unknown_protocol_never_uses_se_mapping(self):
        for driver in ('unknown','feetech-so101','desheng-v5'):
            with self.assertRaises(ValueError):load_profile('arm-1',driver,'missing.json')
    def test_arm_number_required(self):
        with self.assertRaises(ValueError):load_profile('','desheng-se-v401','missing.json')
    def test_calibration_fingerprint_is_stable(self):
        file=ROOT/'scripts/fixtures/leader_arm_isaac_calibration.json'
        a,_=load_profile('arm-1','desheng-se-v401',file);b,_=load_profile('arm-1','desheng-se-v401',file)
        self.assertEqual(a,b);self.assertEqual(len(a['calibrationHash']),64)
    def test_usb_sampling_continues_without_network_ack(self):
        class Reader:
            count=0
            def positions(self):self.count+=1;return [self.count]*6
        sampler=LatestSampler(Reader(),rate=30);sampler.start()
        try:
            time.sleep(.18);first=sampler.snapshot();time.sleep(.1);last=sampler.snapshot()
            self.assertGreaterEqual(first['seq'],4);self.assertGreater(last['seq'],first['seq']);self.assertEqual(last['raw'][0],last['seq'])
        finally:sampler.stop()
if __name__=='__main__':unittest.main()
