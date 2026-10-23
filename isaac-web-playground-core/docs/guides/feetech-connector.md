# 飞特 STS3215 连接工具与服务器更新

当前连接器默认按 **50 Hz（每 20 ms）** 采样和发送，命令行 `--rate` 支持 1–50。
USB 采样、网络发送和接收分别运行，接收确认不会把发送频率拖回 20 Hz；网络拥塞时只保留最新姿态。
窗口标题显示 `50 Hz`，`serial-ready` 日志包含 `target_rate_hz: 50`，同步状态仍显示仿真端实际应用频率。
此次提频需要更新 Windows 连接工具；已有服务端的默认限流允许 50 Hz，无需更改部署配置。
实际云端应用频率还取决于服务端仿真循环和网络，以现场同步读数为准。

2026-10-24 本地提频实测：

| 验证链路 | 修改前 | 修改后 |
| --- | --- | --- |
| 黄色主臂 COM8，六关节只读采样，4 秒 | 20.00 Hz | 49.84 Hz（200 帧） |
| 模拟 USB → 真实 Python 连接器 → 真实网关 → 模拟仿真服务，3.2 秒 | 20.01 Hz | 49.67 Hz（157 帧） |

网络测试的模拟仿真服务延迟 7 ms 返回确认，验证发送不再受接收等待节奏限制；
实物读取没有写入舵机目标、扭矩或校准。这些结果不等同于公司云端实际应用频率。

同日使用黄色主臂连接现有 `https://10.72.255.16` 的 Isaac Sim：源码连接器连续测试约 21 秒，
服务端累计应用 1,038 帧，未丢弃、未重连；采样观察通常为 48.7–50.5 Hz，一次为 45.6 Hz。
最终打包 EXE 的约 12 秒日志显示 45.8–50.1 Hz，最后一条确认序号为 608，期间没有重连。
随后验证程序的状态查询超时，本机直连服务器的 443/8080 端口也超时，因此未完成最终 EXE 的 30 秒复测。
这是短时实测记录，不代表已完成长时间稳定性测试。此次未改动正在运行的服务端或其配置。
发送与接收独立调度，但同一 TLS 连接的读写会串行执行，避免并发读写造成 WSS 断开。

V6 在主界面固定显示采集器配对码，升级时清除免配对模式的影响。继续支持飞特 STS3215 只读采集、
修改服务器地址和 HTTPS/WSS 服务器证书。
飞特使用 1000000 波特率、FF FF 回复、小端位置；德晟 SE 原读取协议独立保留。
连接时读取 ID 1–6 的型号，飞特必须全部为已验证的 STS3215（777），成功读取位置后才报告 serial-ready。
读取不修改扭矩、ID、位置目标或校准参数。校准文件中的硬件偏移不会重复叠加。

## 构建 Windows 工具

在 Windows 的项目根目录执行，使用目标机械臂对应的显式驱动：

```powershell
python -m pip install -r tools/requirements-leader.txt pyinstaller
# 免配对（内网同子网）：直连 8080，不经过 HTTPS 反代
python scripts/build_leader.py --driver feetech-so101 --connection-mode lan --server http://10.72.255.16:8080
# 需要配对码：走 HTTPS/WSS，连接器用随包根证书校验
python scripts/build_leader.py --driver feetech-so101 --connection-mode pair-code --server https://10.72.255.16
# 默认（等价 pair-code）：省略 --connection-mode 时走 HTTPS/WSS 配对
python scripts/build_leader.py --driver feetech-so101 --server https://10.72.255.16
```

`lan` 只向服务器申请局域网接入，仍受服务器的 `localConnectorEnabled` 和网段判断约束。
免配对必须直连 `http://10.72.255.16:8080`：HTTPS 入口经反代转发并带代理头，服务器按“仅接受直接局域网连接”拒绝，
该场景改用 `--connection-mode pair-code` 走 HTTPS/WSS；这也是此前独立提供的飞特 V5 包使用的模式。

V6 固定使用教师端生成的采集器配对码，不请求 `/platform/connector/connect`。
连接器访问 HTTPS 入口时使用 `/platform/pair` 换取设备凭证，再通过 WSS 同步，适用于经代理、跨网段的部署。
主界面输入框一直显示；已有有效配对凭证时可以留空，过期后填新码。浏览器配对码不能代替采集器配对码。
旧包配置、用户设置中的 `autoConnect:true` / `connectionMode:lan` 会被迁移；旧 LAN 凭证需要重新配对。
德晟设备使用 `--driver desheng-se-v401`。省略 `--server` 时首次使用由用户填写，旧设置仍会恢复。
新包明确配置的驱动优先于旧包保存的值，但保留机械臂编号、校准内容、USB 绑定和服务器地址。

输出为 `web/downloads/so101-leader-windows.zip` 及 SHA-256 文件。构建会检查打包后的隐藏窗口启动、驱动、
连接模式和证书资源。完整解压运行 `SO101-Leader.exe`，无需另装 Python。
生成的 ZIP 不提交 Git；当前云端 Docker 构建也排除了 `web/downloads`，推送代码和重建 web 镜像不会自动发布 Windows 下载包。

## 已有服务器的更新

V5 服务端更新已在 `server/platform/access.js` 的机械臂登记驱动列表中加入 `feetech-so101`。
V6 配对修复只需更新 Windows 工具；服务器已经支持飞特时，直接使用现有教师端的“生成采集器配对码”。
以下内网部署文件在这次更新中保持不变，服务器上的本地补丁仍可在更新分支后 rebase：

- `deploy/cloud/host_runtime.py`
- `deploy/cloud/manage.py`
- `server/platform/local-connector.js`
- `server/platform/gateway.js`

服务器获取新提交并合并本地补丁后，按现有部署流程重建 web 镜像、重启相关服务并验收。
Git 推送不会自动重启服务器。已有运行时配置、登录信息和局域网免配对开关由服务器保留。

相同机械臂编号切换驱动或校准文件时，服务端直接采用本次连接的有效配置并记录变更，无需教师再次确认。
旧版本留下的待确认记录会在下次连接时清除；本次修复需要更新服务端，现有 V6 连接器无需重装。
配对凭证过期时生成新的采集器配对码。公司云端不需要为此扩展免配对网段或信任代理转发头。

## 证书与验证范围

用户提供的根证书只用于 `10.72.255.16:443` 的 HTTPS/WSS，仍要求证书链和主机名匹配。
其他地址使用系统默认信任链。没有关闭 TLS 校验，也不修改 Windows 系统证书库。

验证包含协议校验/分帧/重试、驱动分派、旧配置迁移、两种接入模式、TLS 作用域、服务端 WebSocket
和驱动/校准自动更新流程。已用新驱动对六个 STS3215 连续读取 60 帧，无超时；50 Hz 的实物与云端验证范围见本文开头。
