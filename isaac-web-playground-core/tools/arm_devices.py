"""Device identity and driver inventory. USB adapters are not arm identities."""
import hashlib
import json
import uuid
from pathlib import Path
from desheng_calibration import RangeCalibration

DRIVERS = {
    'desheng-se-v401': {'name':'德晟 SE（已验证兼容读取协议）', 'verified':True, 'max_rate':30},
    'feetech-so101': {'name':'Feetech SO-101（待本项目硬件验证）', 'verified':False},
    'desheng-v5': {'name':'德晟其他版本／V5（待协议验证）', 'verified':False},
    'unknown': {'name':'其他／未知版本（请先确认协议）', 'verified':False},
}

def client_identity(directory):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    file=directory/'client-id.txt'
    if not file.exists():file.write_text(str(uuid.uuid4()),encoding='utf-8')
    value=file.read_text(encoding='utf-8').strip()
    uuid.UUID(value)
    return value

def load_profile(arm_id, driver, calibration_path):
    if not isinstance(arm_id,str) or not arm_id.strip() or len(arm_id)>80:
        raise ValueError('请输入机械臂贴纸编号，用于绑定校准；COM 口不是设备编号')
    if driver not in DRIVERS or not DRIVERS[driver]['verified']:
        raise ValueError('该舵机版本尚未验证。不会猜测协议或套用 SE 校准。')
    calibration=RangeCalibration.load(calibration_path)
    fingerprint=hashlib.sha256(Path(calibration_path).read_bytes()).hexdigest()
    return {'armId':arm_id.strip(),'driver':driver,'calibrationHash':fingerprint,'calibration':str(Path(calibration_path).resolve())}, calibration
