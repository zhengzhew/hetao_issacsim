"""Paired, latest-sample leader client. USB acquisition never waits for the network."""
import argparse
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import Request
from urllib.error import HTTPError
from urllib.parse import urlparse
import websocket
from arm_devices import client_identity, load_profile, make_reader
from connector_config import atomic_json
from connector_tls import open_url, websocket_ssl_options

class LatestSampler:
    def __init__(self, reader, rate=20, clock=time.monotonic):
        self.reader=reader;self.rate=rate;self.clock=clock
        self.stop_event=threading.Event();self.lock=threading.Lock();self.latest=None;self.error=None
        self.thread=threading.Thread(target=self.run,daemon=True)
    def start(self):self.thread.start()
    def run(self):
        sequence=0;target=self.clock()
        try:
            while not self.stop_event.is_set():
                positions=self.reader.positions();sequence+=1
                sample={'raw':positions,'seq':sequence,'capturedAt':time.time()*1000,'monotonic':self.clock()}
                with self.lock:self.latest=sample
                target=max(target+1/self.rate,self.clock())
                self.stop_event.wait(max(0,target-self.clock()))
        except Exception as error:
            self.error=error;self.stop_event.set()
    def snapshot(self):
        with self.lock:return dict(self.latest) if self.latest else None
    def stop(self):
        self.stop_event.set();self.thread.join(timeout=5)
        if self.thread.is_alive():raise RuntimeError('串口读取未退出，不能重用该串口')

def log(event,**values):print(json.dumps({'event':event,**values},ensure_ascii=False),flush=True)
def request(server,path,data=None,token=None):
    headers={'Content-Type':'application/json'}
    if token:headers['Authorization']='Bearer '+token
    req=Request(server+path,data=None if data is None else json.dumps(data).encode(),headers=headers)
    with open_url(req,timeout=5) as response:return json.load(response)

def authorize(args,client_id,label,call=request,emit=log):
    import hashlib
    state=Path(args.state_dir);state.mkdir(parents=True,exist_ok=True)
    file=state/(hashlib.sha256(args.server.encode()).hexdigest()[:16]+'.json')
    saved=json.loads(file.read_text(encoding='utf-8')) if file.exists() else {}
    # Keep existing manually paired deployments usable outside the LAN shortcut.
    if args.auto_connect and not args.pair_code and saved.get('token') and saved.get('principal',{}).get('accessMode')!='lan':
        try:
            previous=call(args.server,'/platform/me',token=saved['token'])['principal']
            if previous['role']=='device' and (not args.station_id or previous['stationId']==args.station_id):
                emit('authorized',stationId=previous['stationId'],stations=saved.get('stations',[]))
                return saved['token'],previous
        except HTTPError as error:
            if error.code not in (401,403):raise
    if args.pair_code:
        saved=call(args.server,'/platform/pair',{'code':args.pair_code,'clientId':client_id,'label':label})
        atomic_json(file,saved)
    elif args.auto_connect:
        station=args.station_id or saved.get('principal',{}).get('stationId','')
        data={'clientId':client_id,'label':label}
        if station:data['stationId']=station
        try:result=call(args.server,'/platform/connector/connect',data,token=saved.get('token'))
        except HTTPError as error:
            try:message=json.loads(error.read()).get('error',str(error))
            except (ValueError,OSError):message=str(error)
            if error.code==409:raise ConnectionError(message) from None
            lan_disabled=error.code==403 and any(text in message for text in ('未启用局域网免配对','未配置局域网免配对'))
            if error.code in (401,404) or lan_disabled:
                message='这个服务器需要采集器配对码，请在主界面填写；其他配置不用重填'
                emit('pairing-required',message=message)
            raise RuntimeError(message) from None
        if result.get('chooseStation'):
            emit('station-required',stations=result['stations'],message='请选择要连接的体验台，只需选一次')
            raise RuntimeError('请选择要连接的体验台，然后再次点击连接')
        saved=result
        atomic_json(file,saved)
    token=saved.get('token')
    if not token:
        emit('pairing-required',message='请在主界面输入教师端生成的采集器配对码；其他配置已经记住')
        raise RuntimeError('请在主界面输入采集器配对码')
    try:principal=call(args.server,'/platform/me',token=token)['principal']
    except HTTPError as error:
        if error.code in (401,403):
            emit('pairing-required',message='配对已过期，请在下方输入新采集器配对码；其他配置不用重填')
            raise RuntimeError('配对已过期，请输入新采集器配对码') from None
        raise
    if principal['role']!='device':
        emit('pairing-required',message='请使用采集器配对码，而不是浏览器配对码')
        raise RuntimeError('请使用采集器配对码')
    emit('authorized',stationId=principal['stationId'],stations=saved.get('stations',[]))
    return token,principal

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['port','server','arm-id','calibration']:parser.add_argument('--'+name,required=True)
    parser.add_argument('--driver',default='desheng-se-v401')
    parser.add_argument('--pair-code',default='')
    parser.add_argument('--auto-connect',action='store_true')
    parser.add_argument('--station-id',default='')
    parser.add_argument('--state-dir',default=str(Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'HetaoIsaacConnector'))
    parser.add_argument('--rate',type=float,default=20)
    parser.add_argument('--stop-file')
    args=parser.parse_args()
    if not 1<=args.rate<=30:parser.error('rate must be 1..30')
    server=args.server=args.server.rstrip('/');parsed=urlparse(server)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.path not in ('','/') or parsed.username:
        parser.error('server must be an HTTP(S) origin')
    state=Path(args.state_dir);client_id=client_identity(state)
    profile,calibration=load_profile(args.arm_id,args.driver,args.calibration)
    token,principal=authorize(args,client_id,profile['armId'])
    args.pair_code='' # One-time codes must never be replayed during reconnect.
    stop=Path(args.stop_file) if args.stop_file else None
    if stop and stop.exists():raise RuntimeError('停止标记已存在')
    reader=make_reader(args.driver,args.port);sampler=LatestSampler(reader,args.rate)
    reader.open()
    try:initial=reader.positions()
    except Exception:
        reader.close();raise
    sampler.start();attempt=0;refresh_auth=False
    log('serial-ready',port=args.port,driver=args.driver,baud=reader.port.baudrate,raw=initial,armId=args.arm_id,clientId=client_id,servo_writes=False)
    try:
        while not (stop and stop.exists()):
            if sampler.error:raise sampler.error
            ws=None
            try:
                if args.auto_connect and (refresh_auth or principal.get('expires',0)<time.time()*1000+30000):
                    token,principal=authorize(args,client_id,profile['armId']);refresh_auth=False
                endpoint=('wss' if parsed.scheme=='https' else 'ws')+'://'+parsed.netloc+'/platform/teleop'
                ws=websocket.create_connection(endpoint,header={'Authorization':'Bearer '+token},timeout=3,suppress_origin=True,enable_multithread=True,http_no_proxy=[parsed.hostname],sslopt=websocket_ssl_options(endpoint))
                ws.settimeout(.02)
                start_wall=time.time()*1000;start_mono=time.monotonic()
                ws.send(json.dumps({'type':'clock','echo':start_wall}))
                hello={k:profile[k] for k in ['armId','driver','calibrationHash']}
                ws.send(json.dumps({'type':'hello',**hello,'port':args.port}))
                limits=None;launch=None;offset=None;last_seq=0;report=0;last_reply=time.monotonic();connected_at=time.monotonic();attempt=0
                while not (stop and stop.exists()):
                    if sampler.error:raise sampler.error
                    try:
                        raw=ws.recv()
                        if not raw:raise ConnectionError('服务器已断开')
                        message=json.loads(raw);last_reply=time.monotonic()
                        if message['type']=='clock':
                            offset=message['serverTime']-(start_wall+(time.monotonic()-start_mono)*500)
                        elif message['type']=='ready':
                            limits=message['limits'];calibration.validate_limits(limits);launch=message['launchId']
                            log('scene-reconnected',launchId=launch)
                        elif message['type']=='applied' and time.monotonic()-report>=2:
                            report=time.monotonic();log('following',samples=message['seq'],rate_hz=message.get('rate_hz'),ack_ms=message.get('ackMs'))
                        elif message['type'] in ('error','waiting'):
                            if message['type']=='waiting':limits=None
                            log(message['type'],reason=message.get('message'))
                            if message.get('fatal'):raise RuntimeError(message.get('message','设备配置无效'))
                    except websocket.WebSocketTimeoutException:pass
                    if time.monotonic()-last_reply>8:raise ConnectionError('服务器响应中断')
                    if time.monotonic()-start_mono>30:
                        start_wall=time.time()*1000;start_mono=time.monotonic();ws.send(json.dumps({'type':'clock','echo':start_wall}))
                    sample=sampler.snapshot()
                    # Reconnects may never replay the sample cached before connecting.
                    if limits and offset is not None and sample and sample['seq']>last_seq and sample['monotonic']>=connected_at and time.monotonic()-sample['monotonic']<.15:
                        ws.send(json.dumps({'type':'sample','seq':sample['seq'],'capturedAt':sample['capturedAt']+offset,'launchId':launch,'positions':calibration.targets(sample['raw'],limits)}))
                        last_seq=sample['seq']
            except (OSError,ConnectionError,websocket.WebSocketException) as error:
                refresh_auth=args.auto_connect
                attempt+=1;log('reconnecting',reason=str(error))
                if attempt>=10:raise RuntimeError('连续连接失败，请检查配对状态和服务器') from error
                for _ in range(min(attempt,5)*10):
                    if stop and stop.exists():break
                    time.sleep(.1)
            finally:
                if ws:ws.close()
    finally:
        try:sampler.stop()
        finally:reader.close()
        log('closed',port=args.port)

if __name__=='__main__':main()
