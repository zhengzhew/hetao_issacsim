# 飞特 STS3215 连接工具与服务器更新

V5 增加飞特 STS3215 只读采集，主界面支持修改服务器地址，并处理 HTTPS/WSS 的服务器证书。
飞特使用 1000000 波特率、FF FF 回复、小端位置；德晟 SE 原读取协议独立保留。
连接时读取 ID 1–6 的型号，飞特必须全部为已验证的 STS3215（777），成功读取位置后才报告 serial-ready。
读取不修改扭矩、ID、位置目标或校准参数。校准文件中的硬件偏移不会重复叠加。

## 构建 Windows 工具

在 Windows 的项目根目录执行，使用目标机械臂对应的显式驱动：

```powershell
python -m pip install -r tools/requirements-leader.txt pyinstaller
python scripts/build_leader.py --driver feetech-so101 --connection-mode lan --server https://10.72.255.16
```

`lan` 只向服务器申请局域网接入，仍受服务器的 `localConnectorEnabled` 和网段判断约束。
需要配对码的部署改用 `--connection-mode pair-code`；这也是此前独立提供的飞特 V5 包使用的模式。
德晟设备使用 `--driver desheng-se-v401`。省略 `--server` 时首次使用由用户填写，旧设置仍会恢复。
新包明确配置的驱动和连接模式优先于旧包保存的值，但保留机械臂编号、校准内容、USB 绑定和服务器地址。

输出为 `web/downloads/so101-leader-windows.zip` 及 SHA-256 文件。构建会检查打包后的隐藏窗口启动、驱动、
连接模式和证书资源。完整解压运行 `SO101-Leader.exe`，无需另装 Python。
生成的 ZIP 不提交 Git；当前云端 Docker 构建也排除了 `web/downloads`，推送代码和重建 web 镜像不会自动发布 Windows 下载包。

## 已有服务器的更新

服务端功能修改仅在 `server/platform/access.js` 的机械臂登记驱动列表中加入 `feetech-so101`。
以下内网部署文件在这次更新中保持不变，服务器上的本地补丁仍可在更新分支后 rebase：

- `deploy/cloud/host_runtime.py`
- `deploy/cloud/manage.py`
- `server/platform/local-connector.js`
- `server/platform/gateway.js`

服务器获取新提交并合并本地补丁后，按现有部署流程重建 web 镜像、重启相关服务并验收。
Git 推送不会自动重启服务器。已有运行时配置、登录信息和局域网免配对开关由服务器保留。

相同机械臂编号如果此前登记为德晟，第一次以飞特连接会产生待确认的驱动变更。
教师管理页核对新驱动为 `feetech-so101`、校准指纹未变，确认后重新连接；不要为跳过审核改用新编号。
配对模式凭证过期时生成新的采集器配对码；免配对模式按原服务器授权策略重新申请。

## 证书与验证范围

用户提供的根证书只用于 `10.72.255.16:443` 的 HTTPS/WSS，仍要求证书链和主机名匹配。
其他地址使用系统默认信任链。没有关闭 TLS 校验，也不修改 Windows 系统证书库。

验证包含协议校验/分帧/重试、驱动分派、旧配置迁移、两种接入模式、TLS 作用域、服务端 WebSocket
和驱动变更确认流程。已用新驱动对六个 STS3215 连续读取 60 帧，无超时；完整云端同步仍需要部署后验收。
