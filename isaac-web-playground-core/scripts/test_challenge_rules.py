import importlib.util, math, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('challenge_rules',Path(__file__).parents[1]/'bridge/core/challenge_rules.py')
r=importlib.util.module_from_spec(spec);spec.loader.exec_module(r)

def obj(id='block',p=(.2,0,.02),target=(.2,0),q=(1,0,0,0),speed=0):
 return {'id':id,'p':p,'target':target,'radius':.04,'q':q,'speed':speed,'spin':0}
def hold(j,objects,robot=None,n=22):
 for _ in range(n):j.update(.05,objects,robot)

class TaskRules(unittest.TestCase):
 def test_missing_props_never_pass(self):
  j=r.Judge('fruit');hold(j,[],{'released':True});self.assertFalse(j.done)
 def test_square_zone_matches_display(self):
  j=r.Judge('block');j.lifted.add('block');o=obj(p=(.232,.032,.022));o['half_extent']=.034;hold(j,[o],{'released':True});self.assertTrue(j.done)
 def test_no_pass_without_lifting(self):
  j=r.Judge('block');hold(j,[obj()],{'released':True});self.assertFalse(j.done)
 def test_pick_place_requires_release(self):
  j=r.Judge('block');j.update(.05,[obj(p=(.2,0,.1))],{'released':False});hold(j,[obj()],{'released':False});self.assertFalse(j.done);hold(j,[obj()],{'released':True});self.assertTrue(j.done)
 def test_hover_is_not_placed(self):
  j=r.Judge('block');hold(j,[obj(p=(.2,0,.12))],{'released':True});self.assertFalse(j.done)
 def test_moving_object_not_pass(self):
  j=r.Judge('block');j.lifted.add('block');hold(j,[obj(speed=.2)],{'released':True});self.assertFalse(j.done)
 def test_die_orientation(self):
  self.assertEqual(r.die_face((1,0,0,0)),1);self.assertEqual(r.die_face((0,1,0,0)),6);self.assertIsNone(r.die_face((math.cos(math.pi/8),math.sin(math.pi/8),0,0)))
 def test_dice_requires_lift_and_correct_face(self):
  j=r.Judge('dice');hold(j,[obj(id='dice',q=(0,1,0,0))],{'released':True});self.assertFalse(j.done);j.lifted.add('dice');hold(j,[obj(id='dice')],{'released':True});self.assertFalse(j.done);hold(j,[obj(id='dice',q=(0,1,0,0))],{'released':True});self.assertTrue(j.done)
 def test_fruit_all_required(self):
  j=r.Judge('fruit');j.lifted={'a','o'};hold(j,[obj('a'),obj('o',target=(-.2,0))],{'released':True});self.assertFalse(j.done);hold(j,[obj('a'),obj('o')],{'released':True});self.assertTrue(j.done)
 def fruit_objects(self):
  return [dict(obj(name,p=(x,y,.022),target=(.16,target_y)),half_extent=.05) for name,x,y,target_y in
          [('apple1',.18966,.15694,.17),('orange1',.13960,-.18118,-.17),('apple2',.17794,.18743,.17),('orange2',.13623,-.14173,-.17)]]
 def test_fruit_placed_low_counts_without_hidden_lift(self):
  j=r.Judge('fruit');j.lifted={'apple1','orange1','apple2'}
  hold(j,self.fruit_objects(),{'released':True})
  self.assertTrue(j.done);self.assertEqual(j.progress,4)
 def test_fruit_requires_release_and_settle_time(self):
  j=r.Judge('fruit');fruit=self.fruit_objects()
  hold(j,fruit,{'released':False});self.assertFalse(j.done)
  j.update(.05,fruit,{'released':True});self.assertFalse(j.done)
  hold(j,fruit,{'released':True});self.assertTrue(j.done)
 def test_fruit_wrong_bin_does_not_count(self):
  j=r.Judge('fruit');fruit=self.fruit_objects();fruit[3]['p']=(.16,.17,.022)
  hold(j,fruit,{'released':True});self.assertFalse(j.done);self.assertEqual(j.progress,3)
 def test_fruit_moving_and_hovering_do_not_count(self):
  for change in ({'speed':.08},{'spin':.5},{'p':(.16,-.17,.12)}):
   j=r.Judge('fruit');fruit=self.fruit_objects();fruit[3].update(change)
   hold(j,fruit,{'released':True});self.assertFalse(j.done);self.assertEqual(j.progress,3)
 def test_walk_needs_upright(self):
  j=r.Judge('move');hold(j,[],{'p':(.65,0,.12),'q':(0,1,0,0),'speed':0});self.assertFalse(j.done);hold(j,[],{'p':(.65,0,.12),'q':(1,0,0,0),'speed':0});self.assertTrue(j.done)
 def test_sit_then_stand(self):
  j=r.Judge('posture');robot={'p':(0,0,.12),'q':(1,0,0,0),'speed':0};j.request='stand';hold(j,[],robot);self.assertFalse(j.done);j.request='sit';hold(j,[],dict(robot,p=(0,0,.065)));self.assertTrue(j.sat);j.request='stand';hold(j,[],robot);self.assertTrue(j.done)
 def test_yaw_not_a_roll(self):
  j=r.Judge('roll');j.request='roll'
  for i in range(81):
   a=i*math.pi/40;j.update(.02,[],{'p':(0,0,.12),'q':(math.cos(a/2),0,0,math.sin(a/2)),'speed':0})
  self.assertFalse(j.rolled)
 def test_backward_roll_not_forward(self):
  j=r.Judge('roll');j.request='roll'
  for i in range(81):
   a=-i*math.pi/40;j.update(.02,[],{'p':(0,0,.12),'q':(math.cos(a/2),0,math.sin(a/2),0),'speed':.2})
  self.assertFalse(j.rolled)
 def test_roll_and_recover(self):
  j=r.Judge('roll');j.request='roll'
  for i in range(81):
   a=i*math.pi/40;j.update(.02,[],{'p':(0,0,.12),'q':(math.cos(a/2),0,math.sin(a/2),0),'speed':.2})
  self.assertTrue(j.rolled);self.assertFalse(j.done);hold(j,[],{'p':(0,0,.12),'q':(1,0,0,0),'speed':0});self.assertTrue(j.done)

 def football(self,p=(.09,-.042,.035)):
  return {'id':'football','p':p,'origin':(.09,-.042,.035),'radius':.035,'goal_x':.55,'goal_half_width':.35,'goal_height':.25}
 def test_goal_requires_kick_request(self):
  j=r.Judge('kick');j.update(.05,[self.football()]);j.update(.05,[self.football((.7,0,.035))]);self.assertFalse(j.done)
 def test_goal_needs_whole_ball_crossing(self):
  j=r.Judge('kick');j.request='kick';j.update(.05,[self.football()]);j.update(.05,[self.football((.57,0,.035))]);self.assertFalse(j.done);j.update(.05,[self.football((.59,0,.035))]);self.assertTrue(j.done)
 def test_shot_outside_posts_is_not_goal(self):
  j=r.Judge('kick');j.request='kick';j.update(.05,[self.football((.5,.34,.035))]);j.update(.05,[self.football((.7,.34,.035))]);self.assertFalse(j.done)
 def test_shot_over_crossbar_is_not_goal(self):
  j=r.Judge('kick');j.request='kick';j.update(.05,[self.football((.5,0,.35))]);j.update(.05,[self.football((.7,0,.35))]);self.assertFalse(j.done)
 def test_backwards_and_already_in_goal_do_not_score(self):
  j=r.Judge('kick');j.request='kick';j.update(.05,[self.football((.7,0,.035))]);self.assertFalse(j.done);j.update(.05,[self.football((.4,0,.035))]);self.assertFalse(j.done)
 def test_fast_shot_crossing_is_detected(self):
  j=r.Judge('kick');j.request='kick';j.update(.05,[self.football((.4,0,.035))]);j.update(.05,[self.football((1.2,0,.035))]);self.assertTrue(j.done)
 def test_no_ball_and_reset_cannot_pass(self):
  j=r.Judge('kick');j.request='kick';hold(j,[]);self.assertFalse(j.done)
  j=r.Judge('kick');j.update(.05,[self.football()]);self.assertFalse(j.done)

if __name__=='__main__':unittest.main()
