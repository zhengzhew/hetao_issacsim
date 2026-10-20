"""MicroDuck policies on the playing PhysX clock (200 Hz physics / 50 Hz inference).

Reuses the supplied bundle's upstream command state machine and target filtering.
No timeline.pause or second physics clock: WebRTC and physics keep updating.
"""
import time
from pathlib import Path
import numpy as np
from .adapters import JointPositionAdapter
from .duck_controller import PlaygroundController, POLICY_JOINTS, HOME_POSE
from .duck_control import smooth_position_targets
from .uploads import resolve_upload

def rotate_inverse(q,v):
    w=q[0];u=np.asarray(q[1:]);v=np.asarray(v)
    return 2*np.dot(u,v)*u+(w*w-np.dot(u,u))*v-2*w*np.cross(u,v)

class MicroDuckAdapter(JointPositionAdapter):
    def __init__(self,config,scene):
        self.subscription=None;self.error=None;self.frames=0;self.elapsed=0.;self.last_command=time.monotonic()
        super().__init__(config,scene)
        import onnxruntime as ort
        self.sessions={}
        files={'standing':'alpha_stand','walking':'alpha_walking','sitstand':'alpha_sitstand','roulade':'roulade'}
        directory=resolve_upload('challenges/microduck/policies/alpha_stand.onnx').parent
        if (directory/'ball_kick_right.onnx').exists():files['kick_right']='ball_kick_right'
        for key,name in files.items():
            options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
            net=ort.InferenceSession(str(directory/(name+'.onnx')),sess_options=options,providers=['CPUExecutionProvider'])
            if net.get_inputs()[0].shape[-1]!=61 or net.get_outputs()[0].shape[-1]!=14:raise ValueError('Unexpected MicroDuck policy dimensions')
            self.sessions[key]=net
        self.controller=PlaygroundController(set(files));self.home_policy=np.asarray(HOME_POSE,dtype=np.float32)
        self.indices=np.asarray([self.dof_names.index(n) for n in POLICY_JOINTS]);self.last_action=np.zeros(14,dtype=np.float32);self.previous=self.home_policy.copy();self.active=None;self.sample=None
        # Tensor APIs use radians; USD angular drive attributes use degrees.
        # Match the bundled Isaac Lab reference's 0.55 / 0.053 Nm/rad gains.
        self.robot.get_articulation_controller().set_gains(kps=np.full(len(self.dof_names),.55,dtype=np.float32),kds=np.full(len(self.dof_names),.053,dtype=np.float32))
        self.robot._articulation_view.set_max_joint_velocities(np.full((1,len(self.dof_names)),6.,dtype=np.float32))
        self._place_upright()
        from omni.physx import get_physx_interface
        self.subscription=get_physx_interface().subscribe_physics_step_events(self._step)
    def _place_upright(self):
        self.robot.set_world_pose(position=np.array([0.,0.,.125]),orientation=np.array([1.,0.,0.,0.]))
        self.robot.set_linear_velocity(np.zeros(3));self.robot.set_angular_velocity(np.zeros(3))
        full=np.zeros(len(self.dof_names));full[self.indices]=self.home_policy
        self.robot.set_joint_positions(full);self.robot.set_joint_velocities(np.zeros(len(full)));self.write_all(full)
    def _step(self,dt):
        if self.error:return
        try:
            self.frames+=1;self.elapsed+=float(dt)
            if self.elapsed<.02-1e-6:return
            step=self.elapsed;self.elapsed=0
            if time.monotonic()-self.last_command>.4:self.controller.set_velocity(0,0,0)
            self.controller.update(step)
            kind=self.controller.current_policy
            if kind!=self.active:
                # Authoring USD drive gains in a callback can reparse physics;
                # keep one tested gain set during motion instead.
                self.active=kind
            net=self.sessions[kind];robot=self.robot
            _,q=robot.get_world_pose()
            pos=np.asarray(robot.get_joint_positions())[self.indices];vel=np.asarray(robot.get_joint_velocities())[self.indices]
            obs=np.concatenate((rotate_inverse(q,robot.get_angular_velocity()),rotate_inverse(q,[0,0,-1]),pos-self.home_policy,vel,self.last_action,self.controller.command())).astype(np.float32).reshape(1,61)
            if not np.isfinite(obs).all():raise ValueError('MicroDuck non-finite observation')
            action=net.run(None,{net.get_inputs()[0].name:obs})[0].reshape(14)
            if not np.isfinite(action).all():raise ValueError('MicroDuck non-finite action')
            self.last_action=action
            self.sample={"policy":kind,"command":list(self.controller.command()),"steps":self.frames,"joints":pos.tolist(),"action":action.tolist()}
            target=np.asarray(smooth_position_targets(self.home_policy+self.controller.action_scale()*action,self.previous,head_alpha=.5,legs_alpha=.7),dtype=np.float32)
            self.previous=target.copy();full=np.zeros(len(self.dof_names),dtype=np.float32);full[self.indices]=target
            self.write_all(full)
        except Exception as exc:
            self.error=str(exc);print('[microduck] policy stopped: '+self.error,flush=True)
    def info(self):
        info=super().info();running=hasattr(self,'controller') and not self.error
        info.update(ready=running,policy_runtime=self.sample if running else None,policy_driven=running,policy_error=self.error,capabilities={'forward':running,'lateral':running,'yaw':running,'joints':False})
        return info
    def apply_motion(self,linear,lateral,angular):
        if self.error:raise ValueError(self.error)
        self.controller.set_velocity(linear,lateral,angular);self.last_command=time.monotonic()
        return {'accepted':True}
    def stop(self):
        if hasattr(self,'controller'):self.controller.set_velocity(0,0,0)
    def skill(self,name):
        if self.error:raise ValueError(self.error)
        ok=self.controller.request_posture(name) if name in ('sit','stand') else self.controller.trigger_timed_behavior('roulade') if name=='roll' else self.controller.trigger_timed_behavior('kick_right') if name=='kick' else False
        if not ok:raise ValueError('动作当前不可用')
        return {'accepted':True,'skill':name}
    def reset(self):
        self.error=None;self.controller.reset();self.last_action[:]=0;self.previous=self.home_policy.copy();self._place_upright()
        return {'reset':True}
    def close(self):
        self.subscription=None
