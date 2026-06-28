# Snell VPS Firewall Manager (v0.2 / nftables-only)

集中管理多台 VPS 上 Snell 代理服务及 SSH 的防火墙入站策略，提供基于 nftables 的原子化服务策略下发、安全防锁死自动回滚以及环境风险感知。

---

## 核心特性

- 🖥️ **多节点集中管理** — 一个控制面板，集中管理所有落地/边缘 VPS 节点的防火墙及策略状态。
- 🛡️ **基于 nftables 架构** — 被控节点采用原生 `nftables` 取代 UFW，利用 IP 集 (`set`) 实现匹配加速，无规则堆叠和性能损耗。
- 🔒 **SSH 防锁死回滚 (Lockout Guard)** — 策略下发时先以临时规则加载并启动 15 秒 rollback 自动恢复守护；控制中心随即探测 SSH，连通性验证正常则发出 confirm 锁定规则，超时则拒绝 confirm 以让节点安全回滚，彻底防止误配导致失联。
- 👁️ **环境感知与 Docker 风险警告** — 自动感知节点上的 Docker 和 Tailscale 状态。如果 Snell 端口在 Docker 桥接模式中映射发布（导致 Docker 自建 NAT 绕过宿主机防火墙限制），前台会高亮警示 Docker 网络风险。
- 🇨🇳 **中国段 IP 库集成** — 集成一键从可靠 CDN 拉取和更新中国区 IPv4 CIDR 网段到本地地址管理，方便为 Snell 端口一键开启/关闭备用直连。
- 🏷️ **统一 IP 地址标签化管理** — 取代原有繁琐的 IP 分组，升级为统一标签的 IP 管理；支持从节点被拦截日志中直接一键收录新客户端。
- 🔐 **安全最小化授权** — 节点侧自动创建系统受限用户 `snellmgr`，配置 sudoers 限制其仅能免密执行限制脚本；同时可通过 SSH `from=` 限制指定控制中心 IP 来源。
- 🌓 **高端暗色拟物主题** — 完备的半透明玻璃卡片 (`--bg-glass`) 双主题设计，亮色模式下依然保证极佳的字体与状态可读性。

---

## 系统架构

```
你的浏览器 → SSH Tunnel → 控制中心 VPS (127.0.0.1:8899)
                                ↓ SSH
                          落地节点 A (nft-fwctl)
                          落地节点 B (nft-fwctl)
                          落地节点 C (nft-fwctl)
```

- **控制中心**：Python 3.10+ / FastAPI + Jinja2 + HTMX 2.x，轻量 SQLite 数据库，无刷新交互。
- **被控节点**：仅部署一个受限 Bash 脚本 `nft-fwctl`，不额外常驻进程或开放管理端口。

---

## 快速开始

### 1. 部署控制中心

```bash
# 上传到控制中心 VPS
scp -r snell-vps-firewall-manager/ root@控制中心VPS:/opt/

# SSH 到控制中心 VPS
ssh root@控制中心VPS

# 一键安装
bash /opt/snell-vps-firewall-manager/controller/install.sh
```

### 2. 访问面板

```bash
# 本地终端建立安全隧道
ssh -L 8899:127.0.0.1:8899 root@控制中心VPS

# 浏览器打开
# http://localhost:8899
```

### 3. 被控节点添加

1. 在面板「节点管理」页中点击「生成初始化脚本」。
2. 复制脚本，在落地 VPS 节点上以 **root** 用户执行，自动创建 `snellmgr` 用户、部署受限 `/usr/local/sbin/nft-fwctl` 脚本并授权。
3. 在面板上输入节点公网 IP 完成对接并「测试连接」。

### 4. 推荐使用流程

1. **管理 IP 地址**：在「IP 地址管理」中添加你的常用客户端 IP（如中转机 IP 标记为 `relay_ips`，手机直连标记为 `direct_ips`）。
2. **拉取中国 IP 库**：在「IP 地址管理」页面点击 `更新中国 IP 库`，以拉取最新的中国大陆段 CIDR。
3. **下发策略**：进入特定节点的详情页，为 Snell 代理服务勾选 `relay_ips` 或是 `direct_ips`，并点击 `应用防火墙策略`。系统会自动秒级验证并持久化规则！

---

## 技术栈

| 组件 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / Uvicorn |
| 前端 | Jinja2 + HTMX 2.x |
| 样式 | 原生 CSS (Vanilla CSS，支持亮暗色切换) |
| 数据 | SQLite (aiosqlite) |
| SSH | asyncssh |
| 节点脚本 | Bash (nft-fwctl) |

---

## 目录结构

```
snell-vps-firewall-manager/
├── controller/          # 控制中心
│   ├── app/
│   │   ├── main.py      # FastAPI 路由与核心逻辑
│   │   ├── database.py  # SQLite 数据库管理与迁移
│   │   ├── ssh_executor.py  # 远程 SSH 策略握手下发
│   │   ├── templates/   # Jinja2 HTML 模板
│   │   └── static/      # 静态资源 (style.css 等)
│   ├── config.yaml      # 配置文件
│   ├── requirements.txt
│   └── install.sh       # 控制中心一键安装
├── node/                # 节点侧脚本
│   ├── nft-fwctl        # 基于 nftables 的防火墙受限管理脚本
│   └── setup-node.sh    # 落地节点一键初始化部署脚本
└── README.md
```

---

## 配置文件 (config.yaml)

```yaml
server:
  host: "127.0.0.1"    # 仅本地监听，保障安全
  port: 8899

ssh:
  private_key_path: "/root/.ssh/snellmgr_ed25519"  # 控制中心 SSH 私钥
  connect_timeout: 10
  command_timeout: 30

snell:
  default_conf_path: "/root/snelldocker/snell-conf/snell.conf"
```

---

## 开发与验证

项目包含完善的单元测试套件，在修改代码前可执行测试验证：

```bash
# 激活虚拟环境
source venv/bin/activate

# 运行测试
python3 -m pytest
```

---

## License

MIT
