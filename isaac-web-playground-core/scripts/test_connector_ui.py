"""Real Tk widgets with an injected fake subprocess; never opens a serial port."""
import json
from pathlib import Path
import sys
import tempfile
import tkinter as tk
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from connector_config import ConnectorConfig
from desheng_connector import ConnectorWindow
from test_connector_config import write_robot_pack
CALIBRATION=Path(__file__).parents[1]/'scripts/fixtures/leader_arm_isaac_calibration.json'
USB={'port':'COM19','description':'USB Serial','serial':'usb-1','vid':1,'pid':2}
class FakeProcess:
    returncode=None
    def poll(self):return self.returncode
class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.base=Path(self.temp.name);self.config=ConnectorConfig(self.base,self.base/'user')
        self.config.save('http://server:8080',CALIBRATION,USB);self.calls=[];self.child=FakeProcess()
        def spawn(command,**kwargs):self.calls.append(command);return self.child
        self.root=tk.Tk();self.root.withdraw();self.window=ConnectorWindow(self.root,self.config,lambda:[{**USB,'port':'COM20'}],spawn);self.root.update_idletasks()
    def tearDown(self):
        self.child.returncode=0;self.window.process=None;self.window.close();self.temp.cleanup()
    def test_remembered_configuration_connects_in_one_click(self):
        self.assertFalse(self.window.settings_open);self.window.connect_button.invoke()
        self.assertEqual(len(self.calls),1);command=self.calls[0]
        self.assertEqual(command[command.index('--port')+1],'COM20')
        self.assertEqual(command[command.index('--server')+1],'http://server:8080')
        self.assertIn('--state-dir',command);self.assertIn('--auto-connect',command);self.assertNotIn('--pair-code',command)
        self.assertEqual(str(self.window.connect_button['state']),'disabled')
    def test_stop_requests_worker_exit_and_restores_connect_button(self):
        self.window.connect();self.window.stop_button.invoke();self.assertTrue(self.window.stop_path.exists())
        self.child.returncode=0;self.root.after_cancel(self.window.timer);self.window.poll()
        self.assertIsNone(self.window.process);self.assertEqual(str(self.window.connect_button['state']),'normal')
    def test_failure_message_is_not_replaced_by_generic_exit_text(self):
        self.window.connect();self.window.log_path.write_text(json.dumps({'event':'failed','message':'服务器未启动'},ensure_ascii=False)+'\n',encoding='utf-8')
        self.child.returncode=1;self.root.after_cancel(self.window.timer);self.window.poll()
        self.assertEqual(self.window.status.get(),'服务器未启动')
    def test_pairing_error_reveals_existing_pairing_field(self):
        self.window.consume_event({'event':'pairing-required','message':'请更新配对码'})
        self.assertTrue(self.window.settings_open)
        self.assertEqual(self.window.pair_row.winfo_manager(),'grid')
        self.assertEqual(self.window.status.get(),'请更新配对码')
    def test_selected_station_is_saved_and_used_in_next_connection(self):
        choices=[{'id':'one','name':'一号'},{'id':'two','name':'二号'}]
        self.window.consume_event({'event':'station-required','stations':choices,'message':'请选择体验台'})
        self.assertTrue(self.window.settings_open);self.window.station_box.current(1);self.window.select_station()
        self.window.connect()
        self.assertEqual(self.calls[0][self.calls[0].index('--station-id')+1],'two')
        self.window.consume_event({'event':'authorized','stationId':'two','stations':choices})
        self.assertEqual(ConnectorConfig(self.base,self.base/'user').data['stationId'],'two')
    def test_file_picker_adds_second_arm_and_selector_sends_that_file_to_worker(self):
        original=self.config.data['activeProfile']
        other=self.base/'二号臂.json';content=json.loads(CALIBRATION.read_text(encoding='utf-8'));content['motors']['1']['range_min']+=50
        other.write_text(json.dumps(content,ensure_ascii=False),encoding='utf-8')
        with patch('tkinter.filedialog.askopenfilename',return_value=str(other)):
            self.window.file_button.invoke()
        selected=self.config.data['activeProfile'];self.assertNotEqual(original,selected)
        self.assertEqual(len(self.window.profile_ids),2);self.assertIn('二号臂.json',self.window.profile_selection.get())
        self.window.profile_box.current(self.window.profile_ids.index(original));self.window.select_saved_profile()
        self.assertEqual(self.config.data['activeProfile'],original)
        self.window.profile_box.current(self.window.profile_ids.index(selected));self.window.select_saved_profile()
        self.window.connect()
        command=self.calls[0];used=Path(command[command.index('--calibration')+1])
        self.assertEqual(used.read_bytes(),other.read_bytes())
        self.assertEqual(command[command.index('--arm-id')+1],self.config.data['armId'])
    def test_running_connection_keeps_its_configuration_until_stopped(self):
        selected=self.config.data['activeProfile'];self.window.connect()
        self.assertEqual(str(self.window.profile_box['state']),'disabled')
        with patch('tkinter.filedialog.askopenfilename') as picker:
            self.window.select_file();picker.assert_not_called()
        self.window.select_saved_profile()
        self.assertEqual(self.config.data['activeProfile'],selected)
    def test_pack_file_picker_auto_selects_leader_and_passes_resolved_calibration(self):
        manifest,leader,_=write_robot_pack(self.base/'门店')
        self.window.enumerate_ports=lambda:[{**USB,'serial':'follower-usb'},
                                           {**USB,'serial':'leader-usb','port':'COM30'}]
        with patch('tkinter.filedialog.askopenfilename',return_value=str(manifest)):
            self.window.file_button.invoke()
        self.assertEqual(self.window.profile_selection.get(),'测试门店')
        self.assertEqual(self.window.manual_port['port'],'COM30')
        self.assertFalse(self.window.settings_open)
        self.window.connect_button.invoke()
        command=self.calls[0]
        self.assertEqual(command[command.index('--port')+1],'COM30')
        self.assertEqual(Path(command[command.index('--calibration')+1]).read_bytes(),leader.read_bytes())
        self.assertEqual(len(self.config.profiles()),2)
        self.assertEqual(self.config.data['expectedLeaderSerial'],'leader-usb')
    def test_pack_does_not_connect_to_only_connected_follower(self):
        manifest,_,_=write_robot_pack(self.base/'门店')
        self.window.enumerate_ports=lambda:[{**USB,'serial':'follower-usb'}]
        with patch('tkinter.filedialog.askopenfilename',return_value=str(manifest)):
            self.window.file_button.invoke()
        self.assertIsNone(self.window.manual_port)
        self.assertIn('未找到此配置包的主臂',self.window.port_text.get())
        self.window.connect_button.invoke()
        self.assertEqual(self.calls,[])
    def test_saved_pre_pack_profiles_can_all_be_listed_after_upgrade(self):
        other=self.base/'other.json'
        data=json.loads(CALIBRATION.read_text(encoding='utf-8'));data['motors']['1']['range_min']+=50
        other.write_text(json.dumps(data),encoding='utf-8')
        self.config.save('http://server:8080',other)
        for profile in self.config.data['profiles'].values():
            profile.pop('profileKey',None);profile.pop('expectedLeaderSerial',None)
        self.config.file.write_text(json.dumps(self.config.data),encoding='utf-8')
        self.window.store=ConnectorConfig(self.base,self.base/'user')
        self.window.calibration.set(self.window.store.data['calibration'])
        self.window.update_summary()
        self.assertEqual(len(self.window.profile_ids),2)

if __name__=='__main__':unittest.main()
