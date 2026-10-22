# hetao_issacsim

基于 NVIDIA Isaac Sim 的浏览器机器人仿真控制项目，包含 SO-101 机械臂与 MicroDuck 小鸭子关卡。

## 本机一键启动 / 关闭

已安装好的这台 Windows 电脑，双击仓库根目录的 [启动服务.bat](启动服务.bat) 即可启动真实仿真并打开网页；结束使用时双击 [关闭服务.bat](关闭服务.bat)。一键启动默认使用 WebRTC + GPU 编码、1080p、目标 30 FPS。脚本支持重复点击并核验本项目进程，详细参数见 [原生部署说明](isaac-web-playground-core/deploy/windows/README-native.md)。

## 体验台配对与运行

现在使用老师登录与体验台配对入口。首次老师密码在 `isaac-web-playground-core/run/platform/teacher-password.txt`。接机械臂的电脑需要更新连接器，选择该机械臂自己的 `.robot.json` 配置包或主臂校准 JSON；配置和串口选择会被记住。完整操作见 [体验台运行说明](isaac-web-playground-core/docs/guides/platform-operations.md)。

## 目录

| 目录 | 内容 |
| --- | --- |
| [isaac-web-playground-core](isaac-web-playground-core/README.md) | 浏览器界面、Node.js 服务、Isaac Sim Python 桥接程序、配置与部署脚本 |
| [microduck-bundle](microduck-bundle/README.md) | MicroDuck 策略引擎、控制模块及上游参考代码；主项目已提供小鸭子关卡入口 |

## 工作方式

浏览器发送操作请求，Node.js 服务将请求转交给运行在 Isaac Sim 中的 Python 桥接程序；Isaac Sim 计算机器人运动并将画面通过串流返回浏览器。

真实仿真需要在服务端安装 Isaac Sim，并准备适合运行它的 NVIDIA GPU。原项目说明指定 Isaac Sim 6.0.1 和 Node.js 20 或更新版本。访问网页的客户端无需安装 Isaac Sim。

## 腾讯云 TencentOS 4 部署

在服务器从 GitHub 拉取源码后，执行 `isaac-web-playground-core/deploy/cloud/install_host.py`。适配现有 L20、TencentOS Server 4、50 GB 系统盘与 70 GB 数据盘：大镜像存 `/data/docker`，程序与运行数据存系统盘，不要求扩容或更换操作系统。依赖通过 RPM/DNF 安装，公网 IP 显式配置，使用 HTTPS/WSS + WebRTC。

完整的 clone、首次安装、更新和排查命令见 [云端部署说明](isaac-web-playground-core/deploy/cloud/README.md)。已移除 Windows SSH 上传和阿里云专用安装入口；Windows 本机仿真启动方式保持原状。当前为单 GPU、单体验台，新 TencentOS 路径仍需在公司服务器上完成真实 GPU 和浏览器验收。GitHub 不保存密码、运行数据或个人校准配置。

## 简化演示

安装 Node.js 后，在主项目目录运行：

```sh
cd isaac-web-playground-core
npm run demo
```

按终端输出的网址访问。此模式使用简化模拟逻辑，帮助理解网页操作流程，不是真实 Isaac Sim 仿真。

## 真实仿真部署

参阅 [主项目说明](isaac-web-playground-core/README.md) 和 [部署指南](isaac-web-playground-core/deploy/README.md)。需要配置桥接服务地址、串流方式及资源路径；请显式设置 `ISAAC_STREAM_RENDERER`，配置示例使用 `mjpeg`，服务代码未配置时使用 `native`。

Windows 本机部署请使用 [原生部署说明](isaac-web-playground-core/deploy/windows/README-native.md)。儿童界面采用薄荷绿与白色卡片，提供中文语音、图形方向键和家长工作台，保留 NVIDIA 与 Isaac Sim 描述。

本仓库不包含 Isaac Sim 安装程序、USD 场景/机器人资产或 ONNX 策略权重，需另行准备。

## 当前状态与边界

- 默认启动一个真实 Isaac Sim 实例；可通过 `configs/platform.json` 配置独立体验台进程、端口、GPU 和资产目录。双台路由通过隔离服务测试，双 GPU 实例并发容量尚未实测。
- 入口区分老师、体验浏览器、采集器；内部 Node 只监听回环地址并验证密钥。原生 WebRTC 视频端口还需要网络隔离，公网部署需 HTTPS/WSS 与私网/VPN 或相应访问控制。
- 主臂连接器通过本地 USB 读取，再经 WebSocket 发送最新关节数据。当前只启用已验证兼容读取的德晟 SE 驱动，其他舵机版本等待协议与硬件验证。
- 已提供机械臂 3 关、小鸭子 4 关；骰子由玩家手动操控机械臂抛掷，自动抛出功能已移除。
- 2026-10-10：72 项自动化测试、配对管理浏览器检查、真实 Kit 控制链路与切关重连、真实 1080p 浏览器画面检查通过。新连接器在另一台 Windows 上的实体主臂联调、异地网络与 8 小时持续运行尚待验收。
- 既往性能记录见 [WebRTC 验证记录](isaac-web-playground-core/deploy/windows/webrtc-verification-20260917.md)，不能作为其他 GPU、门店或网络的性能保证。

## 代码与资产来源

保留交付材料中的原始来源和许可说明。本仓库不新增对第三方代码或 NVIDIA 资产的授权；复用与分发时应核对对应材料的许可。
