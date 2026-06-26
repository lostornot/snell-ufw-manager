# Snell UFW Manager

集中管理多台 VPS 上 Snell 代理端口的 UFW 白名单规则，并提供跨节点批量防火墙规则下发与清理功能。

## 特性

- 🖥️ **多节点管理** — 一个面板集中管理所有落地/边缘 VPS 节点的防火墙状态。
- 📍 **地理位置解析** — 自动检测并缓存 VPS 公网 IP 的地理位置，并在界面展示精致的国旗 Emoji 及所属国家/地区。
- 🌐 **国家分组视图** — 仪表盘支持“全部节点”扁平网格和“按国家/地区分组”两种视图的无缝切换。
- 🏷️ **节点标签系统** — 支持为节点打标签（例如“中转机”、“落地机”），并在卡片与管理列表中高亮展示。
- ✏️ **内联信息编辑** — 节点详情页支持直接内联编辑主机名、IP、标签和备注，保存时自动在线重测并更新国旗。
- ⚡ **跨节点批量部署** — 详情页右侧控制面板支持同时多选被控节点，一键批量放行或清理删除指定端口的 IP/IP分组白名单。
- 🛡️ **安全幂等防重** — 批量配置前自动拉取各目标 VPS 的 UFW 规则进行比对，对已放行的规则执行免配置跳过，减少冗余 SSH 开销。
- 🔗 **IP 分组(中转组)** — 按组批量管理中转 IP，在向节点授权端口时作为“宏”一键放行组内所有 IP。
- 🛡️ **UFW 白名单** — 可视化管理防火墙规则，支持单个 IP 和 CIDR 网段。
- 👁️ **访问日志候选** — 实时读取节点安全日志，列出最近 24 小时访问/被拦截的候选 IP，支持一键直接放行或加入分组。
- 🔄 **自动备份** — 操作前自动备份 UFW 规则，支持一键查看与恢复备份。
- 🌓 **双主题** — 完备的亮色 (Light Theme) / 暗色 (Dark Theme) 视觉体系，适配系统偏好。
- 🔒 **零暴露** — 仅监听 `127.0.0.1`，通过 SSH 隧道安全访问，安全可靠。

## 架构

```
你的浏览器 → SSH Tunnel → 控制中心 VPS (127.0.0.1:8899)
                                ↓ SSH
                          落地节点 A (snell-fwctl)
                          落地节点 B (snell-fwctl)
                          落地节点 C (snell-fwctl)
```

- **控制中心**：FastAPI + Jinja2 + HTMX 2.x，轻量 SQLite 数据库，无刷局刷体验。
- **落地节点**：只部署一个受限 Bash 脚本 `snell-fwctl`，无需额外运行 Python 环境，不开任何额外管理端口。

## 快速开始

### 1. 部署控制中心

```bash
# 上传到控制中心 VPS
scp -r snell-ufw-manager/ root@控制中心VPS:/opt/

# SSH 到控制中心 VPS
ssh root@控制中心VPS

# 一键安装
bash /opt/snell-ufw-manager/controller/install.sh
```

### 2. 访问面板

```bash
# 本地终端建立安全隧道
ssh -L 8899:127.0.0.1:8899 root@控制中心VPS

# 浏览器打开
# http://localhost:8899
```

### 3. 添加节点

1. 在面板「节点管理」页第一步中点击「生成初始化脚本」。
2. 复制生成的初始化脚本命令行，在落地 VPS 上以 **root** 用户粘贴执行。
3. 在面板第二步或「手动添加节点」表单中输入落地 VPS 的公网 IP 等信息，系统会自动检测名称并完成对接。
4. 回到控制面板点击「测试连接」以确保通道正常。

### 4. 使用流程

1. **创建 IP 分组**：如「公司固定IP」「中转服务器组」。
2. **添加 IP**：往分组里添加中转机 IP 或 CIDR 网段。
3. **单节点配置**：进入节点详情页，在左侧直接对特定端口添加/删除来源 IP 放行规则。
4. **多节点批量部署**：在节点详情页右侧的「端口防火墙部署」面板，输入端口和 IP，勾选需要同步的多台 VPS，点击「确认批量放行部署」或「确认批量删除白名单」即可一次性更新多台机器的 UFW 规则。

## 技术栈

| 组件 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / Uvicorn |
| 前端 | Jinja2 + HTMX 2.0.4 |
| 样式 | 纯 CSS（亮色/暗色双主题，无 Tailwind 依赖） |
| 数据 | SQLite (aiosqlite) |
| SSH | asyncssh |
| 节点脚本 | Bash (snell-fwctl) |
| 进程管理 | systemd |

## 目录结构

```
snell-ufw-manager/
├── controller/          # 控制中心（部署在一台 VPS）
│   ├── app/
│   │   ├── main.py      # FastAPI 路由与核心逻辑
│   │   ├── config.py    # 配置文件解析
│   │   ├── database.py  # SQLite 数据库管理与 CRUD
│   │   ├── ssh_executor.py  # 远程 SSH 指令并行下发
│   │   ├── templates/   # Jinja2 HTML 模板
│   │   └── static/      # 静态资源 (style.css 等)
│   ├── config.yaml      # 配置文件
│   ├── requirements.txt
│   ├── install.sh       # 控制中心一键安装脚本
│   └── snell-ufw-manager.service
├── node/                # 节点侧脚本
│   ├── snell-fwctl      # UFW 防火墙受限管理脚本
│   └── setup-node.sh    # 落地节点一键初始化部署脚本
└── README.md
```

## 配置文件 (config.yaml)

```yaml
server:
  host: "127.0.0.1"    # 仅本地监听，保障安全
  port: 8899

ssh:
  private_key_path: "/root/.ssh/snellmgr_ed25519"  # 控制中心 SSH 密钥
  connect_timeout: 10
  command_timeout: 30

snell:
  default_conf_path: "/root/snelldocker/snell-conf/snell.conf"
```

## 安全设计

- **零端口暴露**：Web 控制中心仅监听 `127.0.0.1`，外界只能通过 SSH 安全隧道进行访问，阻断扫描器的嗅探。
- **权限最小化**：添加节点时自动创建系统受限用户 `snellmgr`，并在 sudoers 中限制其**仅能**免密运行 `/usr/local/sbin/snell-fwctl` 脚本，绝对禁止执行其他任意 Linux 系统命令。
- **SSH 来源限制**：节点初始化脚本会在 `.ssh/authorized_keys` 中加入 `from="<控制中心IP>"` 限制，防止密钥泄露时被其他 IP 恶意利用。
- **规则日志审计**：所有添加、删除、测试、同步等操作均详细记录到系统 SQLite 操作日志中，随时可溯源。

## License

MIT
