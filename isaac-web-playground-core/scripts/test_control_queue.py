import importlib.util
from pathlib import Path
import unittest
import sys
spec=importlib.util.spec_from_file_location('work_queue',Path(__file__).parents[1]/'bridge/core/work_queue.py')
module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module;spec.loader.exec_module(module)
class QueueTests(unittest.TestCase):
    def setUp(self):self.now=1.;self.q=module.WorkQueue(limit=3,clock=lambda:self.now)
    def test_expired_command_never_dispatches(self):
        work=self.q.put('teleop_sample',{'token':'a'},.2);self.now+=.3
        self.assertIsNone(self.q.take());self.assertFalse(work.reply.get_nowait()[0])
    def test_cancelled_waiter_cannot_later_execute(self):
        work=self.q.put('reset_robot',{},2);self.q.cancel(work);self.assertIsNone(self.q.take())
    def test_only_latest_pose_per_lease(self):
        old=self.q.put('teleop_sample',{'token':'a','seq':1},1)
        self.q.put('teleop_sample',{'token':'a','seq':2},1)
        self.assertEqual(self.q.take().args['seq'],2);self.assertIsNone(self.q.take());self.assertFalse(old.reply.get_nowait()[0])
    def test_other_lease_and_reliable_operations_are_preserved(self):
        self.q.put('teleop_sample',{'token':'a'},1);self.q.put('teleop_sample',{'token':'b'},1);self.q.put('reset_robot',{},1)
        self.assertEqual([self.q.take().op for _ in range(3)],['teleop_sample','teleop_sample','reset_robot'])
    def test_bounded_queue(self):
        for _ in range(3):self.q.put('ping',{},1)
        with self.assertRaises(RuntimeError):self.q.put('ping',{},1)
    def test_capture_is_coalesced(self):
        self.q.put('capture_frame',{'n':1},1);self.q.put('capture_frame',{'n':2},1)
        self.assertEqual(self.q.take().args['n'],2)
if __name__=='__main__':unittest.main()
