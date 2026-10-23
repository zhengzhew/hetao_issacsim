import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0,str(Path(__file__).parents[1]/'tools'))
from connector_config import ConnectorConfig,calibration_profile,choose_port,normalize_server
from desheng_calibration import RangeCalibration, NAMED_JOINTS
from so101_leader import SO101_JOINTS
ROOT=Path(__file__).parents[1]
CALIBRATION=ROOT/'scripts/fixtures/leader_arm_isaac_calibration.json'
USB={'port':'COM19','description':'USB Serial','serial':'usb-1','vid':1,'pid':2}
class ConfigTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.package=self.root/'package';self.package.mkdir();self.state=self.root/'user'
    def tearDown(self):self.temp.cleanup()
    def test_restart_keeps_server_and_calibration_after_original_is_deleted(self):
        file=self.root/'selected.json';file.write_bytes(CALIBRATION.read_bytes())
        store=ConnectorConfig(self.package,self.state);first=store.save('192.168.8.57:8080',file,USB);file.unlink()
        restored=ConnectorConfig(self.package,self.state)
        self.assertEqual(restored.data['server'],'http://192.168.8.57:8080');self.assertTrue(Path(restored.data['calibration']).exists())
        self.assertEqual(calibration_profile(restored.data['calibration'])['calibrationHash'],first['calibrationHash'])
    def test_unpacking_new_program_version_keeps_user_choices(self):
        store=ConnectorConfig(self.package,self.state);store.save('http://server:8080',CALIBRATION,USB)
        other=self.root/'new-version';other.mkdir();(other/'connector.json').write_text(json.dumps({'server':'http://localhost:8080'}))
        self.assertEqual(ConnectorConfig(other,self.state).data['server'],'http://server:8080')
    def test_paired_release_overrides_legacy_lan_setting_and_preserves_arm(self):
        store=ConnectorConfig(self.package,self.state)
        saved=store.save('https://10.72.255.16',CALIBRATION,USB)
        saved.update({'autoConnect':True,'connectionMode':'lan'})
        store.file.write_text(json.dumps(saved),encoding='utf-8')
        (self.package/'connector.json').write_text(json.dumps({'server':'','autoConnect':False,'connectionMode':'pair-code'}))
        updated=ConnectorConfig(self.package,self.state)
        self.assertFalse(updated.data['autoConnect'])
        self.assertEqual(updated.data['server'],saved['server'])
        self.assertEqual(updated.data['profiles'],saved['profiles'])
        self.assertEqual(updated.data['activeProfile'],saved['activeProfile'])
        updated.remember_server(saved['server'])
        self.assertFalse(ConnectorConfig(self.package,self.state).data['autoConnect'])
    def test_first_use_does_not_guess_an_arm_from_nearby_files(self):
        for name in ('leader_arm_calibration.json','leader_arm_isaac_calibration.json'):(self.package/name).write_bytes(CALIBRATION.read_bytes())
        store=ConnectorConfig(self.package,self.state,downloads=self.package)
        self.assertEqual(store.data['calibration'],'');self.assertEqual(store.profiles(),[])
    def test_legacy_lan_package_cannot_restore_enrollment_in_v6(self):
        (self.package/'connector.json').write_text(json.dumps({'connectionMode':'pair-code'}))
        paired=ConnectorConfig(self.package,self.state)
        saved=paired.save('https://10.72.255.16',CALIBRATION,USB)
        self.assertFalse(saved['autoConnect'])
        (self.package/'connector.json').write_text(json.dumps({'connectionMode':'lan','hardwareDriver':'feetech-so101'}))
        lan=ConnectorConfig(self.package,self.state)
        self.assertFalse(lan.data['autoConnect'])
        self.assertEqual(lan.data['connectionMode'],'pair-code')
        self.assertEqual(lan.data['driver'],'feetech-so101')
        self.assertEqual(lan.data['armId'],saved['armId'])
        self.assertEqual(lan.data['server'],saved['server'])
    def test_wrong_json_does_not_replace_saved_configuration(self):
        store=ConnectorConfig(self.package,self.state);store.save('http://server:8080',CALIBRATION,USB);before=store.file.read_bytes()
        bad=self.root/'not-a-calibration.json';bad.write_text('{}')
        with self.assertRaises(ValueError):store.save('http://other:8080',bad,USB)
        self.assertEqual(store.file.read_bytes(),before)
    def test_usb_serial_recovers_port_after_com_number_changes(self):
        moved={**USB,'port':'COM21'}
        self.assertEqual(choose_port([moved],USB),moved)
    def test_wrong_usb_or_duplicate_serial_does_not_get_auto_selected(self):
        self.assertIsNone(choose_port([{**USB,'serial':'different'}],USB))
        self.assertIsNone(choose_port([USB,{**USB,'port':'COM20'}],USB))
    def test_bluetooth_is_not_chosen_and_multiple_usb_requires_selection(self):
        self.assertIsNone(choose_port([{'port':'COM11','vid':None,'pid':None}],None))
        self.assertIsNone(choose_port([USB,{**USB,'port':'COM20'}],None))
        self.assertEqual(choose_port([USB],None),USB)
    def test_configuration_identifier_is_stable_without_manual_arm_number(self):
        self.assertEqual(calibration_profile(CALIBRATION),calibration_profile(CALIBRATION))
    def test_origin_accepts_plain_ip_but_rejects_paths_and_credentials(self):
        self.assertEqual(normalize_server(' 192.168.8.57 '),'http://192.168.8.57:8080')
        for value in ('http://user:pass@host:8080','http://host:8080/file','http://host:8080?token=a'):
            with self.assertRaises(ValueError):normalize_server(value)
    def arm_file(self,name,minimum_delta=0):
        file=self.root/name;file.parent.mkdir(parents=True,exist_ok=True)
        content=json.loads(CALIBRATION.read_text(encoding='utf-8'));content['motors']['1']['range_min']+=minimum_delta
        file.write_text(json.dumps(content,ensure_ascii=False),encoding='utf-8');return file
    def test_each_arm_keeps_its_calibration_and_port_after_restart(self):
        arm_a=self.arm_file('一号臂.json');arm_b=self.arm_file('二号臂.json',50)
        store=ConnectorConfig(self.package,self.state)
        first=store.save('http://server:8080',arm_a,USB)
        other_usb={**USB,'port':'COM25','serial':'usb-2'}
        second=store.save('http://server:8080',arm_b,other_usb)
        restored=ConnectorConfig(self.package,self.state)
        self.assertEqual(restored.data['activeProfile'],second['calibrationHash'])
        a=restored.select_profile(first['calibrationHash']);self.assertEqual(a['portIdentity'],USB)
        b=restored.select_profile(second['calibrationHash']);self.assertEqual(b['portIdentity'],other_usb)
        self.assertEqual(Path(a['calibration']).read_bytes(),arm_a.read_bytes())
        self.assertEqual(Path(b['calibration']).read_bytes(),arm_b.read_bytes())
    def test_same_filenames_remain_separate_after_originals_are_moved(self):
        arm_a=self.arm_file('one/leader_arm_calibration.json');arm_b=self.arm_file('two/leader_arm_calibration.json',50)
        store=ConnectorConfig(self.package,self.state)
        first=store.save('http://server:8080',arm_a,USB);second=store.save('http://server:8080',arm_b)
        arm_a.unlink();arm_b.unlink()
        for saved in (first,second):
            active=store.select_profile(saved['calibrationHash'])
            self.assertTrue(Path(active['calibration']).exists())
            self.assertEqual(active['calibrationName'],'leader_arm_calibration.json')
        self.assertEqual(len(store.profiles()),2)
    def test_changed_source_needs_explicit_import_to_replace_the_selected_values(self):
        source=self.arm_file('leader.json');store=ConnectorConfig(self.package,self.state)
        first=store.save('http://server:8080',source,USB)
        self.arm_file('leader.json',50)
        restored=ConnectorConfig(self.package,self.state)
        self.assertEqual(calibration_profile(restored.data['calibration'])['calibrationHash'],first['calibrationHash'])
        second=restored.save('http://server:8080',source)
        self.assertNotEqual(second['calibrationHash'],first['calibrationHash'])
        self.assertEqual(restored.select_profile(first['calibrationHash'])['calibrationHash'],first['calibrationHash'])
    def test_legacy_single_file_settings_migrate_with_the_original_name_and_port(self):
        source=self.arm_file('my-arm.json');profile=calibration_profile(source)
        cache=self.state/'calibrations'/(profile['calibrationHash']+'.json');cache.parent.mkdir(parents=True);cache.write_bytes(source.read_bytes())
        legacy={'server':'http://server:8080','calibration':str(cache),'sourceCalibration':str(source),'calibrationHash':profile['calibrationHash'],'portIdentity':USB}
        (self.state/'simple-connector.json').write_text(json.dumps(legacy),encoding='utf-8');source.unlink()
        store=ConnectorConfig(self.package,self.state)
        self.assertEqual(store.data['calibrationName'],'my-arm.json');self.assertEqual(len(store.profiles()),1)
        store.save(store.data['server'],store.data['calibration'],USB)
        restored=ConnectorConfig(self.package,self.state)
        self.assertEqual(restored.data['calibrationName'],'my-arm.json');self.assertEqual(restored.data['portIdentity'],USB)
    def test_missing_selected_profile_does_not_fall_back_to_a_different_arm(self):
        source_a=self.arm_file('one.json');source_b=self.arm_file('two.json',50)
        store=ConnectorConfig(self.package,self.state)
        first=store.save('http://server:8080',source_a,USB);second=store.save('http://server:8080',source_b)
        store.select_profile(first['calibrationHash']);Path(first['calibration']).unlink();source_a.unlink()
        restored=ConnectorConfig(self.package,self.state)
        self.assertEqual(restored.data['calibration'],'')
        self.assertIn('找不到',restored.notice)
        self.assertEqual(restored.select_profile(second['calibrationHash'])['calibrationName'],'two.json')

def write_robot_pack(root, serial='leader-usb', label='测试门店'):
    root.mkdir(parents=True,exist_ok=True)
    document={name:{'id':sid,'drive_mode':0,'homing_offset':-1200+sid*300,
                    'range_min':800+sid*10,'range_max':3200-sid*10}
              for sid,name in enumerate(NAMED_JOINTS,1)}
    # The wrist can span the complete encoder range; the gripper is asymmetric.
    document['wrist_roll'].update(range_min=0,range_max=4095)
    document['gripper'].update(range_min=2045,range_max=3238)
    leader=root/'calibration/teleoperators/so_leader/leader.json'
    leader.parent.mkdir(parents=True);leader.write_text(json.dumps(document),encoding='utf-8')
    follower=root/'calibration/follower.json';follower.write_text('{"should_not_be_read":true}')
    manifest=root/'门店.robot.json'
    manifest.write_text(json.dumps({'profile_version':1,'label':label,
        'program':'missing.exe','arguments':['--do-not-run'],'motor_ids':[1,2,3,4,5,6],
        'calibration':{'leader_output':leader.relative_to(root).as_posix(),
                       'follower_output':follower.relative_to(root).as_posix(),'tool':'missing-tool.exe'},
        'expected_devices':[{'runtime_role':'follower','fingerprint':'serial:follower-usb'},
                            {'runtime_role':'leader','fingerprint':'serial:'+serial}]},
        ensure_ascii=False),encoding='utf-8-sig')
    return manifest,leader,document


class RobotPackTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.store=ConnectorConfig(self.root,self.root/'state')
        self.manifest,self.leader,self.document=write_robot_pack(self.root/'配置包')
    def tearDown(self):self.temp.cleanup()
    def test_import_resolves_only_leader_file_label_and_usb_binding(self):
        profile=calibration_profile(self.manifest)
        self.assertEqual(profile['calibration'],str(self.leader.resolve()))
        self.assertEqual(profile['calibrationName'],'测试门店')
        self.assertEqual(profile['expectedLeaderSerial'],'leader-usb')
        self.assertEqual(profile['calibrationHash'],calibration_profile(self.leader)['calibrationHash'])
        self.assertNotEqual(profile['profileKey'],profile['calibrationHash'])
    def test_named_offsets_are_already_in_hardware_not_added_to_positions(self):
        mapping=RangeCalibration(self.document);limits={name:(-1.,1.) for name in SO101_JOINTS}
        low=[m['range_min'] for m in mapping.motors]
        high=[m['range_max'] for m in mapping.motors]
        self.assertEqual(list(mapping.targets(low,limits).values()),[-1.]*6)
        self.assertEqual(list(mapping.targets(high,limits).values()),[1.]*6)
        self.assertEqual(list(mapping.targets([(a+b)/2 for a,b in zip(low,high)],limits).values()),[0.]*6)
        self.document['shoulder_pan']['drive_mode']=1
        self.assertEqual(RangeCalibration(self.document).targets(low,limits)['Rotation'],1.)
    def test_feetech_release_corrects_legacy_driver_without_changing_arm_identity(self):
        usb={**USB,'serial':'leader-usb'}
        old=self.store.save('https://10.72.255.16',self.manifest,usb)
        self.assertEqual(old['driver'],'desheng-se-v401')
        (self.root/'connector.json').write_text(json.dumps({'hardwareDriver':'feetech-so101','connectionMode':'pair-code'}))
        upgraded=ConnectorConfig(self.root,self.root/'state')
        for field in ('server','armId','calibrationHash','expectedLeaderSerial','profileKey','portIdentity','sourceCalibration'):
            self.assertEqual(upgraded.data[field],old[field],field)
        self.assertEqual(upgraded.data['driver'],'feetech-so101')
        self.assertFalse(upgraded.data['autoConnect'])
        saved=upgraded.save(old['server'],upgraded.data['calibration'],usb)
        self.assertEqual(saved['driver'],'feetech-so101')
        self.assertEqual(Path(saved['calibration']).read_bytes(),self.leader.read_bytes())
        selected=ConnectorConfig(self.root,self.root/'state').select_profile(old['profileKey'])
        self.assertEqual(selected['driver'],'feetech-so101')
        self.assertEqual(selected['armId'],old['armId'])
        # A generic later build must also preserve the explicitly saved choice.
        (self.root/'connector.json').unlink()
        generic=ConnectorConfig(self.root,self.root/'state')
        self.assertEqual(generic.save(old['server'],generic.data['calibration'])['driver'],'feetech-so101')
    def test_feetech_release_uses_explicit_driver_for_new_pack(self):
        (self.root/'connector.json').write_text(json.dumps({'hardwareDriver':'feetech-so101'}))
        store=ConnectorConfig(self.root,self.root/'state')
        self.assertEqual(store.save('https://server',self.manifest)['driver'],'feetech-so101')
    def test_invalid_named_joint_fields_are_rejected(self):
        for field,value in [('homing_offset',2048),('range_min',4095),('drive_mode',2),('id',2)]:
            document=json.loads(json.dumps(self.document));document['shoulder_pan'][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):RangeCalibration(document)
    def test_missing_leader_path_reports_specific_error_does_not_import_follower(self):
        self.leader.unlink()
        with self.assertRaisesRegex(ValueError,'找不到主臂校准文件'):calibration_profile(self.manifest)
    def test_invalid_reference_reports_field(self):
        document=json.loads(self.manifest.read_text(encoding='utf-8-sig'))
        del document['calibration']['leader_output']
        self.manifest.write_text(json.dumps(document),encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'leader_output'):calibration_profile(self.manifest)
    def test_partial_or_wrong_json_reports_useful_error(self):
        self.leader.write_text('{',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'JSON 文件格式不正确'):calibration_profile(self.manifest)
        self.leader.write_text('[]',encoding='utf-8')
        with self.assertRaisesRegex(ValueError,'JSON 对象'):calibration_profile(self.manifest)
    def test_pack_without_serial_can_still_import(self):
        document=json.loads(self.manifest.read_text(encoding='utf-8-sig'))
        document.pop('expected_devices');self.manifest.write_text(json.dumps(document))
        self.assertEqual(calibration_profile(self.manifest)['expectedLeaderSerial'],'')
    def test_expected_leader_wins_over_remembered_follower_after_com_change(self):
        leader={**USB,'serial':'leader-usb','port':'COM30'}
        follower={**USB,'serial':'follower-usb'}
        self.assertEqual(choose_port([follower,leader],follower,'leader-usb'),leader)
        self.assertIsNone(choose_port([follower],None,'leader-usb'))
        self.assertIsNone(choose_port([leader,{**leader,'port':'COM31'}],None,'leader-usb'))
    def test_imported_pack_survives_move_and_connect_retains_binding(self):
        saved=self.store.save('http://server:8080',self.manifest)
        self.assertEqual(Path(saved['calibration']).read_bytes(),self.leader.read_bytes())
        self.manifest.unlink();self.leader.unlink()
        restored=ConnectorConfig(self.root,self.root/'state')
        port={**USB,'serial':'leader-usb'}
        connected=restored.save('http://server:8080',restored.data['calibration'],port)
        self.assertEqual(connected['activeProfile'],saved['activeProfile'])
        self.assertEqual(connected['armId'],saved['armId'])
        self.assertEqual(connected['sourceCalibration'],str(self.manifest.resolve()))
        self.assertEqual(connected['calibrationName'],'测试门店')
        self.assertEqual(connected['expectedLeaderSerial'],'leader-usb')
        self.assertEqual(len(connected['profiles']),1)
    def test_wrong_manual_port_does_not_replace_binding(self):
        saved=self.store.save('http://server:8080',self.manifest);before=self.store.file.read_bytes()
        with self.assertRaisesRegex(ValueError,'不是此配置包的主臂'):
            self.store.save('http://server:8080',saved['calibration'],{**USB,'serial':'follower-usb'})
        self.assertEqual(before,self.store.file.read_bytes())
    def test_identical_calibration_with_different_leader_bindings_stays_separate(self):
        second,_,_=write_robot_pack(self.root/'另一台',serial='leader-two',label='另一台')
        first=self.store.save('http://server:8080',self.manifest)
        other=self.store.save('http://server:8080',second)
        self.assertEqual(first['calibrationHash'],other['calibrationHash'])
        self.assertNotEqual(first['activeProfile'],other['activeProfile'])
        self.assertNotEqual(first['armId'],other['armId'])
        self.assertEqual(len(self.store.profiles()),2)
        restored=ConnectorConfig(self.root,self.root/'state')
        for saved in (first,other):
            restored.select_profile(saved['activeProfile'])
            connected=restored.save('http://server:8080',restored.data['calibration'])
            self.assertEqual(connected['expectedLeaderSerial'],saved['expectedLeaderSerial'])
            self.assertEqual(connected['armId'],saved['armId'])
    def test_deleted_cache_can_be_recovered_from_original_manifest(self):
        saved=self.store.save('http://server:8080',self.manifest)
        Path(saved['calibration']).unlink()
        restored=ConnectorConfig(self.root,self.root/'state')
        self.assertEqual(Path(restored.data['calibration']).read_bytes(),self.leader.read_bytes())
        self.assertEqual(restored.data['calibrationName'],'测试门店')

if __name__=='__main__':unittest.main()
