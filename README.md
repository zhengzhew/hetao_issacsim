# hetao_issacsim

基于 NVIDIA Isaac Sim 的浏览器机器人仿真控制项目，以及待集成的 MicroDuck 双足机器人扩展材料。

## 目录

| 目录 | 内容 |
| --- | --- |
| [isaac-web-playground-core](isaac-web-playground-core/README.md) | 浏览器界面、Node.js 服务、Isaac Sim Python 桥接程序、配置与部署脚本 |
| [microduck-bundle](microduck-bundle/README.md) | MicroDuck 策略引擎、控制模块及上游参考代码，尚未接入主项目 |

## 工作方式

浏览器发送操作请求，Node.js 服务将请求转交给运行在 Isaac Sim 中的 Python 桥接程序；Isaac Sim 计算机器人运动并将画面通过串流返回浏览器。

真实仿真需要在服务端安装 Isaac Sim，并准备适合运行它的 NVIDIA GPU。原项目说明指定 Isaac Sim 6.0.1 和 Node.js 20 或更新版本。访问网页的客户端无需安装 Isaac Sim。

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

- 所有访问者共享同一个仿真场景、机器人和相机，尚无独立学生会话。
- 原项目没有身份认证，部署范围应与其可信访问假设一致。
- MicroDuck 尚未集成，原说明记录了策略运行时画面采集异常的问题。
- 当前副本缺少部分原文档引用的材料，包括主项目 `tests/` 目录和 MicroDuck 的 `2026-09-07-clock-and-control-fix-report.md`。
- 2026-09-16：Windows 本机 Isaac Sim 6.0.1 + MJPEG 已通过四组场景/机器人加载和图像响应检查；Jetbot 前进、Kaya 横移均测得真实位姿变化。浏览器已确认 Grid/Jetbot 画面、启动与停止交互。另一台设备的局域网访问尚待确认。
- 模型服务与实体机械臂未验证；MicroDuck 未集成。原文档的性能数字是原参考部署记录，不代表本机性能。

- 2026-09-17：采用 WebRTC＋GPU 编码为主方案，Windows 默认 1080p、目标 60 FPS，保留 MJPEG 备用。本机网格场景前台采样平均约 52.2 FPS，无新增丢帧；跨设备和异地网络尚待验证。见 [验证记录](isaac-web-playground-core/deploy/windows/webrtc-verification-20260917.md)。

## 代码与资产来源

保留交付材料中的原始来源和许可说明。本仓库不新增对第三方代码或 NVIDIA 资产的授权；复用与分发时应核对对应材料的许可。
