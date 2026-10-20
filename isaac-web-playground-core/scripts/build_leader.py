"""Build a generic paired connector with no calibration or credentials bundled."""
import argparse,hashlib,json,subprocess,sys,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--server',default='http://localhost:8080')
args=parser.parse_args()
sys.path.insert(0,str(ROOT/'tools'))
from connector_config import normalize_server
server=normalize_server(args.server)
work=(ROOT/'run'/('connector-build-'+str(time.time_ns()))).resolve()
assert ROOT in work.parents
work.mkdir(parents=True)
subprocess.run([sys.executable,'-m','PyInstaller','--noconfirm','--windowed','--onedir','--name','SO101-Leader','--distpath',str(work/'dist'),'--workpath',str(work/'build'),'--specpath',str(work),'--paths',str(ROOT/'tools'),str(ROOT/'tools/desheng_connector.py')],check=True,cwd=ROOT)
package=work/'dist/SO101-Leader'
(package/'connector.json').write_text(json.dumps({'server':server,'calibration':'','autoConnect':True},indent=2),encoding='utf-8')
(package/'使用说明.txt').write_text('1. 停止旧版工具，解压整个文件夹，在插着 USB 主臂的电脑运行 SO101-Leader.exe。\n2. 点击“添加配置”，选择当前机械臂的 .robot.json 配置包入口，或直接选择主臂校准 JSON。首次导入配置包时保留旁边的 calibration 子文件夹。每台机械臂添加一次，主界面的配置列表可以直接切换，不用手填机械臂编号。\n3. 配置包记录主臂 USB 序列号时会自动找对应串口；普通校准文件在只接一个 USB 时自动选择，多个设备时展开“连接设置”选一次。不同配置分别记住各自的串口。\n4. 点击“连接机械臂”。换臂时先停止同步，在列表选择对应配置，再连接。下次打开会恢复上次选择；设置和各份校准副本保存在 LocalAppData/HetaoIsaacConnector，换程序文件夹仍保留。\n5. 当前默认服务器：'+server+'。服务器换 IP 时，在“连接设置”中改地址，之后会记住。\n6. 当前服务器允许同一 WLAN 子网连接器免配对；多个体验台时选一次。老师和体验浏览器仍按原规则登录。旧版服务器才需要在设置中填写采集器配对码。\n7. 使用结束点击“停止同步”。此工具只读取实物主臂，不发送舵机位置控制。\n',encoding='utf-8-sig')
out=ROOT/'web/downloads';out.mkdir(parents=True,exist_ok=True)
archive=out/'so101-leader-windows.zip'
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
 for file in package.rglob('*'):
  if file.is_file():bundle.write(file,file.relative_to(package.parent))
print(json.dumps({'package':str(package),'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest()}))
