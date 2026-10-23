# 飞特 STS3215 连接工具与服务器更新

V6 在主界面固定显示采集器配对码，升级时清除免配对模式的影响。继续支持飞特 STS3215 只读采集、
修改服务器地址和 HTTPS/WSS 服务器证书。
飞特使用 1000000 波特率、FF FF 回复、小端位置；德晟 SE 原读取协议独立保留。
连接时读取 ID 1–6 的型号，飞特必须全部为已验证的 STS3215（777），成功读取位置后才报告 serial-ready。
读取不修改扭矩、ID、位置目标或校准参数。校准文件中的硬件偏移不会重复叠加。

## 构建 Windows 工具

在 Windows 的项目根目录执行，使用目标机械臂对应的显式驱动：

```powershell
python -m pip install -r tools/requirements-leader.txt pyinstaller
python scripts/build_leader.py --driver feetech-so101 --server https://10.72.255.16
```

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
和驱动/校准自动更新流程。已用新驱动对六个 STS3215 连续读取 60 帧，无超时；完整云端同步仍需要部署后验收。
