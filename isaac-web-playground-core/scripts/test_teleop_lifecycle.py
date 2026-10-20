"""Exercise production teleop policy with a fake clock and an in-memory robot, without Kit."""
import collections
import importlib.util
import math
from pathlib import Path
import sys
import types
import unittest
import uuid

class TeleopTests(unittest.TestCase):
    def setUp(self):
        self.now=100.;self.stops=0
        self.robot=types.SimpleNamespace(dof_names=['joint'],limits={'joint':(-10,10)},targets={'joint':0.},set_joints=self.apply,stop=self.stop)
        prefix='isolated_teleop_test'
        package=types.ModuleType(prefix);package.__path__=[]
        context=types.ModuleType(prefix+'.app_context')
        context.ARGS=types.SimpleNamespace(teleop_max_step=.08,teleop_watchdog=.5)
        context.deque=collections.deque;context.math=math;context.uuid=uuid
        context.time=types.SimpleNamespace(monotonic=lambda:self.now,perf_counter=lambda:self.now)
        session=types.ModuleType(prefix+'.session');session.ROBOT=self.robot
        uploads=types.ModuleType(prefix+'.uploads');uploads._json_safe=lambda value:value
        self.names=[prefix,prefix+'.app_context',prefix+'.session',prefix+'.uploads',prefix+'.teleop']
        for name,value in zip(self.names,[package,context,session,uploads]):sys.modules[name]=value
        spec=importlib.util.spec_from_file_location(self.names[-1],Path(__file__).parents[1]/'bridge/core/teleop.py')
        self.module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=self.module;spec.loader.exec_module(self.module)
    def tearDown(self):
        for name in self.names:sys.modules.pop(name,None)
    def apply(self,targets,relative):self.robot.targets.update(targets);return {'targets':dict(self.robot.targets)}
    def stop(self):self.stops+=1
    def engage(self,request='request-1',source='client-a'):return self.module.teleop_engage({'requestId':request,'source':source})['token']
    def sample(self,token,seq,target=9):return self.module.teleop_sample({'token':token,'seq':seq,'positions':{'joint':target}})
    def test_ack_retry_preserves_lease_and_sequence(self):
        token=self.engage();self.now+=.05;self.sample(token,10)
        self.assertEqual(self.engage(),token);self.assertEqual(self.module.TELEOP['seq'],10)
        with self.assertRaisesRegex(ValueError,'another leader'):self.engage('request-2','client-b')
    def test_equal_elapsed_time_has_equal_slew_at_different_packet_rates(self):
        positions=[]
        for hz in (10,20,40):
            self.module.teleop_disengage();self.robot.targets={'joint':0.};token=self.engage()
            start=self.now
            for seq in range(1,hz+1):self.now=start+seq/hz;self.sample(token,seq)
            positions.append(self.robot.targets['joint'])
        for position in positions:self.assertAlmostEqual(position,1.6,places=7)
    def test_zero_elapsed_and_out_of_order_samples_cannot_move_robot(self):
        token=self.engage();self.sample(token,2);self.assertEqual(self.robot.targets['joint'],0.)
        self.now+=.05;result=self.sample(token,1,-9)
        self.assertFalse(result['applied']);self.assertEqual(self.robot.targets['joint'],0.)
    def test_silent_leader_holds_then_releases_and_cannot_stop_replacement(self):
        token=self.engage();self.now+=.6;self.module.enforce_teleop_watchdog()
        self.assertTrue(self.module.TELEOP['holding']);self.assertEqual(self.stops,1)
        self.module.enforce_teleop_watchdog();self.assertEqual(self.stops,1)
        self.now+=5;self.module.enforce_teleop_watchdog();self.assertFalse(self.module.TELEOP['engaged'])
        new_token=self.engage('request-2','client-b')
        self.module.teleop_disengage({'token':token});self.assertEqual(self.module.TELEOP['token'],new_token)
        self.assertFalse(self.sample(token,99)['applied'])
if __name__=='__main__':unittest.main()
