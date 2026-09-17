# Windows 本机部署

Node.js 与 Isaac Sim 在同一台 Windows 电脑运行，使用 MJPEG 回传画面。无需 WSL 或端口代理。

## 启动

将 Isaac Sim 6.0.1 解压到 `D:\IsaacSim\6.0.1`，确认其中存在 `python.bat`。在已登录的 Windows 桌面会话中运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\windows\start-native.ps1
```

可用 `-IsaacDir` 指定其他安装目录。默认采用 grid 场景和 Jetbot、单 GPU，1920×1080 请求分辨率（实际按 16 像素对齐为 1920×1072）、30 FPS 采集上限和 JPEG 质量 90。30 FPS 是目标上限，不是实测帧率保证；本机测试见 [画质与性能记录](performance-20260917.md)。隐藏的 Kit 视口保持 640×352，网页图像由独立 Replicator 渲染产品以目标分辨率生成。

需要降低负载时，启动参数可改为 `-CaptureWidth 1280 -CaptureHeight 720 -CaptureFps 30 -CaptureQuality 85`。只改变现有串流、不重启仿真时可运行：

```powershell
Invoke-RestMethod -Method Post http://localhost:8080/api/stream/settings -ContentType application/json -Body '{"width":1280,"height":720,"fps":30,"quality":85}'
```

恢复高清档时将请求改为 `{"width":1920,"height":1080,"fps":30,"quality":90}`。运行时设置会在网页服务重启后恢复启动参数；`start-native.ps1` 中的参数控制下次启动。

浏览器打开 `http://localhost:8080`。只启动其中一部分可传入 `-Component Web` 或 `-Component Bridge`。真实仿真尚未就绪时，单独启动网页不会生成模拟画面。

## 状态与日志

- 日志位于项目 `logs/`，每次启动使用新的时间戳。
- 启动进程 PID 记录在 `run/`；PID 可能复用，停止前应核对实际进程命令行。
- `/api/status` 用于检查网页与桥接状态，`/api/session` 查看已加载场景和机器人。
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
