"""FastAPI application — routes and HTMX endpoints for Snell UFW Manager."""

import ipaddress
import logging
import re
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database as db
from .config import load_config
from .ssh_executor import SSHExecutor

logger = logging.getLogger(__name__)
config = load_config()
ssh = SSHExecutor(config)

APP_DIR = Path(__file__).parent
TEMPLATE_DIR = APP_DIR / "templates"
STATIC_DIR = APP_DIR / "static"
NODE_DIR = Path(__file__).parent.parent.parent / "node"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_IP_CIDR_RE = re.compile(
    r"^(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})(/\d{1,2})?$"
)


def validate_ip_cidr(value: str) -> bool:
    """Validate an IPv4 address or CIDR notation."""
    value = value.strip()
    try:
        if "/" in value:
            ipaddress.IPv4Network(value, strict=False)
        else:
            ipaddress.IPv4Address(value)
        return True
    except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
        return False


def _relative_time(dt_str: str | None) -> str:
    """Convert a datetime string to a human-readable relative time."""
    if not dt_str:
        return ""
    from datetime import datetime, timezone

    try:
        # Try ISO format first
        dt = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return dt_str

    now = datetime.now(timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())

    if seconds < 60:
        return f"{seconds} 秒前"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    return f"{seconds // 86400} 天前"


# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.init_db()
    yield


app = FastAPI(title="Snell UFW Manager", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals["relative_time"] = _relative_time


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard: all node cards + recent operations."""
    nodes = await db.get_all_nodes()
    logs = await db.get_op_logs(limit=10)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "nodes": nodes, "logs": logs},
    )


@app.get("/nodes/manage", response_class=HTMLResponse)
async def nodes_manage(request: Request):
    """Node management page: add / edit / delete nodes."""
    nodes = await db.get_all_nodes()
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    return templates.TemplateResponse(
        "nodes_manage.html",
        {
            "request": request,
            "nodes": nodes,
            "pubkey": pubkey,
            "ctrl_ip": ctrl_ip,
            "default_snell_conf": config.snell.default_conf_path,
        },
    )


@app.get("/nodes/{node_id}", response_class=HTMLResponse)
async def node_detail(request: Request, node_id: int):
    """Node detail page: whitelist, access log, relay groups, op log."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    all_groups = await db.get_all_relay_groups()
    node_group_ids = await db.get_node_relay_group_ids(node_id)
    allowed_ips = await db.get_node_allowed_ips(node_id)
    logs = await db.get_op_logs(node_id=node_id, limit=20)
    return templates.TemplateResponse(
        "node_detail.html",
        {
            "request": request,
            "node": node,
            "all_groups": all_groups,
            "node_group_ids": node_group_ids,
            "allowed_ips": allowed_ips,
            "logs": logs,
            "access_log_hours": config.log.access_log_hours,
        },
    )


@app.get("/relay-groups", response_class=HTMLResponse)
async def relay_groups_page(request: Request):
    """Relay group management page."""
    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "relay_groups.html",
        {"request": request, "groups": groups},
    )


@app.get("/logs", response_class=HTMLResponse)
async def logs_page(request: Request):
    """Global operation logs page."""
    logs = await db.get_op_logs(limit=100)
    return templates.TemplateResponse(
        "logs.html",
        {"request": request, "logs": logs},
    )


# ---------------------------------------------------------------------------
# HTMX Partials
# ---------------------------------------------------------------------------


@app.get("/partials/nodes/{node_id}/whitelist", response_class=HTMLResponse)
async def partial_whitelist(request: Request, node_id: int):
    """Fetch live whitelist from node via SSH."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
    result = await ssh.get_whitelist(node)
    allowed_ips = await db.get_node_allowed_ips(node_id)
    allowed_set = {ip["ip_cidr"] for ip in allowed_ips}
    return templates.TemplateResponse(
        "partials/whitelist.html",
        {
            "request": request,
            "node": node,
            "result": result,
            "allowed_set": allowed_set,
            "allowed_ips": allowed_ips,
        },
    )


@app.get("/partials/nodes/{node_id}/access-log", response_class=HTMLResponse)
async def partial_access_log(request: Request, node_id: int, hours: int = 24):
    """Fetch recent access log from node via SSH."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
    result = await ssh.get_candidates(node, hours)
    allowed_ips = await db.get_node_allowed_ips(node_id)
    allowed_set = {ip["ip_cidr"] for ip in allowed_ips}
    all_groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/access_log.html",
        {
            "request": request,
            "node": node,
            "result": result,
            "allowed_set": allowed_set,
            "all_groups": all_groups,
        },
    )


@app.get("/partials/nodes/{node_id}/op-log", response_class=HTMLResponse)
async def partial_op_log(request: Request, node_id: int):
    logs = await db.get_op_logs(node_id=node_id, limit=20)
    return templates.TemplateResponse(
        "partials/op_log.html",
        {"request": request, "logs": logs},
    )


@app.get("/partials/relay-groups", response_class=HTMLResponse)
async def partial_relay_groups(request: Request):
    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {"request": request, "groups": groups},
    )


# ---------------------------------------------------------------------------
# API: Nodes
# ---------------------------------------------------------------------------


@app.post("/api/nodes", response_class=HTMLResponse)
async def api_create_node(
    request: Request,
    name: str = Form(...),
    host: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form("snellmgr"),
    snell_port: int = Form(...),
    snell_conf: str = Form("/root/snelldocker/snell-conf/snell.conf"),
    remark: str = Form(""),
):
    """Create a new node."""
    node_id = await db.create_node(
        name=name,
        host=host,
        ssh_port=ssh_port,
        ssh_user=ssh_user,
        snell_port=snell_port,
        snell_conf=snell_conf,
        remark=remark,
    )
    await db.add_op_log(node_id, name, "ADD_NODE", host, f"Port {snell_port}")
    # Return updated node list
    nodes = await db.get_all_nodes()
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    return templates.TemplateResponse(
        "partials/node_manage_list.html",
        {
            "request": request,
            "nodes": nodes,
            "pubkey": pubkey,
            "ctrl_ip": ctrl_ip,
            "default_snell_conf": config.snell.default_conf_path,
            "toast": {"type": "success", "message": f"节点 {name} 已添加"},
            "new_node_id": node_id,
        },
    )


@app.put("/api/nodes/{node_id}", response_class=HTMLResponse)
async def api_update_node(
    request: Request,
    node_id: int,
    name: str = Form(...),
    host: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form("snellmgr"),
    snell_port: int = Form(...),
    snell_conf: str = Form(""),
    remark: str = Form(""),
):
    """Update an existing node."""
    await db.update_node(
        node_id,
        name=name,
        host=host,
        ssh_port=ssh_port,
        ssh_user=ssh_user,
        snell_port=snell_port,
        snell_conf=snell_conf,
        remark=remark,
    )
    nodes = await db.get_all_nodes()
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    return templates.TemplateResponse(
        "partials/node_manage_list.html",
        {
            "request": request,
            "nodes": nodes,
            "pubkey": pubkey,
            "ctrl_ip": ctrl_ip,
            "default_snell_conf": config.snell.default_conf_path,
            "toast": {"type": "success", "message": f"节点 {name} 已更新"},
        },
    )


@app.delete("/api/nodes/{node_id}", response_class=HTMLResponse)
async def api_delete_node(request: Request, node_id: int):
    """Delete a node."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
    await db.delete_node(node_id)
    await db.add_op_log(node_id, node["name"], "DELETE_NODE", node["host"])
    nodes = await db.get_all_nodes()
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    return templates.TemplateResponse(
        "partials/node_manage_list.html",
        {
            "request": request,
            "nodes": nodes,
            "pubkey": pubkey,
            "ctrl_ip": ctrl_ip,
            "default_snell_conf": config.snell.default_conf_path,
            "toast": {"type": "success", "message": f"节点 {node['name']} 已删除"},
        },
    )


@app.post("/api/nodes/{node_id}/test", response_class=HTMLResponse)
async def api_test_node(request: Request, node_id: int):
    """Test SSH connection to a node."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
    result = await ssh.test_connection(node)
    toast_type = "success" if result.get("ok") else "error"
    if result.get("ok"):
        msg = f"✅ {node['name']} 连接成功 — {result.get('hostname', '')} / UFW {result.get('ufw_status', 'unknown')}"
    else:
        msg = f"❌ {node['name']} 连接失败 — {result.get('error', 'unknown error')}"
    return templates.TemplateResponse(
        "partials/toast.html",
        {"request": request, "toast": {"type": toast_type, "message": msg}},
    )


@app.post("/api/nodes/{node_id}/sync", response_class=HTMLResponse)
async def api_sync_node(request: Request, node_id: int):
    """Sync whitelist: push all allowed IPs (from relay groups) to the node."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    allowed = await db.get_node_allowed_ips(node_id)
    ip_list = list({ip["ip_cidr"] for ip in allowed})

    result = await ssh.sync_whitelist(node, ip_list)

    if result.get("ok"):
        msg = f"✅ {node['name']} 同步成功 — {len(ip_list)} 个 IP, {result.get('rules_added', 0)} 条规则"
        await db.add_op_log(
            node_id, node["name"], "SYNC",
            f"{len(ip_list)} IPs",
            f"Rules added: {result.get('rules_added', 0)}",
        )
    else:
        msg = f"❌ {node['name']} 同步失败 — {result.get('error', '')}"
        await db.add_op_log(
            node_id, node["name"], "SYNC",
            f"{len(ip_list)} IPs",
            result.get("error", ""),
            success=False,
        )

    return templates.TemplateResponse(
        "partials/toast.html",
        {"request": request, "toast": {"type": "success" if result.get("ok") else "error", "message": msg}},
    )


# ---------------------------------------------------------------------------
# API: Relay Groups
# ---------------------------------------------------------------------------


@app.post("/api/relay-groups", response_class=HTMLResponse)
async def api_create_relay_group(
    request: Request,
    name: str = Form(...),
    remark: str = Form(""),
):
    """Create a new relay group."""
    await db.create_relay_group(name, remark)
    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {
            "request": request,
            "groups": groups,
            "toast": {"type": "success", "message": f"中转组 {name} 已创建"},
        },
    )


@app.put("/api/relay-groups/{group_id}", response_class=HTMLResponse)
async def api_update_relay_group(
    request: Request,
    group_id: int,
    name: str = Form(...),
    remark: str = Form(""),
):
    """Update relay group name/remark."""
    await db.update_relay_group(group_id, name=name, remark=remark)
    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {
            "request": request,
            "groups": groups,
            "toast": {"type": "success", "message": f"中转组 {name} 已更新"},
        },
    )


@app.delete("/api/relay-groups/{group_id}", response_class=HTMLResponse)
async def api_delete_relay_group(request: Request, group_id: int):
    """Delete a relay group."""
    group = await db.get_relay_group(group_id)
    if not group:
        raise HTTPException(status_code=404)
    await db.delete_relay_group(group_id)
    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {
            "request": request,
            "groups": groups,
            "toast": {"type": "success", "message": f"中转组 {group['name']} 已删除"},
        },
    )


@app.post("/api/relay-groups/{group_id}/ips", response_class=HTMLResponse)
async def api_add_relay_ip(
    request: Request,
    group_id: int,
    ip_cidr: str = Form(...),
    note: str = Form(""),
):
    """Add an IP/CIDR to a relay group."""
    ip_cidr = ip_cidr.strip()
    if not validate_ip_cidr(ip_cidr):
        groups = await db.get_all_relay_groups()
        return templates.TemplateResponse(
            "partials/relay_group_list.html",
            {
                "request": request,
                "groups": groups,
                "toast": {"type": "error", "message": f"无效的 IP/CIDR: {ip_cidr}"},
            },
        )
    try:
        await db.add_relay_ip(group_id, ip_cidr, note)
    except Exception as exc:
        if "UNIQUE" in str(exc):
            groups = await db.get_all_relay_groups()
            return templates.TemplateResponse(
                "partials/relay_group_list.html",
                {
                    "request": request,
                    "groups": groups,
                    "toast": {"type": "error", "message": f"IP {ip_cidr} 已存在于该组"},
                },
            )
        raise

    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {
            "request": request,
            "groups": groups,
            "toast": {"type": "success", "message": f"已添加 {ip_cidr}"},
        },
    )


@app.delete("/api/relay-groups/{group_id}/ips/{ip_id}", response_class=HTMLResponse)
async def api_delete_relay_ip(request: Request, group_id: int, ip_id: int):
    """Delete an IP from a relay group."""
    await db.delete_relay_ip(ip_id)
    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {
            "request": request,
            "groups": groups,
            "toast": {"type": "success", "message": "IP 已删除"},
        },
    )


# ---------------------------------------------------------------------------
# API: Node ↔ Relay Group Associations
# ---------------------------------------------------------------------------


@app.put("/api/nodes/{node_id}/relay-groups", response_class=HTMLResponse)
async def api_set_node_relay_groups(request: Request, node_id: int):
    """Update relay groups associated with a node (from checkbox form)."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    form = await request.form()
    group_ids = [int(v) for k, v in form.multi_items() if k == "group_ids"]

    await db.set_node_relay_groups(node_id, group_ids)
    await db.add_op_log(
        node_id, node["name"], "UPDATE_GROUPS",
        f"{len(group_ids)} groups",
    )

    return templates.TemplateResponse(
        "partials/toast.html",
        {
            "request": request,
            "toast": {"type": "success", "message": f"已关联 {len(group_ids)} 个中转组，请点击「同步到节点」生效"},
        },
    )


# ---------------------------------------------------------------------------
# API: Quick-add (from access log candidate to relay group)
# ---------------------------------------------------------------------------


@app.post("/api/nodes/{node_id}/quick-add", response_class=HTMLResponse)
async def api_quick_add(
    request: Request,
    node_id: int,
    ip_cidr: str = Form(...),
    group_id: int = Form(...),
):
    """Quick-add a candidate IP to a relay group."""
    ip_cidr = ip_cidr.strip()
    if not validate_ip_cidr(ip_cidr):
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": f"无效 IP: {ip_cidr}"}},
        )

    group = await db.get_relay_group(group_id)
    if not group:
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": "中转组不存在"}},
        )

    try:
        await db.add_relay_ip(group_id, ip_cidr, "")
    except Exception as exc:
        if "UNIQUE" in str(exc):
            return templates.TemplateResponse(
                "partials/toast.html",
                {"request": request, "toast": {"type": "warning", "message": f"{ip_cidr} 已在组 {group['name']} 中"}},
            )
        raise

    node = await db.get_node(node_id)
    await db.add_op_log(
        node_id, node["name"] if node else "unknown", "QUICK_ADD",
        ip_cidr, f"Added to group: {group['name']}",
    )

    return templates.TemplateResponse(
        "partials/toast.html",
        {
            "request": request,
            "toast": {
                "type": "success",
                "message": f"已将 {ip_cidr} 加入 {group['name']}，请同步到节点生效",
            },
        },
    )


# ---------------------------------------------------------------------------
# API: Sync relay group to all associated nodes
# ---------------------------------------------------------------------------


@app.post("/api/relay-groups/{group_id}/sync", response_class=HTMLResponse)
async def api_sync_relay_group(request: Request, group_id: int):
    """Sync a relay group's IPs to all associated nodes."""
    group = await db.get_relay_group(group_id)
    if not group:
        raise HTTPException(status_code=404)

    results = []
    for node_ref in group["nodes"]:
        node = await db.get_node(node_ref["id"])
        if not node:
            continue
        allowed = await db.get_node_allowed_ips(node["id"])
        ip_list = list({ip["ip_cidr"] for ip in allowed})
        result = await ssh.sync_whitelist(node, ip_list)
        ok = result.get("ok", False)
        results.append({"node": node["name"], "ok": ok, "detail": result})
        await db.add_op_log(
            node["id"], node["name"], "SYNC",
            f"via group {group['name']}",
            f"IPs: {len(ip_list)}, Rules: {result.get('rules_added', '?')}",
            success=ok,
        )

    success_count = sum(1 for r in results if r["ok"])
    total = len(results)
    msg = f"同步完成: {success_count}/{total} 个节点成功"

    groups = await db.get_all_relay_groups()
    return templates.TemplateResponse(
        "partials/relay_group_list.html",
        {
            "request": request,
            "groups": groups,
            "toast": {"type": "success" if success_count == total else "warning", "message": msg},
        },
    )


# ---------------------------------------------------------------------------
# API: Auto-discover node
# ---------------------------------------------------------------------------


@app.post("/api/nodes/discover", response_class=HTMLResponse)
async def api_discover_node(
    request: Request,
    host: str = Form(...),
    ssh_port: int = Form(22),
    snell_port: int | None = Form(None),
):
    """Auto-discover a node: SSH in, detect hostname + snell port (if not specified), create node."""
    node_stub = {
        "host": host.strip(),
        "ssh_port": ssh_port,
        "ssh_user": "snellmgr",
        "snell_port": snell_port or 0,
    }

    # Test SSH connection
    status = await ssh.test_connection(node_stub)
    if not status.get("ok"):
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": f"❌ SSH 连接失败: {status.get('error', 'unknown')}"}},
        )

    # Use the provided port or auto-detect it
    if snell_port is not None and snell_port > 0:
        final_snell_port = snell_port
    else:
        node_stub["snell_conf"] = config.snell.default_conf_path
        port_result = await ssh.get_snell_port(node_stub)
        final_snell_port = port_result.get("port", 28261) if port_result.get("ok") else 28261

    hostname = status.get("hostname", host.strip())

    # Create node
    node_id = await db.create_node(
        name=hostname,
        host=host.strip(),
        ssh_port=ssh_port,
        ssh_user="snellmgr",
        snell_port=final_snell_port,
        snell_conf=config.snell.default_conf_path,
    )
    await db.add_op_log(node_id, hostname, "DISCOVER", host.strip(), f"Auto: port={final_snell_port}")

    nodes = await db.get_all_nodes()
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    return templates.TemplateResponse(
        "partials/node_manage_list.html",
        {
            "request": request,
            "nodes": nodes,
            "pubkey": pubkey,
            "ctrl_ip": ctrl_ip,
            "default_snell_conf": config.snell.default_conf_path,
            "toast": {"type": "success", "message": f"✅ 已发现并添加: {hostname} (Snell:{final_snell_port})"},
        },
    )


@app.get("/partials/nodes/{node_id}/row", response_class=HTMLResponse)
async def partial_node_row(request: Request, node_id: int):
    """Return the normal table row for a node."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return templates.TemplateResponse(
        "partials/node_row.html",
        {"request": request, "node": node},
    )


@app.get("/partials/nodes/{node_id}/edit", response_class=HTMLResponse)
async def partial_node_edit(request: Request, node_id: int):
    """Return the edit table row for a node."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return templates.TemplateResponse(
        "partials/node_edit_row.html",
        {"request": request, "node": node},
    )



# ---------------------------------------------------------------------------
# API: Setup script generation
# ---------------------------------------------------------------------------


@app.get("/api/nodes/setup-script", response_class=PlainTextResponse)
async def api_setup_script():
    """Generate the node setup script with embedded SSH key and controller IP."""
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()

    # Read snell-fwctl script content
    fwctl_path = NODE_DIR / "snell-fwctl"
    try:
        fwctl_content = fwctl_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fwctl_content = "#!/bin/bash\necho '{\"ok\":false,\"error\":\"snell-fwctl not deployed\"}'"

    script = f"""#!/bin/bash
# Snell UFW Manager — Node Setup Script
# Generated by controller. Run as root on the target node.

set -euo pipefail

PUBKEY='{pubkey}'
CTRL_IP='{ctrl_ip}'

echo "══════════════════════════════════════════"
echo " Snell UFW Manager — 节点初始化"
echo "══════════════════════════════════════════"

# 1. Create snellmgr user
echo -n "  创建 snellmgr 用户... "
if id snellmgr &>/dev/null; then
    echo "已存在 ✓"
else
    useradd -r -m -s /bin/bash snellmgr
    echo "完成 ✓"
fi

# 2. Deploy snell-fwctl
echo -n "  部署 snell-fwctl... "
cat > /usr/local/sbin/snell-fwctl << 'SNELL_FWCTL_EOF'
{fwctl_content}
SNELL_FWCTL_EOF
chmod 755 /usr/local/sbin/snell-fwctl
chown root:root /usr/local/sbin/snell-fwctl
echo "完成 ✓"

# 3. Configure sudoers
echo -n "  配置 sudoers... "
echo 'snellmgr ALL=(root) NOPASSWD: /usr/local/sbin/snell-fwctl' \\
    > /etc/sudoers.d/snellmgr
chmod 440 /etc/sudoers.d/snellmgr
echo "完成 ✓"

# 4. Deploy SSH key
echo -n "  部署 SSH 公钥... "
mkdir -p /home/snellmgr/.ssh
if [ -n "$CTRL_IP" ] && [ "$CTRL_IP" != "<控制中心IP>" ]; then
    echo "from=\\"$CTRL_IP\\" $PUBKEY" > /home/snellmgr/.ssh/authorized_keys
else
    echo "$PUBKEY" > /home/snellmgr/.ssh/authorized_keys
fi
chmod 700 /home/snellmgr/.ssh
chmod 600 /home/snellmgr/.ssh/authorized_keys
chown -R snellmgr:snellmgr /home/snellmgr/.ssh
echo "完成 ✓"

# 5. Create backup directory
echo -n "  创建备份目录... "
mkdir -p /opt/snell-fwctl/backups
chown -R snellmgr:snellmgr /opt/snell-fwctl
echo "完成 ✓"

# 6. Enable UFW logging
echo -n "  启用 UFW 日志... "
ufw logging on 2>/dev/null || true
echo "完成 ✓"

# 7. Test
echo -n "  测试 snell-fwctl... "
RESULT=$(sudo -u snellmgr sudo /usr/local/sbin/snell-fwctl status 2>&1)
if echo "$RESULT" | grep -q '"ok":true'; then
    echo "通过 ✓"
else
    echo "失败 ✗"
    echo "  输出: $RESULT"
fi

echo ""
echo "══════════════════════════════════════════"
echo " ✅ 节点初始化完成"
echo " 请回到控制面板，输入本机 IP 点击「发现并添加」"
echo "══════════════════════════════════════════"
"""
    return script


@app.get("/partials/setup-script", response_class=HTMLResponse)
async def partial_setup_script(request: Request):
    """Return the setup script in a copyable HTML code block."""
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    fwctl_path = NODE_DIR / "snell-fwctl"
    try:
        fwctl_content = fwctl_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fwctl_content = "# snell-fwctl not found"

    return templates.TemplateResponse(
        "partials/setup_script.html",
        {"request": request, "pubkey": pubkey, "ctrl_ip": ctrl_ip, "fwctl_content": fwctl_content},
    )


# ---------------------------------------------------------------------------
# Entry point (for uvicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )
