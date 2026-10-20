# 云端试运行（Linux、独立 GPU、受信 VPN）

本目录是第一阶段部署入口：一个体验台，gateway / worker / sim 三个容器。
Windows 原有启动方式保留。尚需在真实 Linux GPU 主机上构建镜像并验收；
本机通过的路由、配置测试不能证明 GPU 兼容或远程视频质量。

## 把 Codex 接入云主机

GitHub 用于版本管理；SSH 用于在你的云主机上读写文件、运行命令、部署及查看日志。
可以继续在当前 Windows 聊天中工作，通过本机 OpenSSH 访问云主机，无需先在云端安装 Codex。

服务器准备好后提供：公网 IP（或可达的 VPN IP）、SSH 端口、用户名、操作系统、
本机 SSH 私钥文件路径或已有 SSH Host 别名。不要发送私钥内容或云平台账号密码。
使用密钥登录；服务器配置公钥，本机保存私钥。首次连接需核对主机指纹。
SSH 入站按实际管理端 IP 配置，不需要为了部署开放 8081/8765 等内部接口。

推荐流程：本地改动和测试 → 源码包/你授权后的 GitHub 提交 → SSH 部署 →
云端真实测试 → 修复同步回本地。只改云端容器内部文件会在重建后丢失。
本聊天不会因为使用 GitHub 就自动获得你的云主机权限。

如果希望在桌面应用中直接打开远程项目，也可使用“设置 → Connections → SSH”：
先配置本机 SSH Host 别名并确认能登录，再在远端安装和认证 Codex，最后选择远程项目目录。
这与“当前本机聊天通过 ssh 执行命令”是两种方式，前者需要远端 Codex 运行环境。
官方说明：https://learn.chatgpt.com/docs/remote-connections#connect-to-an-ssh-host

## 前置环境

- Ubuntu 22.04/24.04 x86_64，完整 NVIDIA GPU，具备 RTX 和 NVENC。
- 兼容 Isaac Sim 6.0.1 的 NVIDIA 驱动、Docker Engine、Compose plugin、NVIDIA Container Toolkit。
- 云端和体验电脑之间已配置可路由的私有 VPN，且允许媒体 UDP 双向通信。
  本配置默认只让网页监听指定 VPN IPv4；它不会替你配置 VPN 或放开防火墙。
- 云安全组不要向公网开放原生信令 TCP 49100、媒体 UDP 47998；
  这些服务仅供 VPN 内体验电脑访问。worker 8081、bridge 8765 仅监听本机。
- 准备可持久保存的数据盘，镜像仓库 nvcr.io、npm、PyPI、GitHub 下载可达。

官方参考：
- https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/requirements.html
- https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_container.html
- https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/manual_livestream_clients.html

## 首次启动

以下命令从 isaac-web-playground-core 目录运行；IP 是示例，必须换成 GPU 主机实际 VPN 地址。
`--accept-eula` 表示已阅读并接受 NVIDIA Isaac Sim 许可；脚本不会代替用户自动接受。

```bash
sudo python3 deploy/cloud/manage.py doctor
sudo python3 deploy/cloud/manage.py init --directory /srv/hetao-isaac --stream-host 10.8.0.1 --gpu 0 --accept-eula
sudo python3 deploy/cloud/manage.py up --directory /srv/hetao-isaac
sudo python3 deploy/cloud/manage.py ready --directory /srv/hetao-isaac --timeout 600
```

`up` 首次会下载基础镜像、构建前端并下载校验场景资产。CPU 镜像和 GPU 镜像分开。
构建需要联网；后续不要在每场活动重新下载资产。建议首次成功后将镜像标签固定到镜像 digest，
并保存包含宿主机驱动、Docker 和已下载镜像的云主机镜像。

`ready` 检查真实桥接、场景 ready、原生串流启用、信令端口和客户端 bundle，
**不代表浏览器收到了视频帧**。还必须从门店浏览器验证画面、FPS、丢帧和实际机械臂跟随。

老师初始密码保存在 `/srv/hetao-isaac/state/platform/teacher-password.txt`；
新云环境会生成独立密码，不读取或修改 Windows 上已有密码。
进入 `http://10.8.0.1:8080/manage`，分别生成浏览器和采集器配对码。
连接器只需改一次服务器地址并选择该机械臂自己的配置文件。
现有配对凭证有效期仍为 12 小时；本次不改变角色权限或把局域网免配对扩大到公网/VPN。

## 日常操作与账单

```bash
sudo python3 deploy/cloud/manage.py status --directory /srv/hetao-isaac
sudo python3 deploy/cloud/manage.py logs --directory /srv/hetao-isaac
sudo python3 deploy/cloud/manage.py down --directory /srv/hetao-isaac
```

down 仅停止容器并保留数据，**云主机仍计费**。之后在阿里云选择“节省停机”，
或腾讯云选择“关机不收费”，查询确认实际停机模式。磁盘等保留资源仍收费。
下一次先在云控制台开机；Docker 开机启动后，未被 down 移除的容器会按 restart 策略恢复。
如果上次执行了 down，需再次运行 up。执行关机前先结束活动；Kit 重启不恢复关卡物体姿态。
本轮没有绑定任何云账号、创建云资源或实现厂商开关机 API。确定厂商及实例后再接入。

更换 IP 时，编辑持久目录的 platform.json：
`host/publicOrigin` 是网页地址；station 的 `streamHost/publicIp` 是浏览器可达的视频地址。
修改后执行 up 重建容器配置；不要只改网页 URL。该 VPN 模板不包含公网 HTTPS/WSS 代理。

## 数据、升级与隔离

- `state/platform`：老师账户、配对凭证、审计。仅 gateway 使用。
- `state/stations/cloud-1/uploads`：该体验台资产和上传文件，worker 与 sim 共用。
- `cache`、`logs`：Kit 缓存和日志。缓存与驱动/Isaac Sim 版本有关，不能承诺跨版本直接复用。
- `worker-key`：gateway 到 worker 的服务凭证，独立文件挂载，不写进镜像。
- Docker 构建采用文件允许列表，不包含本机 .env、校准配置、运行数据、下载包或私钥。
- 资产以 sha256 清单更新，只更新清单管理的文件，不清空用户上传目录。

网关设 `ISAAC_PLATFORM_MODE=external` 时不会启动子进程。独立 worker 使用
`server/station-main.js`，由 `ISAAC_STATION_ID` 选择体验台。每个 station 可配置
`workerOrigin`、`streamHost`、`publicIp`、`webHost`、`bridgeHost`、`signalHost`。
网关只转发到管理员配置的 workerOrigin，浏览器不能提交地址切换目标。
跨机器 worker 通信走受信 VPN，或使用校验证书的 HTTPS。

当前 Compose 模板是单 GPU/单体验台。第二个门店独立运行需要第二套 worker+sim，
同一主机上配置不同端口，并显式选择 GPU；不同主机可以复用端口。
不能只往 JSON 加一行就认为第二套容器已经启动。
GPU 容器按 device_ids 选择宿主机 GPU，在容器内部使用索引 0。

## 无需 GitHub 也能传代码

在本机导出受控源码包（输出文件必须不存在）：

```powershell
python deploy/cloud/manage.py bundle --output run/cloud-source.tar.gz
```

通过 SSH/SCP 上传到云主机的新版本目录，再解压运行上述部署命令。
源码包不包含密钥、机械臂个人配置、运行数据和本机上传资产；仿真资产在镜像构建时校验下载。
它包含当前工作区源码，包括尚未提交的功能，所以不依赖 GitHub 仓库已经更新。
正式发布可改为拉取经过验证的 Git 提交或镜像版本；只有明确要求时才推送 GitHub。

## 云端验收

1. 新数据盘首次构建，SO101 和 MicroDuck 所有关卡能加载。
2. 浏览器真实显示 1080p30，确认编码、码率、丢帧，再试 60 FPS。
3. 真实主臂控制、断网重连、关卡切换；另一体验台无法被越权控制。
4. down / up 后账户和绑定保留；缓存与资产不重复下载。
5. 云平台停机不收费模式确认，重启后 VPN/网页/视频地址仍可达。
6. 两个独立体验台并发与 8 小时稳定性另行验收。
