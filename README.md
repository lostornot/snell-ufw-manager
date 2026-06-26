# Snell UFW Manager

集中管理多台 VPS 上 Snell 代理端口的 UFW 白名单规则。

## 特性

- 🖥️ **多节点管理** — 一个面板管理所有落地 VPS
- 🔗 **中转组** — 按组批量管理中转 IP，一键同步到多个节点
- 🛡️ **UFW 白名单** — 可视化管理防火墙规则，支持 IP 和 CIDR
- 👁️ **访问日志** — 查看谁在访问/被拦截，一键加入白名单
- 🔄 **自动备份** — 操作前自动备份 UFW 规则
- 🌓 **双主题** — 亮色 / 暗色主题切换
- 🔒 **零暴露** — 仅监听 127.0.0.1，通过 SSH 隧道访问

## 架构

```
你的浏览器 → SSH Tunnel → 控制中心 VPS (127.0.0.1:8899)
                                ↓ SSH
                          落地节点 A (snell-fwctl)
                          落地节点 B (snell-fwctl)
                          落地节点 C (snell-fwctl)
```

- **控制中心**：FastAPI + Jinja2 + HTMX，Web 面板 + 数据库
- **落地节点**：只部署一个 Bash 脚本 `snell-fwctl`，不开任何端口

## 快速开始

### 1. 部署控制中心

```bash
# 上传到 VPS
scp -r snell-ufw-manager/ root@控制中心VPS:/opt/

# SSH 到控制中心 VPS
ssh root@控制中心VPS

# 一键安装
bash /opt/snell-ufw-manager/controller/install.sh
```

### 2. 访问面板

```bash
# 本地终端
ssh -L 8899:127.0.0.1:8899 root@控制中心VPS

# 浏览器打开
# http://localhost:8899
```

### 3. 添加节点

1. 在面板「节点管理」页添加节点信息
2. 复制生成的初始化脚本
3. 在落地 VPS 上粘贴执行
4. 回面板点「测试连接」

### 4. 使用流程

1. **创建中转组**：如「JMS 荷兰」「搬瓦工 DC6」
2. **添加 IP**：往中转组里添加中转机 IP/CIDR
3. **关联节点**：在节点详情页勾选要应用的中转组
4. **同步**：点「同步到节点」，控制中心通过 SSH 更新 UFW 规则
5. **查看日志**：在节点详情页查看访问日志，被拦截的 IP 可一键加入

## 技术栈

| 组件 | 技术 |
|---|---|
| 后端 | Python 3.10+ / FastAPI / Uvicorn |
| 前端 | Jinja2 + HTMX 2.x |
| 样式 | 纯 CSS（亮色/暗色双主题） |
| 数据 | SQLite |
| SSH | asyncssh |
| 节点脚本 | Bash (snell-fwctl) |
| 进程管理 | systemd |

## 目录结构

```
snell-ufw-manager/
├── controller/          # 控制中心（部署在一台 VPS）
│   ├── app/
│   │   ├── main.py      # FastAPI 路由
│   │   ├── config.py    # 配置管理
│   │   ├── database.py  # SQLite CRUD
│   │   ├── ssh_executor.py  # SSH 远程执行
│   │   ├── templates/   # Jinja2 模板
│   │   └── static/      # CSS
│   ├── config.yaml      # 配置文件
│   ├── requirements.txt
│   ├── install.sh       # 安装脚本
│   └── snell-ufw-manager.service
├── node/                # 节点侧脚本
│   ├── snell-fwctl      # UFW 管理脚本
│   └── setup-node.sh    # 节点初始化脚本
└── README.md
```

## 配置

编辑 `controller/config.yaml`：

```yaml
server:
  host: "127.0.0.1"    # 仅本地监听
  port: 8899

ssh:
  private_key_path: "/root/.ssh/snellmgr_ed25519"
  connect_timeout: 10
  command_timeout: 30

snell:
  default_conf_path: "/root/snelldocker/snell-conf/snell.conf"
```

## 安全设计

- 面板仅监听 `127.0.0.1`，必须通过 SSH 隧道访问
- 节点创建专用 `snellmgr` 用户，仅能执行 `snell-fwctl`
- SSH 密钥可限制来源 IP（`from=` 指令）
- `snell-fwctl` 严格校验所有输入，不执行任意命令
- 所有操作记录到数据库

## License

MIT
