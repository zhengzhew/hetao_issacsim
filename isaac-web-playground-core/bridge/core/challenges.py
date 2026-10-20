"""Seven physics-backed playground challenges. Everything runs on the Kit thread."""
import json,math,time
from .app_context import CATALOG_DIR,omni,np,kit
from . import session
from .challenge_rules import Judge
LEVELS=json.loads((CATALOG_DIR/'challenges.json').read_text(encoding='utf-8'))['levels']
ACTIVE=None
BODIES=[]
JUDGE=None
ERROR=None
LAST=0.
ROLL_AT=None

def material(stage,path,color,friction=1.2):
    from pxr import UsdShade,UsdPhysics,Sdf,Gf
    m=UsdShade.Material.Define(stage,path);shader=UsdShade.Shader.Define(stage,path+'/Shader');shader.CreateIdAttr('UsdPreviewSurface')
    shader.CreateInput('diffuseColor',Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*color));shader.CreateInput('roughness',Sdf.ValueTypeNames.Float).Set(.65)
    m.CreateSurfaceOutput().ConnectToSource(shader.ConnectableAPI(),'surface')
    ph=UsdPhysics.MaterialAPI.Apply(m.GetPrim());ph.CreateStaticFrictionAttr().Set(friction);ph.CreateDynamicFrictionAttr().Set(friction);ph.CreateRestitutionAttr().Set(.15)
    return m

def shape(stage,path,pos,size,color,kind='cube',dynamic=False):
    from pxr import UsdGeom,UsdPhysics,UsdShade,Gf,PhysxSchema
    geo=UsdGeom.Sphere.Define(stage,path) if kind=='sphere' else UsdGeom.Cube.Define(stage,path)
    if kind=='sphere':geo.CreateRadiusAttr(.5)
    else:geo.CreateSizeAttr(1.)
    xf=UsdGeom.Xformable(geo);xf.AddTranslateOp().Set(Gf.Vec3d(*pos));xf.AddScaleOp().Set(Gf.Vec3f(*size));prim=geo.GetPrim()
    mat=material(stage,path+'/Material',color)
    binding=UsdShade.MaterialBindingAPI.Apply(prim);binding.Bind(mat);binding.Bind(mat,materialPurpose='physics')
    PhysxSchema.PhysxCollisionAPI.Apply(prim).CreateContactOffsetAttr(.001)
    UsdPhysics.CollisionAPI.Apply(prim)
    if dynamic:
        UsdPhysics.RigidBodyAPI.Apply(prim);UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(.018)
        phys=PhysxSchema.PhysxRigidBodyAPI.Apply(prim);phys.CreateEnableCCDAttr(True);phys.CreateLinearDampingAttr(.3);phys.CreateAngularDampingAttr(.5);phys.CreateMaxDepenetrationVelocityAttr(.2)
    return prim

def create_scene(scene):
    from pxr import UsdGeom,UsdPhysics,UsdLux,Gf
    omni.usd.get_context().new_stage();stage=omni.usd.get_context().get_stage();UsdGeom.SetStageUpAxis(stage,UsdGeom.Tokens.z);UsdGeom.SetStageMetersPerUnit(stage,1.)
    world=UsdGeom.Xform.Define(stage,'/World');stage.SetDefaultPrim(world.GetPrim())
    phys=UsdPhysics.Scene.Define(stage,'/World/Physics');phys.CreateGravityDirectionAttr(Gf.Vec3f(0,0,-1));phys.CreateGravityMagnitudeAttr(9.81)
    shape(stage,'/World/Floor',(0,0,-.05),(8,8,.1),(.83,.91,.86))
    # SO-101 base and task objects share the floor at z=0; no raised mount.
    light=UsdLux.DomeLight.Define(stage,'/World/Light');light.CreateIntensityAttr(900.)
    return 'procedural://challenge'

def clear():
    global ACTIVE,BODIES,JUDGE,ERROR,ROLL_AT
    ACTIVE=None;BODIES=[];JUDGE=None;ERROR=None;ROLL_AT=None

def reset_progress():
    global JUDGE,ROLL_AT,LAST
    if ACTIVE:
        JUDGE=Judge(ACTIVE['kind'],ACTIVE.get('target',6));ROLL_AT=None;LAST=time.monotonic()

def status():
    return {'level':ACTIVE,'complete':bool(JUDGE and JUDGE.done),'message':ERROR or (JUDGE.message if JUDGE else '请选择一个挑战'),'progress':JUDGE.progress if JUDGE else 0,'error':ERROR,'telemetry':snapshot() if ACTIVE else None}

def snapshot():
    objects=[]
    for o in BODIES:
        p,q=o['body'].get_world_pose();v=o['body'].get_linear_velocity();w=o['body'].get_angular_velocity()
        objects.append({k:v for k,v in o.items() if k!='body'}|{'p':p.tolist(),'q':q.tolist(),'speed':float(np.linalg.norm(v)),'spin':float(np.linalg.norm(w))})
    robot=None
    if ACTIVE and ACTIVE['track']=='microduck':
        r=session.ROBOT.robot;p,q=r.get_world_pose();robot={'p':p.tolist(),'q':q.tolist(),'speed':float(np.linalg.norm(r.get_linear_velocity()))}
    elif ACTIVE:
        joints=session.ROBOT._current_positions();robot={'released':float(joints.get('Jaw') or 0)>.65 and session.ROBOT.targets.get('Jaw',0)>.65,'joints':joints}
    return {'objects':objects,'robot':robot}

def start(level_id):
    global ACTIVE,JUDGE,BODIES,LAST
    level=next((x for x in LEVELS if x['id']==level_id),None)
    if not level:raise ValueError('未知关卡')
    clear()
    result=session.launch_session(level['sceneId'],level['robotId'])
    if result['status']!='ready':raise RuntimeError(result['error'])
    stage=omni.usd.get_context().get_stage()
    entries=[]
    if level['track']=='so101':
        # SO-101's work area is in front of the base, within its real reach.
        if level['kind']=='block':entries=[('block',(.22,.10,.04),(.22,-.10),(.97,.75,.24),'cube')]
        elif level['kind']=='dice':entries=[('dice',(.22,.08,.04),(.25,0),(.98,.98,.94),'cube')]
        else:entries=[('apple1',(.20,.04,.04),(.16,.17),(.85,.19,.21),'sphere'),('orange1',(.20,-.04,.04),(.16,-.17),(1,.52,.14),'sphere'),('apple2',(.28,-.04,.04),(.16,.17),(.85,.19,.21),'sphere'),('orange2',(.28,.04,.04),(.16,-.17),(1,.52,.14),'sphere')]
        for center,color in ([((.22,-.10),(.35,.73,.49))] if level['kind']=='block' else [((.16,.17),(.95,.63,.66)),((.16,-.17),(1,.8,.43))] if level['kind']=='fruit' else [((.25,0),(.74,.73,.94))]):
            shape(stage,'/World/Zone'+str(abs(hash(center))),(*center,.003),(.14,.14,.006) if level['kind']=='fruit' else (.10,.10,.006),color)
            if level['kind']=='fruit':
                for side,offset,size in [('l',(-.07,0),(.004,.144,.014)),('r',(.07,0),(.004,.144,.014)),('b',(0,-.07),(.144,.004,.014)),('t',(0,.07),(.144,.004,.014))]:
                    shape(stage,f'/World/Bins/{"apple" if center[1]>0 else "orange"}/{side}',(center[0]+offset[0],center[1]+offset[1],.007),size,color)
        for name,pos,target,color,kind in entries:
            prim=shape(stage,'/World/Task/'+name,pos,(.032,.032,.032),color,kind,True)
            if name=='dice':add_pips(stage,prim.GetPath().pathString)
            if name.startswith('apple'):add_leaf(stage,prim.GetPath().pathString)
            if level['kind']=='fruit':
                for side,offset,size in [('l',(-.025,0),(.004,.054,.008)),('r',(.025,0),(.004,.054,.008)),('b',(0,-.025),(.054,.004,.008)),('t',(0,.025),(.054,.004,.008))]:
                    shape(stage,f'/World/Cradles/{name}/{side}',(pos[0]+offset[0],pos[1]+offset[1],.004),size,(.69,.80,.72))
        # A low tray catches unsuccessful throws, without setting the outcome.
        for n,pos,size in [('back',(.48,0,.025),(.015,.65,.05)),('left',(.24,.325,.025),(.5,.015,.05)),('right',(.24,-.325,.025),(.5,.015,.05))]:shape(stage,'/World/Tray/'+n,pos,size,(.72,.82,.76))
        for _ in range(8):kit.update()
        from isaacsim.core.prims import SingleRigidPrim
        for name,pos,target,color,kind in entries:
            body=SingleRigidPrim('/World/Task/'+name,name=name);body.initialize()
            BODIES.append({'id':name,'body':body,'target':list(target),'radius':.035,'half_extent':.05 if level['kind']=='fruit' else .034})
    else:
        if level['kind']=='kick':
            if 'kick_right' not in session.ROBOT.sessions:raise ValueError('缺少踢球策略，请先运行 setup-challenges.ps1')
            create_football_scene(stage)
        if level['kind']=='move':shape(stage,'/World/Goal',(.65,0,.002),(.28,.28,.004),(.42,.82,.48))
        # Stage edits can resync physics. Reset only at challenge start.
        for _ in range(3):kit.update()
        session.ROBOT.reset()
        if level['kind']=='kick':
            from isaacsim.core.prims import SingleRigidPrim
            ball=SingleRigidPrim('/World/Football',name='football');ball.initialize()
            BODIES.append({'id':'football','body':ball,'origin':[.09,-.042,.035],'radius':.035,'goal_x':.55,'goal_half_width':.35,'goal_height':.25})
    from .scene import set_camera
    set_camera(session.CURRENT_SCENE)
    ACTIVE=dict(level);JUDGE=Judge(level['kind'],level.get('target',6));LAST=time.monotonic()
    return {'session':session.session_info(),'challenge':status()}


def create_football_scene(stage):
    from pxr import UsdGeom,UsdPhysics,UsdShade,PhysxSchema,Gf
    # Match the bundled reference's 70 mm / 15 g ball, placed at the right foot.
    ball=shape(stage,'/World/Football',(.09,-.042,.036),(.07,.07,.07),(.97,.98,.95),'sphere',True)
    UsdPhysics.MassAPI(ball).GetMassAttr().Set(.015)
    phys=PhysxSchema.PhysxRigidBodyAPI(ball)
    phys.GetLinearDampingAttr().Set(.05);phys.GetAngularDampingAttr().Set(.08)
    mat=material(stage,'/World/Football/BallMaterial',(.97,.98,.95),friction=.45)
    binding=UsdShade.MaterialBindingAPI.Apply(ball);binding.Bind(mat);binding.Bind(mat,materialPurpose='physics')
    # Visual pentagons move with the rigid sphere; only the sphere has collision.
    black=material(stage,'/World/Football/Black',(.035,.055,.05))
    for i,n in enumerate([(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]):
        n=np.array(n,dtype=float);u=np.cross(n,[0,0,1] if abs(n[2])<.9 else [0,1,0]);u=u/np.linalg.norm(u);v=np.cross(n,u)
        points=[]
        for k in range(5):
            a=2*math.pi*k/5;p=.48*n+.15*(math.cos(a)*u+math.sin(a)*v);p=.503*p/np.linalg.norm(p);points.append(Gf.Vec3f(*p.tolist()))
        patch=UsdGeom.Mesh.Define(stage,f'/World/Football/Patch{i}');patch.CreatePointsAttr(points);patch.CreateFaceVertexCountsAttr([5]);patch.CreateFaceVertexIndicesAttr([0,1,2,3,4]);patch.CreateDoubleSidedAttr(True);UsdShade.MaterialBindingAPI.Apply(patch.GetPrim()).Bind(black)
    shape(stage,'/World/GoalArea',(.71,0,.001),(.32,.70,.002),(.38,.74,.46))
    for name,pos,size in [
        ('LeftPost',(.55,.36,.125),(.02,.02,.25)),
        ('RightPost',(.55,-.36,.125),(.02,.02,.25)),
        ('Crossbar',(.55,0,.26),(.02,.74,.02)),
        ('GoalLine',(.55,0,.0015),(.012,.70,.003)),
    ]:shape(stage,'/World/FootballGoal/'+name,pos,size,(.98,.98,.95))
    for i in range(9):shape(stage,f'/World/FootballGoal/NetV{i}',(.85,-.35+i*.0875,.125),(.003,.003,.25),(.85,.90,.86))
    for i in range(4):shape(stage,f'/World/FootballGoal/NetH{i}',(.85,0,.025+i*.075),(.003,.70,.003),(.85,.90,.86))
    for name,pos,size in [('Left',(.35,.85,.08),(2,.025,.16)),('Right',(.35,-.85,.08),(2,.025,.16)),('Back',(-.65,0,.08),(.025,1.7,.16)),('Far',(1.35,0,.08),(.025,1.7,.16))]:
        shape(stage,'/World/Pitch/'+name,pos,size,(.65,.79,.69))

def add_pips(stage,path):
    from pxr import UsdGeom,Gf,UsdShade
    layout={1:[(0,0)],2:[(-.22,-.22),(.22,.22)],3:[(-.22,-.22),(0,0),(.22,.22)],4:[(-.22,-.22),(.22,.22),(-.22,.22),(.22,-.22)],5:[(-.22,-.22),(.22,.22),(-.22,.22),(.22,-.22),(0,0)],6:[(x,y) for x in [-.22,.22] for y in [-.26,0,.26]]}
    for axis,sign,num in [(2,1,1),(2,-1,6),(0,1,3),(0,-1,4),(1,1,2),(1,-1,5)]:
        others=[i for i in range(3) if i!=axis]
        for i,(u,v) in enumerate(layout[num]):
            p=[0.,0.,0.];p[axis]=sign*.503;p[others[0]]=u;p[others[1]]=v
            ball=UsdGeom.Sphere.Define(stage,f'{path}/Pip{num}_{i}');ball.CreateRadiusAttr(.065);UsdGeom.Xformable(ball).AddTranslateOp().Set(Gf.Vec3d(*p));UsdShade.MaterialBindingAPI.Apply(ball.GetPrim()).Bind(material(stage,f'{path}/PipMaterial',(.08,.11,.12)))

def add_leaf(stage,path):
    from pxr import UsdGeom,Gf,UsdShade
    leaf=UsdGeom.Sphere.Define(stage,path+'/Leaf');leaf.CreateRadiusAttr(.2);x=UsdGeom.Xformable(leaf);x.AddTranslateOp().Set(Gf.Vec3d(.05,0,.51));x.AddScaleOp().Set(Gf.Vec3f(1,.4,.12));UsdShade.MaterialBindingAPI.Apply(leaf.GetPrim()).Bind(material(stage,path+'/LeafMaterial',(.15,.5,.23)))

def action(name):
    global ROLL_AT
    if not ACTIVE:raise ValueError('请先选择关卡')
    if ACTIVE['track']=='microduck':
        allowed={'move':set(),'posture':{'sit','stand'},'roll':{'roll'},'kick':{'kick'}}[ACTIVE['kind']]
        if name not in allowed:raise ValueError('这个动作不属于当前关卡')
        result=session.ROBOT.skill(name);JUDGE.request=name
        if name=='roll':JUDGE.angle=0;JUDGE.last_q=None;JUDGE.rolled=False;ROLL_AT=time.monotonic()
        return result
    raise ValueError('未知关卡动作')

def tick():
    global LAST,ERROR
    if not ACTIVE or ERROR:return
    try:
        now=time.monotonic()
        if now-LAST<.05:return
        dt=now-LAST;LAST=now;data=snapshot();JUDGE.update(dt,data['objects'],data['robot'])
        if ROLL_AT and now-ROLL_AT>5 and not JUDGE.done:
            JUDGE.message='这次还没翻完整，点重新挑战，再试一次吧' if not JUDGE.rolled else '已经翻过来了，再等小鸭子站稳'
        if getattr(session.ROBOT,'error',None):ERROR=session.ROBOT.error
    except Exception as exc:ERROR=str(exc);print('[challenge] '+ERROR,flush=True)
