# SO-101 与 MicroDuck 七关卡

本地开发版，沿用薄荷绿、白色和黄色的大按钮界面、伴学角色、语音与家长入口。保留 NVIDIA Isaac Sim 描述和 WebRTC GPU 编码链路。

## 入口与玩法

首页先选 SO-101 或 MicroDuck，再选择任务：机械臂三个关卡，小鸭子四个关卡。

| 伙伴 | 关卡 | 操作与通过条件 |
| --- | --- | --- |
| SO-101 | 方块搬家 | 用六个关节滑杆夹起黄色方块，放入绿色区域并松开，落稳后通过 |
| SO-101 | 幸运骰子 | 通过实物主臂或网页关节控制夹起骰子，抬腕并张开夹爪，自己完成投掷；没有自动抛出按钮，真实物理落地，朝上为 6 才通过 |
| SO-101 | 水果分拣员 | 两个红苹果放红区，两个橙子放橙区；每个都需夹起、放稳；浅取物托盘和分类盘帮助防滚 |
| MicroDuck | 走到目标区 | 按住方向按钮移动，松开停止；进入绿色区并站稳 |
| MicroDuck | 坐下，再站起 | 先坐稳，再站起；读取机身高度和朝向判定 |
| MicroDuck | 翻滚小勇士 | 调用原模块的 roulade 策略尝试前滚翻；完成一周并站稳才判定通过，目前动作稳定性仍待改进，失败可重新挑战 |

| MicroDuck | 足球小射手 | 足球初始放在右脚前，点击“右脚踢球”；也可按住方向键调整位置。足球从正面完整越过球门线、位于两门柱之间且低于横梁才通过 |

“重新挑战”会重建当前关卡，足球关同时复位小鸭子与足球；切换伙伴会重新加载对应机器人。当前是一台共享仿真实例，多个浏览器会看到、控制同一个关卡，不是独立房间。

## 本机运行

在项目根目录执行：

```powershell
# 已在这台电脑完成；新电脑或丢失 uploads/run 时执行一次，需要联网。
.\isaac-web-playground-core\deploy\windows\setup-challenges.ps1
# 启动网页与 Isaac Sim，自动选择 WLAN IPv4。
.\isaac-web-playground-core\deploy\windows\start-native.ps1
```

默认 Isaac Sim 安装在 `D:\IsaacSim\6.0.1`。网页端口 8080，WebRTC 信令 TCP 49100、媒体 UDP 47998；局域网防火墙规则仍沿用此前授权范围。

模型与策略在 `uploads/challenges/`，ONNX Runtime 在 `run/python-deps/`，都不进入 Git。安装脚本使用当前 Isaac Sim 的 Python，不修改其全局 Python 包。资产下载有固定提交和摘要校验。

## 实现与边界

- `configs/challenges.json`：关卡文字与对应场景、机器人。
- `bridge/core/challenges.py`：关卡场景、物理道具、真实状态采集及动作。
- `bridge/core/challenge_rules.py`：独立的通过判定；网页不能直接设置通关。
- `bridge/core/duck_runtime.py`：200 Hz PhysX、50 Hz ONNX 策略，复用 bundle 的控制状态机与滤波。策略只写关节目标，只有重置会改机器人初始姿态。
- `web/challenges-ui.js`：关卡说明、动作、进度、重试入口。
- SO-101 夹爪增加可见接触垫并降低最大夹持力，物理采样提高到 200 Hz；受限关节目标仍由真实碰撞、重力与摩擦决定抓取结果。
- 足球由右脚踢球策略驱动关节，通过物理碰撞运动；点击踢球不会瞬移足球或直接设置球速度。踢偏后可用“重新挑战”重新摆球。
- 骰子没有指定结果、吸附或强制摆正。方块/水果必须抬起并放稳才算成功。
- 水果采用带碰撞的程序化简化造型，苹果带叶子；不是写实模型。
- 保留旧机器人后端目录供兼容，儿童首页只显示两个新入口。

## 验证

纯判定测试（目前 21 项）：`python isaac-web-playground-core/scripts/test_challenge_rules.py`。

真实仿真回归：`python isaac-web-playground-core/scripts/accept_challenges.py --motion-tests`。该脚本会重建当前共享关卡并移动虚拟机器人，请在没有其他人操作时运行。
真实仿真与浏览器交互验证范围在同目录 `challenges-validation.md` 记录；不要把接口测试等同于浏览器 WebRTC 播放测试。

## 上游来源

MicroDuck 控制代码来自本地 `microduck-bundle`。模型来自 [OSRBOT microduck-ros2-isaac](https://github.com/osrbot/microduck-ros2-isaac/tree/a2e7f327344eda402467af83053f6e33ca6bcdb7)，策略来自 [Pollen Robotics microduck](https://github.com/pollen-robotics/microduck/tree/590b986bd8c0d50ae02cb3ea2f59c463b6828168)。SO-101 USD 来自 [OpenSO-101 v0.1.0](https://github.com/jixinyan/OpenSO-101/releases/tag/v0.1.0)。

MicroDuck 上游 NOTICE 将代码与三维模型区分授权：模型标注 Creative Commons BY-SA-NC，未指定版本。本地测试接入不代表已取得门店商业使用授权；正式门店使用前需向权利方确认。下载保留 `NOTICE-MICRODUCK.md`，模型及权重不随本项目代码重新分发。


### 机械臂底座与任务地面（2026-10-10）

删除三种机械臂关卡共用的 ArmMount 垫台。SO-ARM101-USD.usd 的底座网格最低点在模型坐标 z=0.030081447 m；SO-101 的 spawn_z 设为 -0.030081447 m，使底座底面与任务地面 z=0 重合。原配置 spawn_z=0.012 m，但旧 XformCommonAPI 放置路径不兼容此模型的 orient 操作，实际锚点仍在 z=0；本次同时修正为直接设置 translate 操作，因此相对旧实际位置下移约 30.08 mm。方块、骰子和水果的任务位置不变，保留机械臂固定根约束、关节校准与跟随方向。该偏移针对当前模型测量；更换模型后需重新测量底座底面。

验证：使用实际 USD 模型调用修正后的放置代码，底座最低点为约 -2.6e-10 m（浮点误差），旋转/缩放保持；另验证矩阵变换模型的放置分支。真实 Isaac Sim 依次加载 arm-dice、arm-fruit、arm-block 均 ready/stable，场景均无 /World/ArmMount；当前恢复 arm-block。已查看实际渲染帧，主臂仍使用六轴反向后的仿真专用校准。
