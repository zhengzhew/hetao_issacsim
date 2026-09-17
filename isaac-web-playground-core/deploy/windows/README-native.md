# Windows 本机部署

Node.js 与 NVIDIA Isaac Sim 在同一台 Windows 电脑运行，默认采用原生 WebRTC 视频传输与 GPU 硬件编码，保留 MJPEG 兼容备用。无需 WSL 或端口代理。

## 启动

将 Isaac Sim 6.0.1 安装到 `D:\IsaacSim\6.0.1`，或通过 `-IsaacDir` 指定安装目录。在 `isaac-web-playground-core` 目录中首次安装依赖并构建客户端：

```powershell
npm ci
npm run build:native
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-native.ps1
```

默认 grid 场景、Jetbot、单 GPU、1920×1080 和目标 60 FPS。目标不是实际帧率保证；本机前台 30 秒验证平均约 52.2 FPS，见 [WebRTC 验证记录](webrtc-verification-20260917.md)。原生模式关闭空闲降频，无观看者时仍可能占用 GPU；活动结束后应停止服务。

浏览器打开 `http://127.0.0.1:8080`，选择场景与伙伴后进入体验，再建立原生连接。测试时只保留一个体验页面，避免争用原生主串流。页面显示当前传输方式，失败时回退 MJPEG 并显示原因。断开画面不会停止服务器或仿真。

脚本默认 `-Renderer native -StreamHost 127.0.0.1`，只验证了本机原生连接。局域网部署需设置客户端可达的 `-StreamHost <服务器局域网IP>`，并验证 TCP 49100 信令与 UDP 47998 媒体端口；既有 TCP 8080 网页规则不能替代媒体规则。脚本不会自动添加防火墙规则，异地网络、TURN 与多门店并发尚未验收。

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

原项目没有登录验证，适用于受信任网络。AI 聊天服务需要另行配置模型服务凭据；MicroDuck 仍需单独集成。

## 真实仿真验收

在项目目录运行 `node scripts/accept_stage2.mjs`。脚本要求桥接在线且明确返回 `mock=false`，再依次切换四组场景与机器人，检查 Jetbot 前进、Kaya 横移的实际位姿变化；MJPEG 模式还检查各场景的图像响应。该命令会改变当前仿真会话并移动虚拟机器人，请在无人操作网页时运行。

脚本通过后仍需在浏览器确认连续画面、按住移动与松开停止，并从另一台局域网设备访问。安装未完成时，桥接离线导致验收失败属于预期，不能记为服务通过。

2026-09-16 本机记录：Isaac Sim 6.0.1，RTX 5060 Laptop 8GB，驱动 582.05，Python 3.12.13。官方安装包 MD5 校验通过，安装后脚本通过。四组验收为 warehouse/Jetbot、simple-room/Carter v1、warehouse-multi/Nova Carter、grid/Kaya；Jetbot 前进约 0.342 米，Kaya 横移约 0.230 米。独立停止测试在停止后两次测量之间位姿无变化。首次加载包含远程资源下载和渲染初始化，耗时明显长于再次加载。

网页地址为 `http://localhost:8080`，本次 WLAN 地址为 `http://10.205.22.80:8080`（网络变化后需重新查看 IPv4）。已按用户授权设置防火墙规则 `Hetao-IsaacSim-Web-LAN-8080`，限定 Node.js、WLAN、同一子网与 TCP 8080。未开放桥接 8765；另一台设备访问仍待确认。

Windows 自带 tar 在此次解压中漏掉一个特殊字符文件名的 USD 测试文件并返回退出码 1；已用 Python zipfile 补取。若重新安装遇到同一情况，应核对 ZIP 清单与实际文件，再修复缺项，不要直接忽略解压错误。
