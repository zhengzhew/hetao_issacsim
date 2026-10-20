## 2026-10-10：会话与设备配对入口

根目录的 `启动服务.bat` / `关闭服务.bat` 仍然是入口。现在启动 `server/platform-main.js`：外部管理/体验入口 8080，每个体验台的 Node 实例只监听本机并验证内部密钥。启动会将本项目旧服务切换到新入口，不会并行保留未认证的旧入口。

首次老师密码在 `run/platform/teacher-password.txt`；浏览器打开 `/manage` 登录。生成“浏览器配对码”给体验电脑。同一 WLAN 子网内新版机械臂连接器已免配对；其他网络仍可用“采集器配对码”。码 5 分钟有效、仅使用一次；连接凭证 12 小时有效，可在管理页解除。家长算术题只是儿童交互层，不代替服务端权限。

新版工具下载：/downloads/so101-leader-windows.zip。完整解压，停止旧工具，打开 SO101-Leader.exe，点击“添加配置”选择该臂的 .robot.json 配置包入口或主臂校准 JSON（配置包首次导入时保留 calibration 子目录），然后点击“连接机械臂”。多台臂各添加一次；换臂时先停止同步，在主界面列表切换对应配置。配置包有主臂 USB 绑定时自动选对应串口；普通文件在单个 USB 时自动选择。多串口、多个体验台或服务器地址变更时展开“连接设置”，选择一次会保存。当前 WLAN 子网内自动取得设备凭证，无需配对码。无需手填机械臂编号或驱动；当前支持德晟 SE 配置。设置、校准副本与独立凭证保存在采集电脑 %LOCALAPPDATA%/HetaoIsaacConnector，升级解压目录后仍能复用，不要把该目录打包转发。

GUI 按校准内容与配置包主臂 USB 绑定生成配置编号，代表配置而非实物身份。当前这台臂使用已确认的 configs/leader_arm_isaac_calibration.json，其他臂选择自己的文件。命令行显式指定相同 --arm-id 而更换校准时，仍保留管理页确认流程。浏览器登录、体验台分配与控制隔离保留。

`configs/platform.json` 是实例与端口配置源。默认只启动一个实例；增加第二个 station 时必须分配不同的 `id/webPort/bridgePort/signalPort/mediaPort`，并明确 GPU。每个实例有独立上传目录、场景和关卡状态，公共机器人资产首次复制到自己的目录。两个实际 GPU 仿真实例的容量尚未压测；目前双实例路由验收使用隔离假服务。原生视频一实例仅供一个体验浏览器，不包含多人转播。

控制链路：串口独立采样 → 最新值缓存 → WebSocket → 会话入口 → 本机实例 → 带有效期的 Kit 队列。网络等待不阻塞 USB 采集；位置包过期/被更新会丢弃。默认样本有效期 250 ms，服务端排队只保留最新目标，5 秒没有样本会释放主臂控制权。启动/重连带实例启动代号，避免复用旧场景样本。按实际经过时间限制目标变化速度。

管理页按体验台显示采集器、跟随频率、控制确认耗时和视频上报；旧视频报告标记过期。确认耗时不是完整手到画面延迟。完整延迟仍需实物动作与画面同步测量。GPU 多实例、武汉/北京网络以及 8 小时活动验收尚需现场条件。

本地默认 HTTP，仅适用于当前受信局域网。公网启用前需配置 HTTPS/WSS（反向代理、`publicOrigin`、`secureCookies:true`）以及视频端口的私网/VPN或受控网络访问；当前登录不能替代 NVIDIA 原生视频端口的访问隔离。不要直接暴露内部 Node 或 8765 桥接端口。本次代码更新没有扩展 Windows 防火墙范围。

验证命令：`npm test`；浏览器验收 `node scripts/check_platform_ui.mjs`（需 Playwright，使用 `PLAYWRIGHT_MODULE` 指定现有安装）。Python 采集依赖 `tools/requirements-leader.txt`；连接器构建 `python scripts/build_leader.py --server http://服务器IP:8080`，PyInstaller 当前验证版本为 6.22.2，构建物不含个人校准或配对凭证。项目不自动提交或推送。

服务日志位于 `run/platform`。Node/Kit 进程崩溃按退避自动重启，最多 5 次；重复失败保留日志等待排查。Kit 重启会重置关卡，不会声称自动恢复原有物体状态。单个实例日志达到 10 MiB 轮转并保留 3 个历史文件。

以下为旧版部署和历史测试记录，旧版 `start-native.ps1` 不作为带配对入口的默认启动方式。

# Windows 本机部署

Node.js 与 NVIDIA Isaac Sim 在同一台 Windows 电脑运行，默认采用原生 WebRTC 视频传输与 GPU 硬件编码，保留 MJPEG 兼容备用。无需 WSL 或端口代理。

## 一键启动与关闭

已完成本机安装后，在仓库最外层双击：

- **启动服务.bat**：启动网页与真实 Isaac Sim，自动打开浏览器；等待仿真与 WebRTC 信令就绪后显示本机和局域网地址。默认 1920×1080、目标 30 FPS、WebRTC + GPU 编码。
- **关闭服务.bat**：关闭本仓库的网页、仿真及其子进程，包括启动窗口退出后的残留仿真进程。重复关闭会提示已经关闭。
- 重复双击启动不会再开一套服务；只运行了一部分时会补启缺少的部分。启动与关闭同时进行时会提示等待，不会相互打断。
- 关闭浏览器或启动脚本窗口不会停止后台仿真。停止服务会结束当前关卡，重新启动将从初始场景开始。
- 脚本按本仓库绝对路径核对进程，并在终止前复核创建时间与命令行，不按进程名称批量结束其他 Node.js / Isaac Sim 程序。旧版相对路径 Node 进程还需通过 PID、端口和资产目录验证身份。
- 脚本不会自动修改防火墙或请求管理员权限。若当前网络没有可用的 WLAN IPv4，请按窗口提示指定网卡或 IP。
- 启动窗口最长等待 4 分钟；超时或出错不会显示成功，可到主项目的 logs 目录查看日志。就绪检查不代替浏览器视频播放检查。

需要目标 60 FPS，可在仓库最外层的 PowerShell 中运行（已运行时先关闭再启动，目标帧率不保证实际帧率）：

    & '.\启动服务.bat' -CaptureFps 60

也可在 isaac-web-playground-core 目录直接调用：

    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\windows\service-control.ps1 -Action Start
    powershell -NoProfile -ExecutionPolicy Bypass -File .\deploy\windows\service-control.ps1 -Action Stop

自动化测试可为 Start 添加 -NoBrowser；更换安装位置可添加 -IsaacDir，使用其他网卡或地址可添加 -StreamInterface 或 -StreamHost。

## 启动

将 Isaac Sim 6.0.1 安装到 `D:\IsaacSim\6.0.1`，或通过 `-IsaacDir` 指定安装目录。在 `isaac-web-playground-core` 目录中首次安装依赖并构建客户端：

```powershell
npm ci
npm run build:native
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-native.ps1
```

默认机械臂任务台、SO-101、单 GPU、1920×1080 和目标 60 FPS。目标不是实际帧率保证；本机前台 30 秒验证平均约 52.2 FPS，见 [WebRTC 验证记录](webrtc-verification-20260917.md)。原生模式关闭空闲降频，无观看者时仍可能占用 GPU；活动结束后应停止服务。

浏览器打开 `http://127.0.0.1:8080`，选择伙伴与关卡后进入体验，再建立原生连接。测试时只保留一个体验页面，避免争用原生主串流。页面显示当前传输方式，失败时回退 MJPEG 并显示原因。断开画面不会停止服务器或仿真。

脚本默认 `-Renderer native`，自动使用 WLAN 网卡的 IPv4 作为 WebRTC 串流地址；网络变化后重新启动即可更新。其他网卡用 `-StreamInterface <网卡名>`，也可以显式指定 `-StreamHost <服务器IP>`。仅本机测试时可指定 `-StreamHost 127.0.0.1`。自动检测失败会提示指定地址，不会静默退回本机。

局域网客户端打开 `http://<服务器IP>:8080`。除网页 TCP 8080 外，还需允许同子网访问 Isaac Sim Kit 的 TCP 49100 信令与 UDP 47998 媒体端口。管理员可运行 `deploy/windows/enable-webrtc-lan.ps1` 添加仅限 WLAN、LocalSubnet、指定 Kit 程序的两条规则；启动脚本本身不会修改防火墙。桥接 8765 保持仅本机监听。跨设备、异地网络、TURN 与多门店并发需分别验证，修改地址不等于通过异地验收。

需要降低负载，可在停止现有项目进程后，带 `-CaptureWidth 1280 -CaptureHeight 720 -CaptureFps 30` 启动。WebRTC 分辨率和帧率由启动参数决定，`/api/stream/settings` 仅调整 MJPEG 备用采集，不会修改原生视频。

完整切换到 MJPEG 服务时，停止现有项目进程，再运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-native.ps1 -Renderer mjpeg -CaptureFps 30
```

MJPEG 使用独立采集与后台 JPEG 编码，`-CaptureQuality` 仅影响该备用路径。使用 `-Component Web` 或 `-Component Bridge` 可单独启动组件，两者需传入一致的串流参数。脚本拒绝占用中的端口，不会强行终止其他进程。

## 状态与日志

- 日志位于项目 `logs/`，每次启动使用新的时间戳。
- 启动进程 PID 记录在 `run/`；PID 可能复用，停止前应核对实际进程命令行。
- `/api/status` 用于检查网页与桥接状态，`/api/session` 查看已加载场景和机器人。
- `/api/stream/client-report` 保留最近一份浏览器视频报告，供检查尺寸、累计帧与丢帧使用；多页面会覆盖，不能作为每个门店独立监控。
- 网页可访问不代表仿真完成启动，需继续验证实时画面与运动控制。
- 网页监听所有网卡，桥接仅监听本机；脚本不会修改防火墙、设置公网转发或开机自动登录。
- 局域网访问还需验证 Windows 防火墙及客户端到主机的连通性。

原项目没有登录验证，适用于受信任网络。AI 聊天服务需要另行配置模型服务凭据；SO-101 / MicroDuck 七关卡见 [关卡使用说明](../../docs/guides/challenges.md)。新环境先执行 `setup-challenges.ps1` 下载资产与安装项目本地策略运行时。

## 真实仿真验收

在项目目录运行 `node scripts/accept_stage2.mjs`。脚本要求桥接在线且明确返回 `mock=false`，再依次切换四组场景与机器人，检查 Jetbot 前进、Kaya 横移的实际位姿变化；MJPEG 模式还检查各场景的图像响应。该命令会改变当前仿真会话并移动虚拟机器人，请在无人操作网页时运行。

脚本通过后仍需在浏览器确认连续画面、按住移动与松开停止，并从另一台局域网设备访问。安装未完成时，桥接离线导致验收失败属于预期，不能记为服务通过。

2026-09-16 本机记录：Isaac Sim 6.0.1，RTX 5060 Laptop 8GB，驱动 582.05，Python 3.12.13。官方安装包 MD5 校验通过，安装后脚本通过。四组验收为 warehouse/Jetbot、simple-room/Carter v1、warehouse-multi/Nova Carter、grid/Kaya；Jetbot 前进约 0.342 米，Kaya 横移约 0.230 米。独立停止测试在停止后两次测量之间位姿无变化。首次加载包含远程资源下载和渲染初始化，耗时明显长于再次加载。

网页地址为 `http://localhost:8080`，本次 WLAN 地址为 `http://10.205.22.80:8080`（网络变化后需重新查看 IPv4）。已按用户授权设置防火墙规则 `Hetao-IsaacSim-Web-LAN-8080`，限定 Node.js、WLAN、同一子网与 TCP 8080。未开放桥接 8765；另一台设备访问仍待确认。

Windows 自带 tar 在此次解压中漏掉一个特殊字符文件名的 USD 测试文件并返回退出码 1；已用 Python zipfile 补取。若重新安装遇到同一情况，应核对 ZIP 清单与实际文件，再修复缺项，不要直接忽略解压错误。
