"""Remember connector choices and keep a local copy of the selected calibration."""
import hashlib
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from desheng_calibration import RangeCalibration


def state_directory():
    return Path(os.environ.get('ISAAC_CONNECTOR_STATE_DIR') or (Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'HetaoIsaacConnector'))


def normalize_server(value):
    value=str(value or '').strip().rstrip('/')
    if not value:raise ValueError('请填写服务器地址')
    if '://' not in value:value='http://'+value
    parsed=urlparse(value)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.path or parsed.query or parsed.fragment:
        raise ValueError('服务器地址示例：http://192.168.8.57:8080')
    try:port=parsed.port
    except ValueError:raise ValueError('服务器端口不正确') from None
    if port is None and parsed.scheme=='http':value+=':8080'
    return value


def atomic_json(file,document):
    file.parent.mkdir(parents=True,exist_ok=True)
    temporary=file.with_suffix('.tmp')
    temporary.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(temporary,file)


def read_config_json(file):
    try:
        if file.stat().st_size > 1024 * 1024:
            raise ValueError('配置文件过大：'+str(file))
        document = json.loads(file.read_text(encoding='utf-8-sig'))
    except FileNotFoundError:
        raise ValueError('找不到配置文件：'+str(file)) from None
    except (UnicodeError, json.JSONDecodeError):
        raise ValueError('JSON 文件格式不正确：'+str(file)) from None
    if not isinstance(document, dict):
        raise ValueError('配置文件内容必须是 JSON 对象：'+str(file))
    return document


def profile_key(sha, serial=''):
    # Calibration content and an explicit leader USB binding form separate saved choices.
    # Two packs can contain identical ranges while referring to different USB adapters.
    return sha + ('-'+hashlib.sha256(serial.encode('utf-8')).hexdigest()[:16] if serial else '')


def calibration_profile(file):
    source = Path(file).resolve()
    document = read_config_json(source)
    calibration = source
    name, serial = source.name, ''
    if source.name.lower().endswith('.robot.json') or 'profile_version' in document:
        if document.get('profile_version') != 1:
            raise ValueError('不支持这个配置包版本，请选择 profile_version 为 1 的 .robot.json')
        settings = document.get('calibration')
        reference = settings.get('leader_output') if isinstance(settings, dict) else None
        if not isinstance(reference, str) or not reference.strip():
            raise ValueError('配置包缺少主臂校准路径 calibration.leader_output')
        calibration = (source.parent/reference).resolve()
        if not calibration.is_relative_to(source.parent):
            raise ValueError('主臂校准文件必须位于此配置包内，请保留完整配置包目录')
        if not calibration.is_file():
            raise ValueError('找不到主臂校准文件：'+str(calibration)+'；请复制完整配置包文件夹')
        devices = document.get('expected_devices', [])
        if not isinstance(devices, list):
            raise ValueError('配置包的 expected_devices 必须是设备列表')
        leaders = [d for d in devices if isinstance(d, dict) and d.get('runtime_role') == 'leader']
        if len(leaders) > 1:
            raise ValueError('配置包包含多个主臂绑定，请保留对应主臂的一个设备记录')
        if leaders:
            fingerprint = leaders[0].get('fingerprint', '')
            if not isinstance(fingerprint, str) or not fingerprint.startswith('serial:') or not fingerprint[7:].strip():
                raise ValueError('配置包主臂 USB 绑定应使用 serial:序列号')
            serial = fingerprint[7:].strip()
        label = document.get('label')
        if isinstance(label, str) and label.strip():
            name = label.strip()
        # Only read the leader calibration. Never execute program, arguments or tool.
        document = read_config_json(calibration)
    try:
        RangeCalibration(document)
    except (ValueError, AttributeError, TypeError) as error:
        raise ValueError('主臂校准内容有误（'+calibration.name+'）：'+str(error)) from error
    sha = hashlib.sha256(calibration.read_bytes()).hexdigest()
    key = profile_key(sha, serial)
    identity = hashlib.sha256(key.encode('utf-8')).hexdigest() if serial else sha
    # The user has confirmed SE leader servos; JSON shape and USB are not protocol probes.
    return {'driver':'desheng-se-v401','armId':'cfg-'+identity[:24],
            'calibrationHash':sha,'calibration':str(calibration),
            'sourceCalibration':str(source),'calibrationName':name,
            'expectedLeaderSerial':serial,'profileKey':key}


def choose_port(available, previous=None, expected_serial=''):
    previous = previous or {}
    if expected_serial:
        matches = [p for p in available if p.get('serial') == expected_serial]
        return matches[0] if len(matches) == 1 else None
    if previous.get('serial'):
        matches=[p for p in available if p.get('serial')==previous['serial'] and p.get('vid')==previous.get('vid') and p.get('pid')==previous.get('pid')]
        return matches[0] if len(matches)==1 else None
    if previous.get('port'):
        matches=[p for p in available if all(p.get(k)==previous.get(k) for k in ('port','vid','pid','description'))]
        if len(matches)==1:return matches[0]
    usb=[p for p in available if p.get('vid') is not None and p.get('pid') is not None]
    return usb[0] if len(usb)==1 and not previous else None


class ConnectorConfig:
    PROFILE_FIELDS=('calibration','sourceCalibration','calibrationName','calibrationHash','armId','driver','portIdentity','expectedLeaderSerial','profileKey')

    def __init__(self,root,directory=None,downloads=None):
        self.root=Path(root);self.directory=Path(directory) if directory is not None else state_directory()
        self.file=self.directory/'simple-connector.json'
        self.data={};self.notice=''
        packaged=self.root/'connector.json'
        if packaged.exists():
            try:self.data=json.loads(packaged.read_text(encoding='utf-8-sig'))
            except (ValueError,OSError):self.notice='默认配置无法读取，请选择校准文件'
        if self.file.exists():
            try:self.data.update(json.loads(self.file.read_text(encoding='utf-8')))
            except (ValueError,OSError):raise ValueError('上次连接记录无法读取：'+str(self.file)) from None
        self.data.setdefault('server','http://localhost:8080')
        self.data.setdefault('autoConnect',True)
        self.data.setdefault('profiles',{})
        if not isinstance(self.data['profiles'],dict):raise ValueError('保存的机械臂配置列表无法读取')
        selected=self.data.get('activeProfile') or self.data.get('calibrationHash')
        if selected in self.data['profiles']:
            try:
                restored=self._restore(self.data['profiles'][selected]);self.data['profiles'][selected]=restored;self._activate(self.data,restored)
            except (ValueError,OSError,TypeError) as error:
                self.data['calibration']='';self.notice=str(error)
        elif self.data['profiles']:
            # Never substitute another arm's file when a saved selection is unavailable.
            self.data['calibration']='';self.notice='请选择当前机械臂的配置'
        else:
            # Migrate only a previously chosen file, never guess from the Downloads folder.
            restored=False
            for key in ('calibration','sourceCalibration'):
                candidate=self.data.get(key)
                if not candidate:continue
                try:
                    profile=calibration_profile(candidate)
                    if selected and profile['calibrationHash']!=selected:continue
                    record={**profile,'sourceCalibration':self.data.get('sourceCalibration') or candidate,
                            'calibrationName':self.data.get('calibrationName') or Path(self.data.get('sourceCalibration') or candidate).name,
                            'portIdentity':self.data.get('portIdentity',{})}
                    record=self._restore(record);self.data['profiles'][record['profileKey']]=record
                    self._activate(self.data,record);restored=True
                    break
                except (ValueError,OSError,TypeError):continue
            if not restored:self.data['calibration']=''

    @staticmethod
    def _activate(data,record):
        data.update({key:record[key] for key in ConnectorConfig.PROFILE_FIELDS})
        data['activeProfile']=record['profileKey']

    def _cache(self,file,sha):
        cache=self.directory/'calibrations'/(sha+'.json')
        content=Path(file).read_bytes()
        if hashlib.sha256(content).hexdigest()!=sha:raise ValueError('配置文件读取时发生变化，请重新添加')
        cache.parent.mkdir(parents=True,exist_ok=True)
        if not cache.exists() or cache.read_bytes()!=content:
            temporary=cache.with_suffix('.tmp');temporary.write_bytes(content);os.replace(temporary,cache)
        return str(cache.resolve())

    def _restore(self,record):
        for key in ('calibration','sourceCalibration'):
            file=record.get(key)
            if not file:continue
            try:
                profile=calibration_profile(file)
                if profile['calibrationHash']!=record['calibrationHash']:continue
                return {**profile,**record,'calibration':self._cache(profile['calibration'],profile['calibrationHash']),
                        'sourceCalibration':record.get('sourceCalibration',file),
                        'calibrationName':record.get('calibrationName') or Path(record.get('sourceCalibration') or file).name,
                        'portIdentity':record.get('portIdentity',{})}
            except (ValueError,OSError,TypeError):continue
        raise ValueError('这份配置已找不到，请重新添加对应机械臂的文件')

    def profiles(self):
        return list(self.data['profiles'].values())

    def save(self,server,calibration,port=None):
        server=normalize_server(server);profile=calibration_profile(calibration)
        sha=profile['calibrationHash'];key=profile['profileKey']
        # Connecting uses the active cached file. Retain its pack label and USB binding;
        # another profile can intentionally share the same calibration bytes.
        active=self.data['profiles'].get(self.data.get('activeProfile'),{})
        using_cache=bool(active and Path(calibration).resolve()==Path(active['calibration']).resolve())
        previous=active if using_cache else self.data['profiles'].get(key,{})
        if using_cache:
            for field in ('sourceCalibration','calibrationName','expectedLeaderSerial','profileKey','armId'):
                profile[field]=previous.get(field,profile[field])
            key=profile['profileKey']
        expected=profile['expectedLeaderSerial']
        if port is not None and expected and port.get('serial')!=expected:
            raise ValueError('所选 USB 不是此配置包的主臂，请连接对应主臂后重新检测')
        record={**profile,'calibration':self._cache(profile['calibration'],sha),
                'portIdentity':dict(previous.get('portIdentity',{})) if port is None else dict(port)}
        data={**self.data,'server':server,'profiles':{**self.data['profiles'],key:record}}
        self._activate(data,record)
        data.pop('token',None);data.pop('pairCode',None)
        atomic_json(self.file,data);self.data=data
        return dict(data)

    def select_profile(self,sha):
        if sha not in self.data['profiles']:raise ValueError('请选择已添加的机械臂配置')
        record=self._restore(self.data['profiles'][sha])
        data={**self.data,'profiles':{**self.data['profiles'],sha:record}}
        self._activate(data,record)
        atomic_json(self.file,data);self.data=data
        return dict(data)

    def remember_station(self,station_id,stations):
        self.data.update({'stationId':station_id,'stations':stations})
        atomic_json(self.file,self.data)


def friendly_error(error):
    text=str(error)
    if '401' in text:return '连接凭证已过期，请重新连接或更新连接配置'
    if '409' in text:return '体验台正在被另一台连接工具使用，请先停止原工具'
    if '403' in text:return '服务器未允许这台电脑直接连接，请检查服务器地址'
    if 'PermissionError' in text or 'Access is denied' in text or '拒绝访问' in text:return '串口被占用，请关闭其他机械臂工具后再连接'
    if '10061' in text or 'Connection refused' in text or '拒绝连接' in text:return '未连接到服务器，请确认服务已启动；地址变化时点“连接设置”修改'
    if 'timed out' in text or '10060' in text:return '服务器没有响应，请检查网络和服务器地址'
    return text
