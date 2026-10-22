# 腾讯云 TencentOS 4：从 GitHub 拉取源码部署

目标是现有 **TencentOS Server 4、L20 48 GB、50 GB 系统盘 + 70 GB /data 数据盘**，一个独立体验台。安装和更新都在服务器自己的终端执行；不需要 Windows 上传程序、SSH 私钥交给程序、阿里云元数据或重装操作系统。

本流程已有本机自动化验证，**尚未在这台腾讯云服务器完成 GPU、RPM 安装和浏览器视频实测**。磁盘预算是预检条件，不代表未来任何镜像版本都能在相同空间内安装。

## 1. 获取代码

先用公司提供的方式登录服务器，然后执行：

```bash
sudo dnf install -y git python3
sudo mkdir -p /opt/hetao-isaac
sudo git clone --depth 1 https://github.com/zhengzhew/hetao_issacsim.git /opt/hetao-isaac/repo
cd /opt/hetao-isaac/repo/isaac-web-playground-core
```

若仓库是私有的，使用已获得授权的 GitHub 账号或只读 deploy key；不要把 token 写进 clone URL 或提交到仓库。已有该目录时直接进入目录更新，不要覆盖或删除它。

## 2. 核对磁盘与网络

```bash
findmnt /data
df -h / /data
```

`/data` 必须是数据盘的真实挂载点，且已配置开机挂载。脚本不分区、不格式化、不移动已有 Docker 数据。数据盘缺失时安装和开机启动都会停止，避免大镜像落到系统盘。

| 所在磁盘 | 路径与用途 |
|---|---|
| 50 GB 系统盘 | `/opt/hetao-isaac/repo` 源码，`/srv/hetao-isaac` 账户、上传、Kit 缓存与日志 |
| 70 GB 数据盘 | `/data/docker` 镜像、容器层、Docker 构建缓存 |

首次构建按系统盘空闲 12 GiB、数据盘空闲 45 GiB 预检；已有基础镜像后的构建按系统盘 6 GiB、数据盘 8 GiB 预检，构建阶段再检查。当前配置表的约 46 GiB + 65 GiB 可通过首次预算。相同文件系统上的预算会相加，不能用另一块盘的空闲空间抵扣。

空间控制包括：经典 overlay2 存储、禁止 Docker 29 的 containerd 镜像存储重复保留压缩层、构建串行执行、共享网页镜像、4 GB 构建缓存回收目标、容器日志每份 10 MB/最多 3 份、Python/npm 下载缓存不保留。构建缓存回收目标不是硬磁盘配额，拉取/解包仍有临时空间开销。更新成功后只尝试删除本项目被替换的旧镜像标签，不强制删除，不运行全局 prune。

由公司运维配置安全组及实际网络：

| 入站端口 | 来源 | 用途 |
|---|---|---|
| TCP 22 | 管理电脑 | SSH 维护 |
| TCP 80 | 公网可达 | IP 证书申请、自动续期 |
| TCP 443 | 使用者电脑/门店出口 | 网页、登录、受认证 WSS 信令 |
| UDP 47998 | 使用者电脑/门店出口 | WebRTC 视频 |

8080、8081、8765、49100 不需要开放公网。用户电脑网络必须允许访问视频 UDP。公网 IPv4 必须支持入站访问，不能仅是共享 NAT 出口地址。出站需能访问腾讯软件源、Docker/NVIDIA 仓库、`nvcr.io`、`public.ecr.aws`、npm、PyPI、GitHub/raw.githubusercontent.com 和 Let's Encrypt；若受公司网络限制，由运维配置允许的代理或镜像源。

## 3. 在服务器执行部署

先阅读 [Isaac Sim 容器及许可说明](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_container.html)。确认后，把下面 `公网IPv4` 换成这台服务器的真实入站地址：

```bash
sudo python3 deploy/cloud/install_host.py --public-ip 公网IPv4 --accept-eula --install-driver
```

脚本会：

1. 核对 TencentOS 4、x86_64、挂载点和两块盘的空闲空间。
2. 如果驱动尚未安装，从 TencentOS EPOL 源安装 **580 系列驱动**，不安装整个 CUDA Toolkit。已有驱动只检查，不自动替换。580 分支是程序预检下限；最终以真实 Kit/RTX/NVENC 运行结果为准。若驱动未能加载，检查 DKMS 日志并按提示手动重启，之后重新执行相同命令。
3. 安装 Docker CE、Compose、Buildx 和 NVIDIA Container Toolkit。Docker 使用腾讯镜像站的 EL9 包，仅为该源固定版本 9，不改变 TencentOS 的全局 `$releasever`。已有其他 Docker 安装不会被自动卸载；Compose/Buildx 缺失时需从原安装来源补齐。
4. 在**首次启动 Docker 前**设置 `/data/docker` 和 overlay2，保留其他 daemon.json 配置。检测到已有镜像、容器或离线存储时停止，不擅自迁移。
5. 使用锁定的 Isaac Sim **6.0.1** 构建仿真和网页镜像。SO101、MicroDuck 所需资产按清单下载并校验 SHA256；GitHub 只存源码与校验清单，不复制本机运行数据或下载完整 Isaac 资产库。
6. 保存公网 IP、生成老师密码、启用 HTTPS/WSS 和 systemd 自启动，等待真实场景与信令就绪。

安装驱动可能需要你重启服务器；程序不会自动重启。公司已安装驱动时可省略 `--install-driver`。Node、Python 运行依赖和 Isaac Sim 在容器中，宿主机无需 Conda、Node/npm、CUDA Toolkit、cuDNN 或桌面环境。

安装过程中终端保持连接。需要离开时先使用公司已有的终端会话管理方式，或者在 `tmux` 会话中执行上述命令。下载/构建失败后可以重跑；首次安装失败时不要删除 `/srv/hetao-isaac`，已有账户和上传数据会保留。

## 4. 从浏览器验收

```bash
sudo cat /srv/hetao-isaac/state/platform/teacher-password.txt
sudo cat /srv/hetao-isaac/startup-status.json
```

打开 `https://公网IPv4/`，老师管理入口为 `/manage`。按页面提示登录并配对体验浏览器。

公网 IP 证书由 Caddy 自动申请和续期，不需要域名。端口 80 应保持可达；短期证书到期、网络阻断或签发失败会影响浏览器访问。**scene-ready 只表示真实仿真与信令就绪，不代表浏览器已收到视频或 HTTPS 证书已验收。**

确认：证书受浏览器信任；收到持续更新的视频；SO101 和 MicroDuck 切关、控制正常；断开再连和服务器重启后可恢复。实物主臂遥操作还需本地连接器与实体设备验证。当前一套模板只有一个仿真实例，多人独立运行、60 FPS 和长时间稳定性需另测。

## 5. 以后更新和启动

```bash
cd /opt/hetao-isaac/repo
sudo git pull --ff-only
cd isaac-web-playground-core
sudo python3 deploy/cloud/install_host.py --accept-eula
```

更新复用保存的公网 IP、老师账户、配对与上传数据。先构建新镜像，再停止旧服务切换；下载或构建失败时不主动停止原服务。构建完成后的切换阶段会短暂停机，启动失败需查看日志。本流程不提供自动版本回滚。

公网 IP 改变时重新运行安装命令并传入 `--public-ip 新公网IPv4`，同时更新安全组和浏览器地址。开机只使用保存的 IP 和本地镜像，不访问阿里云或腾讯云元数据，不自动拉取 GitHub/构建/更新地址。建议使用稳定的公网地址。

```bash
sudo systemctl status hetao-isaac --no-pager
sudo systemctl restart hetao-isaac
sudo systemctl stop hetao-isaac
sudo systemctl start hetao-isaac
```

停止容器不会停止云主机计费。账户、配置、缓存和上传都在 Git 仓库外，按公司方式备份 `/srv/hetao-isaac`。

## 排查

```bash
# 只读预检；首次安装尚缺驱动/容器时会如实报告
sudo python3 deploy/cloud/install_host.py --check --public-ip 公网IPv4
sudo journalctl -u hetao-isaac -n 100 --no-pager
sudo python3 deploy/cloud/manage.py status --directory /srv/hetao-isaac
sudo python3 deploy/cloud/manage.py logs --directory /srv/hetao-isaac
sudo docker system df
sudo du -h -d 1 /srv/hetao-isaac
```

若网页可开但视频黑屏，核对 UDP 47998、填写的公网 IP、真实场景状态和容器 NVENC 驱动。若镜像拉取失败，先核对 DNS、出站和日志。不要通过关闭证书检查、清空磁盘、全局 Docker prune 或删除账户来重试。

## 官方依据

- [TencentOS 4 NVIDIA 驱动 RPM 安装](https://cloud.tencent.com/document/product/1397/127038)
- [腾讯云 Docker 安装](https://cloud.tencent.com/document/product/213/46000)
- [Docker CE EL9 软件包](https://docs.docker.com/engine/install/centos/)
- [NVIDIA Container Toolkit RPM 安装](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html)
- [Docker containerd 镜像存储的空间开销](https://docs.docker.com/engine/storage/containerd/)
- [Isaac Sim 6.0.1 容器](https://docs.isaacsim.omniverse.nvidia.com/6.0.1/installation/install_container.html)
