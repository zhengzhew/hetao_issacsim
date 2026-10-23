import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from urllib.error import HTTPError
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from leader_client import authorize
class AccessTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.events=[];self.calls=[]
        self.args=SimpleNamespace(server='http://server:8080',state_dir=self.temp.name,pair_code='',auto_connect=True,station_id='')
        self.principal={'role':'device','accessMode':'lan','stationId':'room1','expires':9999999999999}
        self.token='first-token'
    def tearDown(self):self.temp.cleanup()
    def emit(self,event,**data):self.events.append({'event':event,**data})
    def call(self,server,path,data=None,token=None):
        self.calls.append((path,data,token))
        if path.endswith('/connect'):return {'token':self.token,'principal':self.principal,'stations':[{'id':'room1','name':'体验台'}]}
        return {'principal':self.principal}
    def test_native_connection_remembers_and_reuses_credentials_without_pair_code(self):
        token,_=authorize(self.args,'client-test','cfg-test',self.call,self.emit)
        self.assertEqual(token,'first-token')
        authorize(self.args,'client-test','cfg-test',self.call,self.emit)
        self.assertEqual(self.calls[2][2],'first-token')
        self.assertEqual(self.calls[2][1]['stationId'],'room1')
        self.assertTrue(all(path!='/platform/pair' for path,_,_ in self.calls))
    def test_server_renewal_replaces_expired_credentials(self):
        authorize(self.args,'client-test','cfg-test',self.call,self.emit);self.token='renewed-token'
        token,_=authorize(self.args,'client-test','cfg-test',self.call,self.emit)
        self.assertEqual(token,'renewed-token')
        saved=json.loads(next(Path(self.temp.name).glob('*.json')).read_text(encoding='utf-8'))
        self.assertEqual(saved['token'],'renewed-token')
    def test_station_choice_is_returned_before_any_serial_work(self):
        def choose(*args,**kwargs):return {'chooseStation':True,'stations':[{'id':'room1','name':'一号'},{'id':'room2','name':'二号'}]}
        with self.assertRaisesRegex(RuntimeError,'请选择'):
            authorize(self.args,'client-test','cfg-test',choose,self.emit)
        self.assertEqual(self.events[0]['event'],'station-required')
        self.assertEqual(list(Path(self.temp.name).glob('*.json')),[])
    def test_wrong_network_is_not_silently_changed_to_another_authentication_mode(self):
        def forbidden(*args,**kwargs):raise HTTPError(self.args.server,403,'Forbidden',{},io.BytesIO(json.dumps({'error':'不在允许的 WLAN 子网'}).encode()))
        with self.assertRaisesRegex(RuntimeError,'WLAN'):
            authorize(self.args,'client-test','cfg-test',forbidden,self.emit)
        self.assertEqual(self.events,[])
    def test_disabled_lan_policy_requests_pair_code(self):
        for message in ('此服务器未启用局域网免配对','此服务器未配置局域网免配对'):
            self.events.clear()
            def disabled(*args,**kwargs):raise HTTPError(self.args.server,403,'Forbidden',{},io.BytesIO(json.dumps({'error':message}).encode()))
            with self.assertRaisesRegex(RuntimeError,'采集器配对码'):
                authorize(self.args,'client-test','cfg-test',disabled,self.emit)
            self.assertEqual(self.events[0]['event'],'pairing-required')
    def test_paired_mode_does_not_attempt_lan_enrollment_when_code_is_missing(self):
        self.args.auto_connect=False
        with self.assertRaisesRegex(RuntimeError,'采集器配对码'):
            authorize(self.args,'client-test','cfg-test',self.call,self.emit)
        self.assertEqual(self.calls,[])
        self.assertEqual(self.events[0]['event'],'pairing-required')
    def test_pair_code_authorization_is_reused_without_lan_enrollment(self):
        self.args.auto_connect=False;self.args.pair_code='TEST-PAIR-CODE'
        principal={'role':'device','stationId':'room1','expires':9999999999999}
        def paired(server,path,data=None,token=None):
            self.calls.append(path)
            if path=='/platform/pair':return {'token':'paired-token','principal':principal}
            if path=='/platform/me':return {'principal':principal}
            raise AssertionError('Unexpected endpoint: '+path)
        self.assertEqual(authorize(self.args,'client-test','cfg-test',paired,self.emit)[0],'paired-token')
        self.args.pair_code=''
        self.assertEqual(authorize(self.args,'client-test','cfg-test',paired,self.emit)[0],'paired-token')
        self.assertEqual(self.calls,['/platform/pair','/platform/me','/platform/me'])
    def test_explicit_pair_code_remains_compatible_and_cannot_give_a_browser_role(self):
        self.args.pair_code='ONE-TIME'
        def wrong_role(server,path,data=None,token=None):
            self.calls.append(path)
            if path.endswith('/pair'):return {'token':'browser-token'}
            return {'principal':{'role':'operator','stationId':'room1'}}
        with self.assertRaisesRegex(RuntimeError,'采集器'):
            authorize(self.args,'client-test','cfg-test',wrong_role,self.emit)
        self.assertEqual(self.calls,['/platform/pair','/platform/me'])
if __name__=='__main__':unittest.main()
