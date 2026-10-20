import sys, unittest
from unittest.mock import Mock, patch
from contextlib import redirect_stdout
from io import BytesIO, StringIO
from itertools import chain, repeat
import json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from desheng_leader import read_packet, take_reply, delta_ticks, recovery_decision, DeshengReader
import desheng_leader
from desheng_calibration import RangeCalibration
from so101_leader import SO101_JOINTS
class ReadOnlyLeaderTests(unittest.TestCase):
 def test_request_is_read(self):
  self.assertEqual(read_packet(1,0x38,2).hex(),'ffff0104023802be')
  with self.assertRaises(ValueError):read_packet(1,0x2A,2)
  with self.assertRaises(ValueError):read_packet(254,0x38,2)
 def test_partial_noise_echo(self):
  data=bytearray(b'noise'+read_packet(1,0x38,2)+bytes.fromhex('fff50104'))
  self.assertIsNone(take_reply(data,1,2));data.extend(bytes.fromhex('02085a96'))
  self.assertEqual(take_reply(data,1,2),2138)
 def test_checksum_and_other_id(self):
  data=bytearray(bytes.fromhex('fff5010402085a00 fff50204020c8e5d fff5010402085a96'))
  self.assertEqual(take_reply(data,1,2),2138)
 def test_short_reply_is_not_position(self):
  with self.assertRaises(ValueError):take_reply(bytearray.fromhex('fff5010202fa'),1,2)
 def test_wrap(self):
  self.assertEqual(delta_ticks(2,4094),4)
  self.assertEqual(delta_ticks(4094,2),-4)
  with self.assertRaises(ValueError):delta_ticks(4096,2)
class RecoveryTests(unittest.TestCase):
 def test_scene_reload(self):
  self.assertEqual(recovery_decision({'robotId':'so101','status':'ready','launchId':2},{'engaged':False},1,'us'),'reanchor')
 def test_explicit_disconnect_stays_off(self):
  self.assertEqual(recovery_decision({'robotId':'so101','status':'ready','launchId':1},{'engaged':False},1,'us'),'stop')
 def test_other_leader_not_replaced(self):
  self.assertEqual(recovery_decision({'robotId':'so101','status':'ready','launchId':2},{'engaged':True,'source':'other'},1,'us'),'stop')
 def test_transient_timeout(self):
  self.assertEqual(recovery_decision({'robotId':'so101','status':'ready','launchId':1},{'engaged':True,'source':'us'},1,'us'),'retry')
 def test_duck_stops(self):
  self.assertEqual(recovery_decision({'robotId':'microduck','status':'ready','launchId':2},{},1,'us'),'stop')
class SerialRetryTests(unittest.TestCase):
 def test_timeout_recovers(self):
  reader=object.__new__(DeshengReader)
  reader._read_once=Mock(side_effect=[TimeoutError(),2138])
  self.assertEqual(reader.read(1),2138)
  self.assertEqual(reader._read_once.call_count,2)
 def test_persistent_timeout_stops(self):
  reader=object.__new__(DeshengReader)
  reader._read_once=Mock(side_effect=TimeoutError())
  with self.assertRaises(TimeoutError):reader.read(1)
  self.assertEqual(reader._read_once.call_count,3)
 def test_invalid_data_not_retried(self):
  reader=object.__new__(DeshengReader)
  reader._read_once=Mock(side_effect=ValueError('invalid'))
  with self.assertRaises(ValueError):reader.read(1)
  self.assertEqual(reader._read_once.call_count,1)
class RangeCalibrationTests(unittest.TestCase):
 def setUp(self):
  self.document=json.loads((Path(__file__).resolve().parents[1]/'scripts/fixtures/leader_arm_calibration.json').read_text(encoding='utf-8'))
  self.mapping=RangeCalibration(self.document)
  self.limits={n:(-1.,2.) for n in SO101_JOINTS}
  self.low=[m['range_min'] for m in self.mapping.motors]
  self.high=[m['range_max'] for m in self.mapping.motors]
 def test_all_endpoints_and_midpoints(self):
  self.assertEqual(list(self.mapping.targets(self.low,self.limits).values()),[-1.]*6)
  self.assertEqual(list(self.mapping.targets(self.high,self.limits).values()),[2.]*6)
  middle=[(a+b)/2 for a,b in zip(self.low,self.high)]
  self.assertEqual(list(self.mapping.targets(middle,self.limits).values()),[.5]*6)
 def test_outside_measured_range_is_clamped(self):
  self.assertEqual(list(self.mapping.targets([0]*6,self.limits).values()),[-1.]*6)
  self.assertEqual(list(self.mapping.targets([4095]*6,self.limits).values()),[2.]*6)
 def test_drive_mode_and_simulation_override(self):
  self.document['motors']['1']['drive_mode']=1
  mapping=RangeCalibration(self.document)
  self.assertEqual(mapping.targets(self.low,self.limits)['Rotation'],2.)
  self.assertEqual(mapping.targets(self.low,self.limits,['Rotation'])['Rotation'],-1.)
 def test_hardware_offset_and_neutral_are_not_added_twice(self):
  expected=self.mapping.targets([2048]*6,self.limits)
  for m in self.document['motors'].values():
   m['hardware_middle_offset']=-1000;m['neutral']=2000;m['center']=2010
  self.assertEqual(RangeCalibration(self.document).targets([2048]*6,self.limits),expected)
 def test_missing_joint_rejected(self):
  del self.document['motors']['4']
  with self.assertRaises(ValueError):RangeCalibration(self.document)
 def test_invalid_range_rejected(self):
  self.document['motors']['2']['range_max']=0
  with self.assertRaises(ValueError):RangeCalibration(self.document)
 def test_wrong_role_rejected(self):
  self.document['role']='follower'
  with self.assertRaises(ValueError):RangeCalibration(self.document)
 def test_nonzero_software_offset_rejected(self):
  self.document['motors']['2']['homing_offset']=100
  with self.assertRaises(ValueError):RangeCalibration(self.document)
 def test_missing_simulation_limit_rejected(self):
  del self.limits['Jaw']
  with self.assertRaises(ValueError):self.mapping.targets(self.low,self.limits)
 def test_bad_encoder_sample_rejected(self):
  with self.assertRaises(ValueError):self.mapping.targets([float('nan')]*6,self.limits)
  with self.assertRaises(ValueError):self.mapping.targets([4096]*6,self.limits)
 def test_new_connection_has_same_targets(self):
  raw=[1932,3227,1032,1462,2117,2569]
  self.assertEqual(self.mapping.targets(raw,self.limits),RangeCalibration(self.document).targets(raw,self.limits))
class CalibratedLoopRegressionTests(unittest.TestCase):
 def test_large_gripper_change_does_not_end_session(self):
  config=Path(__file__).resolve().parents[1]/'scripts/fixtures/leader_arm_calibration.json'
  limits={n:[-1.,2.] for n in SO101_JOINTS}
  before=[2035,3230,1039,2975,1888,2571]
  after=[2035,3230,1039,2975,1888,1687]  # observed -884 tick change
  reader=Mock()
  reader.positions.side_effect=chain([before,before],repeat(after))
  reader.read.return_value=0
  client=Mock()
  def post(path,payload):
   if path.endswith('/engage'):
    return 200,{'ok':True,'teleop':{'token':'test','follower_joints':SO101_JOINTS,'last_positions':dict.fromkeys(SO101_JOINTS,0.)}}
   if path=='/api/teleop':return 200,{'applied':True,'targets':payload['positions'],'rate_hz':20}
   return 200,{'ok':True}
  client.post.side_effect=post
  def urlopen(url,**kwargs):
   data=({'bridge':{'result':{'session':{'status':'ready','robotId':'so101','launchId':1,'robot':{'joint_limits':limits}}}}}
         if url.endswith('/api/status') else {'teleop':{'engaged':False}})
   return BytesIO(json.dumps(data).encode())
  argv=['leader','--port','TEST','--seconds','0.2','--rate','30','--calibration',str(config)]
  with patch.object(sys,'argv',argv), patch.object(desheng_leader,'DeshengReader',return_value=reader), patch.object(desheng_leader,'Playground',return_value=client), patch.object(desheng_leader,'urlopen',side_effect=urlopen), patch.object(desheng_leader.signal,'signal'), redirect_stdout(StringIO()):
   desheng_leader.main()
  samples=[c.args[1]['positions'] for c in client.post.call_args_list if c.args[0]=='/api/teleop']
  self.assertGreaterEqual(len(samples),3)
  expected=RangeCalibration.load(config).targets(after,limits)
  self.assertEqual(samples[-1],expected)
  self.assertNotEqual(samples[0]['Jaw'],samples[-1]['Jaw'])
  reader.close.assert_called_once()
if __name__=='__main__':unittest.main()