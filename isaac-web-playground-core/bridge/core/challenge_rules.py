"""Deterministic task scoring; no UI command can award a pass."""
import math

def axes(q):
    w,x,y,z=q
    n=math.sqrt(sum(v*v for v in q))
    if not math.isfinite(n) or n < 1e-8: raise ValueError('invalid quaternion')
    w,x,y,z=[v/n for v in q]
    return ((1-2*(y*y+z*z),2*(x*y+w*z),2*(x*z-w*y)),
            (2*(x*y-w*z),1-2*(x*x+z*z),2*(y*z+w*x)),
            (2*(x*z+w*y),2*(y*z-w*x),1-2*(x*x+y*y)))

def die_face(q):
    # Same mapping as the physical pip geometry: +Z=1,-Z=6,+X=3,-X=4,+Y=2,-Y=5.
    a=axes(q); candidates=[(a[2][2],1),(-a[2][2],6),(a[0][2],3),(-a[0][2],4),(a[1][2],2),(-a[1][2],5)]
    alignment,face=max(candidates)
    return face if alignment>.94 else None

def inside(p,center,radius):
    return math.hypot(p[0]-center[0],p[1]-center[1]) <= radius

class Judge:
    def __init__(self, kind, target=6):
        self.kind=kind; self.target=target; self.done=False; self.stable=0.; self.lifted=set()
        self.sat=False; self.rolled=False; self.angle=0.; self.last_pitch=None; self.last_q=None
        self.last_ball=None
        self.request=None; self.message='开始挑战吧'; self.progress=0
    def update(self, dt, objects, robot=None):
        if self.done: return
        dt=max(0,min(float(dt),.1)); good=False
        if self.kind=='kick':
            if not objects:
                self.message='等待足球准备好';return
            ball=objects[0];p=ball['p'];previous=self.last_ball;self.last_ball=tuple(p)
            moved=math.hypot(p[0]-ball['origin'][0],p[1]-ball['origin'][1])
            self.progress=round(moved,3)
            self.message='点踢球，让右脚把足球踢出去' if self.request!='kick' else f'足球移动了 {moved:.2f} 米，再试着射门！'
            # Award only a front-to-back crossing of the WHOLE ball, inside the posts.
            plane=ball['goal_x']+ball['radius']
            if self.request=='kick' and previous and previous[0]<plane<=p[0]:
                fraction=(plane-previous[0])/(p[0]-previous[0])
                y=previous[1]+fraction*(p[1]-previous[1]);z=previous[2]+fraction*(p[2]-previous[2])
                if abs(y)<=ball['goal_half_width']-ball['radius'] and ball['radius']*.5<=z<=ball['goal_height']-ball['radius']:
                    self.done=True;self.message='进球啦！挑战成功！';self.progress=1
            return
        if self.kind in ('block','fruit','dice'):
            for o in objects:
                if o['p'][2]>.075:self.lifted.add(o['id'])
            settled=lambda o: o['speed']<.025 and o['spin']<.3 and .015<o['p'][2]<.06
            if self.kind=='dice':
                o=objects[0];face=die_face(o['q']) if settled(o) else None
                self.message=('朝上点数：'+str(face)) if face else '抬起、松开，等骰子落稳'
                good=o['id'] in self.lifted and settled(o) and face==self.target and bool(robot and robot.get('released'))
            else:
                # Fruit sorting scores the final classified placement, not a hidden lift height.
                count=sum((self.kind=='fruit' or o['id'] in self.lifted) and settled(o) and (all(abs(o['p'][i]-o['target'][i])<=o['half_extent'] for i in (0,1)) if 'half_extent' in o else inside(o['p'],o['target'],o['radius'])) for o in objects)
                self.progress=count;self.message=f'已完成 {count} / {len(objects)}'
                good=bool(objects) and count==len(objects) and bool(robot and robot.get("released"))
        elif robot:
            p,q=robot['p'],robot['q'];up=axes(q)[2][2];still=robot['speed']<.09
            if self.kind=='move':
                good=inside(p,(.65,0),.14) and up>.8 and still
                self.message=f'距离目标 {math.hypot(p[0]-.65,p[1]):.2f} 米'
            elif self.kind=='posture':
                if self.request=='sit' and p[2]<.095 and up>.3 and still:
                    self.stable+=dt
                    if self.stable>.5:self.sat=True;self.stable=0;self.message='坐好啦！再点站起来'
                    return
                good=self.sat and self.request=='stand' and p[2]>.108 and up>.8 and still
            else:
                a=axes(q)
                if self.request=='roll':
                    if self.last_q is not None:
                        w,x,y,z=self.last_q; W,X,Y,Z=q
                        # Local relative quaternion, accumulated about the duck's lateral axis.
                        dw=w*W+x*X+y*Y+z*Z;dy=w*Y-y*W-z*X+x*Z
                        if dw<0:dw=-dw;dy=-dy
                        self.angle+=2*math.atan2(dy,dw)
                    self.last_q=q
                    if self.angle>5.2:self.rolled=True
                good=self.rolled and up>.8 and p[2]>.1 and still
                self.message='翻过来了，站稳就成功！' if self.rolled else '点击前滚翻，观察小鸭子的动作'
        self.stable=self.stable+dt if good else 0
        if self.stable>=1.0:self.done=True;self.message='挑战成功！';self.progress=1 if self.kind not in ('block','fruit') else self.progress
