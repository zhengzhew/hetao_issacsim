"""Build the Windows connector with an explicit servo driver and access mode."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import zipfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from connector_config import normalize_server


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--server',default='',help='Optional HTTP(S) origin; blank prompts on first use')
    parser.add_argument('--driver',choices=['desheng-se-v401','feetech-so101'],default='desheng-se-v401')
    parser.add_argument('--connection-mode',choices=['lan','pair-code'],default='lan',
                        help='lan requires server-authorized local enrollment; pair-code uses teacher-issued codes')
    args=parser.parse_args()
    if sys.platform!='win32':parser.error('Build the Windows EXE on Windows')
    server=normalize_server(args.server) if args.server.strip() else ''
    work=(ROOT/'run'/('connector-build-'+str(time.time_ns()))).resolve()
    assert ROOT in work.parents
    work.mkdir(parents=True)
    subprocess.run([
        sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','SO101-Leader',
        '--distpath',str(work/'dist'),'--workpath',str(work/'build'),'--specpath',str(work),
        '--add-data',str(ROOT/'tools/certificates/10.72.255.16-root.crt')+';certificates',
        '--paths',str(ROOT/'tools'),str(ROOT/'tools/desheng_connector.py'),
    ],check=True,cwd=ROOT)
    package=work/'dist/SO101-Leader'
    config={'server':server,'calibration':'','autoConnect':args.connection_mode=='lan',
            'connectionMode':args.connection_mode,'hardwareDriver':args.driver}
    (package/'connector.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
    access=('本包使用服务器授权的局域网免配对；是否允许接入由服务器决定。'
            if args.connection_mode=='lan' else '本包使用采集器配对码；首次连接或凭证过期时，在教师端生成并填写采集器配对码。')
    (package/'使用说明.txt').write_text(f'''SO-101 Windows 连接工具 V5

1. 关闭旧版工具，完整解压，在插着 USB 主臂的电脑运行 SO101-Leader.exe。
2. 主界面可输入并保存服务器地址，支持 HTTP、HTTPS 和端口。默认地址：{server or '首次使用时填写'}。
3. 添加这台主臂的 .robot.json 配置包或主臂校准 JSON，导入时保留配置包的 calibration 子目录。
4. 驱动：{args.driver}。飞特 STS3215 使用 1000000 波特率，德晟 SE 使用 115200 波特率。
5. {access}
6. 点击“连接机械臂”。每台臂独立保存校准和 USB 绑定；换臂先停止，再选择对应配置。
7. 结束时点击“停止同步”。工具只读取主臂型号/位置，不写入舵机控制或校准参数。

解压新版会保留服务器、机械臂编号和校准，采用本包明确配置的驱动与连接模式。
驱动或校准变更若触发服务器待确认，请在教师管理页核对后确认，再连接。
已包含 Python 环境，不必另装 Python。包内不包含设备凭证、老师密码或个人校准文件。
内置根证书仅用于 https://10.72.255.16:443 及对应 WSS；仍验证证书与主机名。
其他服务器使用系统默认信任链。普通 JSON 和 USB 芯片不会被当作舵机型号识别依据。
''',encoding='utf-8-sig')
    smoke=work/'ui-smoke.json'
    subprocess.run([str(package/'SO101-Leader.exe'),'--ui-smoke',str(smoke)],check=True,timeout=45,
                   env=dict(os.environ,ISAAC_CONNECTOR_STATE_DIR=str(work/'smoke-state')),
                   cwd=package,creationflags=subprocess.CREATE_NO_WINDOW)
    state=json.loads(smoke.read_text(encoding='utf-8'))
    assert state['server']==server and state['driver']==args.driver
    assert state['autoConnect']==config['autoConnect'] and state['bundledCaLoaded'] is True
    assert not state['calibration'] and not state['profiles']
    out=ROOT/'web/downloads';out.mkdir(parents=True,exist_ok=True)
    archive=out/'so101-leader-windows.zip'
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
        for file in sorted(package.rglob('*')):
            if file.is_file():bundle.write(file,file.relative_to(package.parent))
    with zipfile.ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        assert json.loads(bundle.read('SO101-Leader/connector.json'))==config
    digest=hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.sha256').write_text(digest+'  '+archive.name+'\n',encoding='ascii')
    print(json.dumps({'package':str(package),'archive':str(archive),'sha256':digest,'config':config}))


if __name__=='__main__':main()
