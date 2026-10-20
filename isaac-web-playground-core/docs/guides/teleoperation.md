# Leader / follower teleoperation

## The shape of it

The leader arm is physical hardware on a serial port, so it cannot live inside
Isaac Sim. Three pieces:

    leader arm --serial--> so101_leader.py --HTTP--> playground --TCP--> Isaac Sim
    (your desk)            (wherever the arm is)     (web server)        (follower)

`tools/so101_leader.py` runs on whatever machine the arm is plugged into. It
needs only the Python standard library, and talks to the playground on the same
port the web page uses — so the arm can sit on your desk while the simulation
runs in the server room. It does **not** have to run on the Isaac Sim machine.

## Running it

    # no hardware yet: drive the follower with a generated trajectory
    python3 tools/so101_leader.py --server http://<host-ip>:8080 --simulate

    # real SO-101 leader (needs lerobot installed on that machine)
    python3 tools/so101_leader.py --server http://<host-ip>:8080 --port /dev/ttyACM0

Load an arm in the playground first — teleop is refused unless the active robot
is joint driven.

## Joint names and units — read this before plugging in hardware

The calibration map is keyed by **follower** joint name, with `source` naming
the **leader** joint. Getting that backwards produces a session where every
sample is rejected, so the client no longer guesses: it engages first, asks the
follower for its joint names, and builds the map against those.

If nothing matches it says so and exits rather than streaming into the void:

    [leader] no leader joint maps onto a follower joint.
             Follower has: Rotation, Pitch, ...; leader reports: shoulder_pan, ...
             Map them with --map follower=leader,... and try again.

    python3 so101_leader.py --port /dev/ttyACM0 \
        --map Rotation=shoulder_pan,Pitch=shoulder_lift,Jaw=gripper

`--unit rad|deg|raw` converts what the leader reports. lerobot does not report
radians, so **`--unit rad` on real hardware will drive the follower into its
limits**. Check what your leader actually returns before trusting the default.

## Calibration

By default the script zeroes the follower at whatever pose the leader is in
when it starts, then streams from there. Sending raw servo counts straight at a
follower is how you slam an arm into its limit on the very first sample, so raw
pass-through is opt-in (`--no-zero`).

Each joint maps as `follower = scale * (raw - offset)`, optionally inverted:

    {"calibration": {"Rotation": {"source": "Rotation", "offset": 100.0,
                                  "scale": 0.01, "invert": true}}}

Capture one and reuse it:

    python3 tools/so101_leader.py --port /dev/ttyACM0 --write-calibration leader.json
    python3 tools/so101_leader.py --port /dev/ttyACM0 --calibration leader.json

With no calibration, joints pass through by name and anything the follower does
not have is dropped.

## Safety

- **Slew limited.** No joint moves more than `--teleop-max-step` (0.08 rad by
  default) per sample, so the first sample after engage ramps toward the leader
  instead of jumping there from wherever the arm happens to be.
- **One leader at a time.** Engaging mints a token; samples must carry it. A
  killed leader's in-flight samples cannot move the arm or wedge the next
  leader's sequence numbers, and an old leader exiting cannot stop the new one.
- **Sliders and `/api/robot/joints` are refused while a leader is engaged**, so
  a second tab cannot fight the stream.
- **A calibration belongs to its session.** It is cleared on disengage and on
  relaunch, so the next operator never inherits someone else's offsets.
- **Hold, never drop.** If the leader stops sending for `ISAAC_TELEOP_HOLD`
  seconds (0.5 by default) the follower holds its last pose. It is not zeroed —
  an arm commanded to zero falls.
- **Stale samples are discarded** by sequence number, so a sample that overtakes
  another on a lossy link cannot rewind the arm.
- **Relaunching a scene or robot drops the teleop session**, because the
  follower it was driving no longer exists.
- **The page can cut the leader loose** at any time with *Disengage leader*.
- While a leader is driving, the joint sliders become a read-only readout.

## Rate and latency — measured, not guessed

Rate and lag are separate problems and they were fixed separately.

The client sends over **several connections at once** (`--connections`, default
4) and holds **one slot** for the newest pose rather than a queue. A queue was
tried and made things worse: buffered samples add their wait to the control lag,
which is the one thing teleoperation cannot afford. With a single slot, a pose
nobody has picked up is simply overwritten by a fresher one.

Measured from a Mac to the Windows box over the corporate VPN, simulated leader
at 30 Hz:

| Configuration | Applied rate | Lag |
|---|---|---|
| 1 connection | 7 Hz | 178 ms |
| 4 connections + queue | 15-17 Hz | 270 ms |
| **4 connections, single slot** | **20 Hz** | **184 ms** |
| 8 connections, single slot | 22 Hz | 202 ms |

Eight connections buy 2 Hz and cost 18 ms and a lot of superseded samples; four
is the setting.

Where the 184 ms goes, from the same measurements:

- **~90 ms** is the VPN round trip. `curl` on a reused connection to
  `/api/config`, which touches nothing, measures 78-115 ms.
- **~40 ms** is the bridge path. `/api/teleop/status` on a reused connection
  measures 103-165 ms, and the bridge itself reports 0.2 ms of work — the rest
  is waiting for the Kit main loop, which is single threaded and runs every op
  including rendering.
- the remainder is slot wait and jitter.

**So: remote teleoperation over this VPN has a floor of roughly 150 ms.** At
20-30 Hz the motion is continuous rather than stepping, but it is visibly behind
the hand. Fine for demonstrating the pipeline; poor for precise work.

**The only way to get low latency is to run the leader client on the machine
running Isaac Sim** — loopback is 0.6 ms mean. That means the physical arm
plugged into that box, with a person next to it. Watching the simulation can be
remote; precise teleoperation cannot. These are different use cases and it is
worth being explicit about which one is being asked for.

Samples are rate limited twice: `ISAAC_TELEOP_MAX_HZ` (120/s) across everything,
and `ISAAC_TELEOP_MAX_HZ_PER_SOURCE` (80/s) per peer, so one misbehaving client
cannot spend the whole budget and starve the real leader.

## Endpoints

`POST /api/teleop/engage` · `POST /api/teleop` (one sample) ·
`POST /api/teleop/disengage` · `POST /api/teleop/calibrate` ·
`GET /api/teleop/status`

The token that `engage` returns is a capability: samples, calibration changes
and a targeted disengage all require it. `GET /api/teleop/status` is public and
therefore reports only `has_token`, never the token itself. A disengage with no
token always works — it is the operator's stop control.

## Not done

- No authentication. Anyone who can reach the port can engage a leader and move
  the arm. Same trade-off as the rest of the tool, but the consequence is larger
  here.
- Single follower. A second leader that engages takes over from the first, which
  is then cleanly locked out — but there is no queue or arbitration.
- The leader's own pose is not drawn in the scene. You see the follower only.
- The real-hardware path (`--port`) has never been run against an actual SO-101.
  The simulated leader has been exercised end to end against real Isaac Sim:
  arm loaded, joints driven, watchdog hold verified.

## 德盛 SE 主臂（本机接入）

`tools/desheng_leader.py` 使用已在这次实物臂验证的兼容位置读取：115200 bps，FF FF 请求 / FF F5 回复，读 0x38 的 2 字节大端 12 位位置。ID 1–6 对应底座、肩、肘、腕俯仰、腕旋转、夹爪。读回前导字节 02 保留为本设备的已观测契约，不解释为飞特状态；不能由此断言所有德盛固件兼容。

在 core 目录运行：

    python tools/desheng_leader.py --port COM19

COM 编号以 Windows 当前识别为准。依赖 pyserial；不需要 LeRobot。先在网页选择 SO-101 关卡，再启动采集。脚本只向实物发送位置/扭矩状态读取，仿真目标通过 HTTP 发出，不启用实物扭矩，也不发送运动、写参数或自动校准指令。

使用相对跟随：连接时记录实物编码器值与当前虚拟关节位置，以 2π/4096 映射位移并处理环绕。它不保证起始绝对姿态一致；各关节正反方向需实际核对，可用 `--invert Pitch,Elbow` 指定反向（仅示例，不是已确定配置）。不能套用另一台主臂校准数据。

默认目标 20 Hz；`--seconds 5` 为有界测试。Ctrl+C 会断开跟随并释放串口；也可指定 `--stop-file run/desheng-leader.stop`，创建该文件即可停止。重新加载 SO-101 关卡后会自动重连，并以新场景和实物当时的位置重新建立相对跟随起点；短暂桥接超时会重试，持续不可用 30 秒则退出。网页明确断开主臂、切换到小鸭子、其他主臂接管、串口读取连续三次超时或不可恢复的接口拒绝会退出。启动前如有停止文件，须明确移除再运行。

2026-10-10：COM19 检出 1–6 号电机，手动底座前后原始读数从约 2138 变为 1964；六轴扭矩状态均读回 0。首轮真实串口到仿真 HTTP 测试 5 秒应用 100 个样本，约 20 Hz。随后复现了选关清除跟随会话、一次 1.5 秒超时令采集程序退出的问题；修复后真实重载 arm-block（launchId 2 → 3）自动重连成功，重新持续应用样本且无丢弃，用户确认网页机械臂已跟随手动动作。协议解析、错帧拒绝、位置环绕及重连判断单元测试共 13 项通过（含串口超时恢复、重试上限与异常数据拒绝）。全部关节的正反方向和绝对姿态对齐尚未逐一验收。
同次验证从 Isaac Sim 实际关节位置采样 50 次，肩和肘的位置变化范围分别约 0.420 / 0.533 rad。随后捕获 ID 5 单次读取超时，补充每次读取最多三次尝试；持续失败仍退出释放串口，不发送实物运动指令。


### 使用用户提供的 SE 范围校准（2026-10-10）

项目副本为 `configs/leader_arm_calibration.json`，来自用户提供的同名文件，格式为 `lerobot_style_desheng_v401`。固定映射启动命令：

    python tools/desheng_leader.py --port COM19 --calibration configs/leader_arm_calibration.json --stop-file run/desheng-leader.stop

如停止文件存在，先确认旧进程已退出，再移除该文件。省略 `--calibration` 仍为旧的相对模式。

每轴先按 `range_min/range_max` 归一化到 -100..100，应用文件的 `drive_mode`，再线性映射到 Isaac Sim 返回的该关节上下限。超出实测范围时截断；仿真端保留渐进追踪。六轴 ID 沿用 1–6 到 Rotation、Pitch、Elbow、Wrist_Pitch、Wrist_Roll、Jaw 的对应关系。连接时实物姿态不再作为零点，SO-101 重载后也沿用固定映射。

文件中六轴 `drive_mode=0`。`hardware_middle_offset` 已是硬件校准的记录，不重复写入或叠加；`center`、`neutral` 不替代范围归一化的中点。当前仅接受 `homing_offset=0`，未知语义的非零偏移直接拒绝，避免猜测。此映射实现范围比例对应，不证明实物角度与仿真角度一比一。文件没有记录仿真轴向；实际方向仍需逐轴核对，需要时使用 `--invert` 指定额外的仿真反向，不能把六轴都为 0 当作方向已验收。

24 项协议、超时恢复、重连和校准测试通过，覆盖六轴端点/中点、越界截断、反向、硬件偏移不重复应用、缺失/错误字段拒绝。

本机接入验证：加载上述文件后约 20 Hz，静止采样时六轴仿真实际位置与命令最大差约 0.00545 rad（0.31°）。重载 arm-block 后自动重新接入，恢复 46 个样本时为 19.7 Hz、无丢弃；固定映射目标保持一致（允许编码器读数抖动）。这不等于实物与仿真姿态或方向已逐轴验收。

2026-10-10 后续断连定位：日志明确显示 `ID 6: implausible single-sample change -884`，触发旧相对模式的 512 刻度阈值并退出，并非仿真服务退出。已校准的绝对范围映射不再使用此阈值，继续执行帧校验、12 位读数验证、范围截断和仿真渐进追踪。加入夹爪 2571 → 1687 的主循环回归用例，确保变化后仍持续发送校准目标；共 25 项测试通过。此回归为模拟串口输入，不代表真实手动操作已经验收。


### 六轴方向修正（2026-10-10）

用户确认修复退出阈值后可以持续同步，并明确反馈六轴方向全部反向。保留上传文件的原样副本 `configs/leader_arm_calibration.json`，新增仿真专用 `configs/leader_arm_isaac_calibration.json`：仅将六轴 `drive_mode` 从 0 改为 1，全部量程、零点和硬件中位记录保持一致。不会向实物写方向参数。当前使用以下命令；不要再额外叠加六轴 `--invert`，否则会抵消反向：

    python tools/desheng_leader.py --port COM19 --calibration configs/leader_arm_isaac_calibration.json --stop-file run/desheng-leader.stop

范围反转围绕仿真上下限的中点进行，包含非对称的夹爪和肘关节范围；不是简单把弧度值取负。


### 局域网另一台 Windows 电脑接主臂（2026-10-10）

> 以下为旧版联调记录，IP 和打包内容不是当前默认值。当前连接器操作见 [体验台运行与设备配对](platform-operations.md)：选配置、点击连接，自动保存设置；当前服务器 WLAN 同一子网内的新版连接器已免配对。

主臂插在 10.205.22.46，仿真服务器当前为 10.205.22.98。新电脑仅打开浏览器不会自动读 USB；需同时运行本地主臂连接工具。下载 `http://10.205.22.98:8080/downloads/so101-leader-windows.zip`，完整解压后启动 `SO101-Leader.exe`，服务器保持 `http://10.205.22.98:8080`，刷新并选择新电脑识别的串口，再点连接。该设备的 COM 号不沿用服务器原先的 COM19。

源码为 `tools/desheng_connector.py`，使用 `desheng_leader.py` 和 `desheng_calibration.py`，附带用户当前这台实体主臂的六轴反向配置。设备仍执行只读关节采集。停止按钮/关闭窗口通过本进程独有的停止文件退出并释放串口；日志写入解压目录下 logs。`connector.json` 可调整默认服务器。

可用 PyInstaller 重新构建：

    python -m PyInstaller --noconfirm --clean --windowed --onedir --name SO101-Leader --paths tools --distpath run/leader-client-dist --workpath run/leader-client-build --specpath run tools/desheng_connector.py

输出目录还需放入当前的 `leader_arm_isaac_calibration.json`（来自 configs）、`connector.json`（含 server 与 calibration 文件名），以及使用说明。生成物放在被忽略的 run 与 web/downloads 下。

验证边界：打包后 EXE 的 Tk 窗口、校准加载、串口枚举通过；工作进程通过当前服务器 LAN 地址到达串口打开步骤，无效串口会明确失败退出且不接管仿真。另一台电脑上的 USB 和实际同步尚待运行该工具验证。
