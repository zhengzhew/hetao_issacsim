"""Real-simulator smoke checks. Changes the shared virtual scene (no hardware)."""
import argparse,json,time,urllib.request
from pathlib import Path
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base',default='http://127.0.0.1:8080')
parser.add_argument('--motion-tests',action='store_true',help='Also command block pickup, walking and posture in the simulator')
args=parser.parse_args()
def api(path,data=None):
    request=urllib.request.Request(args.base.rstrip('/')+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(request,timeout=300) as response: result=json.load(response)
    if result.get('ok') is False:raise RuntimeError(result)
    return result
def status():return api('/api/challenges')['challenge']
def launch(id):
    result=api('/api/challenges/start',{'id':id})
    assert result['session']['status']=='ready',result
    time.sleep(1)
    result=status();assert not result['error'] and not result['complete'],result
    return result
checks=[]
def record(name,data):
    checks.append({'check':name,'result':data});print(name,json.dumps(data,ensure_ascii=True),flush=True)
try:
    live=api('/api/status');assert live['bridge']['result']['mock'] is False
    catalog=api('/api/catalog')['challenges'];assert len(catalog)==7
    for level in catalog:
        c=launch(level['id']);expected=4 if level['kind']=='fruit' else 1 if level['track']=='so101' or level['kind']=='kick' else 0
        assert len(c['telemetry']['objects'])==expected,c
        record('load '+level['id'],{'ready':True,'props':expected})
    if args.motion_tests:
        launch('arm-block')
        names=['Rotation','Pitch','Elbow','Wrist_Pitch','Wrist_Roll','Jaw'];current=[0]*6
        def move(q):
            global current
            steps=max(12,int(max(abs(a-b) for a,b in zip(q,current))/.025))
            for i in range(1,steps+1):
                api('/api/robot/joints',{'positions':dict(zip(names,[a+(b-a)*i/steps for a,b in zip(current,q)]))});time.sleep(.035)
            current=q;time.sleep(.6)
        move([-.383,.064,-.096,1.603,0,1])
        move([-.383,.330,.366,.876,0,1])
        move([-.383,.330,.366,.876,0,-.12])
        move([-.383,.061,-.018,1.528,0,-.12])
        lifted=status();assert lifted['telemetry']['objects'][0]['p'][2]>.075,lifted
        assert not lifted['telemetry']['robot']['released'],lifted
        move([.549,.239,-.254,1.586,0,-.12])
        move([.549,.376,.118,1.077,0,-.12])
        move([.549,.376,.118,1.077,0,1])
        move([.549,.239,-.254,1.586,0,1]);time.sleep(2)
        c=status();record('block physical pickup and release',c);assert c['complete'],c
        launch('duck-move')
        try:
            deadline=time.monotonic()+12
            while time.monotonic()<deadline:
                c=status();x,y,_=c['telemetry']['robot']['p']
                if x>.54:break
                api('/api/control',{'type':'motion','linear':.4,'angular':0});time.sleep(.10)
        finally:api('/api/control',{'type':'motion','linear':0})
        time.sleep(2);c=status();record('duck walk',c);assert c['complete'],c
        launch('duck-posture');api('/api/challenges/action',{'action':'sit'});time.sleep(3)
        seated=status();assert seated['telemetry']['robot']['p'][2]<.095,seated
        api('/api/challenges/action',{'action':'stand'});time.sleep(4)
        c=status();record('duck sit then stand',c);assert c['complete'],c
    print('PASS (HTTP and real physics; browser video is a separate check)')
finally:
    output=Path(__file__).resolve().parents[1]/'run'/'challenge-acceptance.json';output.parent.mkdir(exist_ok=True);output.write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
