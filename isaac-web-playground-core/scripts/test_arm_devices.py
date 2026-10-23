import sys, tempfile, unittest, time, threading
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from arm_devices import client_identity, load_profile
from leader_client import LatestSampler, LatestPoseSender
ROOT=Path(__file__).parents[1]
class DeviceTests(unittest.TestCase):
    def test_client_identity_survives_port_change(self):
        with tempfile.TemporaryDirectory() as directory:self.assertEqual(client_identity(directory),client_identity(directory))
    def test_unknown_protocol_never_uses_se_mapping(self):
        for driver in ('unknown','desheng-v5'):
            with self.assertRaises(ValueError):load_profile('arm-1',driver,'missing.json')
    def test_arm_number_required(self):
        with self.assertRaises(ValueError):load_profile('','desheng-se-v401','missing.json')
    def test_calibration_fingerprint_is_stable(self):
        file=ROOT/'scripts/fixtures/leader_arm_isaac_calibration.json'
        a,_=load_profile('arm-1','desheng-se-v401',file);b,_=load_profile('arm-1','desheng-se-v401',file)
        self.assertEqual(a,b);self.assertEqual(len(a['calibrationHash']),64)
    def test_feetech_keeps_same_calibration_fingerprint_and_explicit_driver(self):
        file=ROOT/'scripts/fixtures/leader_arm_isaac_calibration.json'
        old,_=load_profile('arm-1','desheng-se-v401',file)
        new,_=load_profile('arm-1','feetech-so101',file)
        self.assertEqual(new['calibrationHash'],old['calibrationHash'])
        self.assertEqual(new['driver'],'feetech-so101')
    def test_usb_sampling_continues_without_network_ack(self):
        class Reader:
            count=0
            def positions(self):self.count+=1;return [self.count]*6
        sampler=LatestSampler(Reader());sampler.start()
        try:
            time.sleep(.18);first=sampler.snapshot();time.sleep(.1);last=sampler.snapshot()
            self.assertEqual(sampler.rate,50)
            self.assertGreaterEqual(first['seq'],7);self.assertGreater(last['seq'],first['seq']);self.assertEqual(last['raw'][0],last['seq'])
        finally:sampler.stop()
    def test_sender_discards_preconnection_and_stale_samples(self):
        now=time.monotonic();received=[];sent=threading.Event()
        samples=[{'seq':1,'monotonic':now-.1,'capturedAt':1,'raw':[1]*6},
                 {'seq':2,'monotonic':now-.3,'capturedAt':2,'raw':[2]*6},
                 {'seq':3,'monotonic':now,'capturedAt':3,'raw':[3]*6}]
        class Sampler:
            def wait_next(self,sequence):
                if samples:return samples.pop(0)
                sent.wait(.01);return None
        class Calibration:
            def targets(self,raw,limits):return {'Jaw':raw[0]}
        class Socket:
            def send(self,message):received.append(__import__('json').loads(message));sent.set()
        sender=LatestPoseSender(Sampler(),Socket(),Calibration(),now-.05)
        sender.set_clock(0);sender.set_scene({'Jaw':[0,10]},'launch');sender.start()
        try:
            self.assertTrue(sent.wait(1));self.assertEqual([row['seq'] for row in received],[3])
        finally:sender.stop()
    def test_blocked_sender_does_not_block_usb_or_replay_queued_poses(self):
        blocked=threading.Event();resume=threading.Event();second=threading.Event();received=[]
        class Reader:
            count=0
            def positions(self):self.count+=1;return [self.count]*6
        class Calibration:
            def targets(self,raw,limits):return {'Jaw':raw[0]}
        class Socket:
            def send(self,message):
                received.append(__import__('json').loads(message))
                if len(received)==1:blocked.set();resume.wait(2)
                else:second.set()
        sampler=LatestSampler(Reader());sender=LatestPoseSender(sampler,Socket(),Calibration(),time.monotonic())
        sender.set_clock(0);sender.set_scene({'Jaw':[0,100]},'launch');sampler.start();sender.start()
        try:
            self.assertTrue(blocked.wait(1));time.sleep(.12)
            captured=sampler.snapshot()['seq'];self.assertGreaterEqual(captured-received[0]['seq'],4)
            resume.set();self.assertTrue(second.wait(1))
            self.assertGreaterEqual(received[1]['seq'],captured)
        finally:resume.set();sender.stop();sampler.stop()
if __name__=='__main__':unittest.main()
