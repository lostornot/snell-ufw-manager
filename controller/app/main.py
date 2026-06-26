import ipaddress
import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path
import urllib.request
import json
import asyncio
from datetime import datetime, timedelta, timezone

from fastapi import FastAPI, Form, HTTPException, Request
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
# Geolocation & Regional Flags Helpers
# ---------------------------------------------------------------------------

def _sync_get_ip_country(host: str) -> tuple[str, str]:
    """Blocking sync call to ip-api using urllib."""
    url = f"http://ip-api.com/json/{host}"
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0'}
        )
        with urllib.request.urlopen(req, timeout=3.0) as response:
            if response.status == 200:
                data = json.loads(response.read().decode('utf-8'))
                if data.get("status") == "success":
                    return data.get("country", "未知地区"), data.get("countryCode", "XX")
    except Exception:
        pass
    return "未知地区", "XX"


async def get_ip_country(host: str) -> tuple[str, str]:
    """Resolve IP or domain to country and country_code."""
    h = host.strip()
    # Check for private or loopback IP
    if h in ("localhost", "127.0.0.1", "::1") or h.startswith("192.168.") or h.startswith("10.") or h.startswith("172.16."):
        return "本地回环", "CN"
    try:
        return await asyncio.to_thread(_sync_get_ip_country, h)
    except Exception:
        return "未知地区", "XX"


def get_flag_emoji(country_code: str) -> str:
    """Translate 2-letter country code to flag emoji using regional indicator symbols."""
    if not country_code or country_code == "XX":
        return "🌐"
    try:
        return "".join(chr(127397 + ord(c)) for c in country_code.upper())
    except Exception:
        return "🌐"


def convert_to_taiwan_time(ts_str: str, tz_offset_str: str) -> str:
    """
    Convert naive ISO-ish timestamp string (from VPS log) and its tz_offset
    to Taiwan time (Asia/Taipei, UTC+8).
    """
    if not ts_str:
        return ""
    try:
        if len(tz_offset_str) != 5:
            return ts_str.replace("T", " ")
        sign = 1 if tz_offset_str[0] == '+' else -1
        hours = int(tz_offset_str[1:3])
        minutes = int(tz_offset_str[3:5])
        
        vps_tz = timezone(timedelta(hours=sign * hours, minutes=sign * minutes))
        naive_dt = datetime.fromisoformat(ts_str)
        vps_dt = naive_dt.replace(tzinfo=vps_tz)
        
        tw_tz = timezone(timedelta(hours=8))
        tw_dt = vps_dt.astimezone(tw_tz)
        return tw_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return ts_str.replace("T", " ")




# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def validate_ip_cidr(value: str) -> bool:
    """Validate an IPv4 address, CIDR notation, or anywhere keywords."""
    value = value.strip().lower()
    if value in ("any", "anywhere", "all"):
        return True
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


app = FastAPI(title="VPS UFW Firewall Manager", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

templates = Jinja2Templates(directory=str(TEMPLATE_DIR))
templates.env.globals["relative_time"] = _relative_time
templates.env.globals["get_flag_emoji"] = get_flag_emoji



# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Main dashboard: all node cards grouped by region + recent operations."""
    nodes = await db.get_all_nodes()
    
    # Resolve missing regions for existing nodes on the fly
    updated_any = False
    for node in nodes:
        if not node.get("country") or node.get("country") == "未知" or node.get("country") == "未知地区" or not node.get("country_code"):
            country, country_code = await get_ip_country(node["host"])
            if country != "未知地区" or country_code != "XX":
                await db.update_node(node["id"], country=country, country_code=country_code)
                node["country"] = country
                node["country_code"] = country_code
                updated_any = True
                
    if updated_any:
        nodes = await db.get_all_nodes()
        
    # Group nodes by country
    from collections import defaultdict
    grouped = defaultdict(list)
    for node in nodes:
        c = node.get("country") or "未知地区"
        cc = node.get("country_code") or "XX"
        flag = get_flag_emoji(cc)
        grouped[(c, cc, flag)].append(node)
        
    # Sort groups: put "未知地区" at the end, others alphabetically
    sorted_groups = sorted(
        grouped.items(),
        key=lambda x: (x[0][0] == "未知地区" or x[0][0] == "", x[0][0])
    )
    
    logs = await db.get_op_logs(limit=10)
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "sorted_groups": sorted_groups, "logs": logs},
    )



@app.get("/ip-groups", response_class=HTMLResponse)
async def ip_groups_page(request: Request):
    """IP groups library management page."""
    groups = await db.get_all_ip_groups()
    return templates.TemplateResponse(
        "ip_groups.html",
        {"request": request, "groups": groups},
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
    """Node detail page: contains Port Cards Grid and sticky sidebar form."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
        
    # Resolve country if missing
    if not node.get("country") or node.get("country") == "未知" or node.get("country") == "未知地区" or not node.get("country_code"):
        country, country_code = await get_ip_country(node["host"])
        if country != "未知地区" or country_code != "XX":
            await db.update_node(node["id"], country=country, country_code=country_code)
            node["country"] = country
            node["country_code"] = country_code
            
    ip_groups = await db.get_all_ip_groups()
    return templates.TemplateResponse(
        "node_detail.html",
        {
            "request": request,
            "node": node,
            "ip_groups": ip_groups,
            "access_log_hours": config.log.access_log_hours,
        },
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
# API: Node Summary & Ping (Dashboard Async Loading)
# ---------------------------------------------------------------------------

@app.get("/api/nodes/{node_id}/summary", response_class=HTMLResponse)
async def api_node_summary(request: Request, node_id: int):
    """SSH query node status and list ports, return card summary."""
    node = await db.get_node(node_id)
    if not node:
        return f'<div class="glass-card">节点不存在 ({node_id})</div>'

    result = await ssh.test_connection(node)
    if result.get("ok"):
        # Fetch UFW rules to count active ports
        wl_result = await ssh.get_whitelist(node)
        ports = []
        if wl_result.get("ok"):
            unique_ports = set()
            for r in wl_result.get("rules", []):
                unique_ports.add(r.get("port"))
            ports = sorted(list(unique_ports))
        
        status = {
            "online": True,
            "ufw_status": result.get("ufw_status", "unknown"),
            "uptime": result.get("uptime", "unknown"),
            "kernel": result.get("kernel", "unknown"),
            "ports": ports
        }
    else:
        status = {
            "online": False,
            "error": result.get("error", "SSH 连接失败")
        }

    return templates.TemplateResponse(
        "partials/node_summary.html",
        {"request": request, "node": node, "status": status},
    )


@app.post("/api/nodes/{node_id}/test", response_class=HTMLResponse)
async def api_test_node(request: Request, node_id: int):
    """Test SSH connection to a node and return toast."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
    result = await ssh.test_connection(node)
    toast_type = "success" if result.get("ok") else "error"
    if result.get("ok"):
        msg = f"✅ {node['name']} 连接成功 — Hostname: {result.get('hostname', '')} / UFW: {result.get('ufw_status', 'unknown')}"
    else:
        msg = f"❌ {node['name']} 连接失败 — {result.get('error', 'unknown error')}"
    return templates.TemplateResponse(
        "partials/toast.html",
        {"request": request, "toast": {"type": toast_type, "message": msg}},
    )


@app.get("/api/nodes/{node_id}/ping", response_class=HTMLResponse)
async def api_ping_node(request: Request, node_id: int):
    """Simple ping indicator (returns active dot)."""
    node = await db.get_node(node_id)
    if not node:
        return '<span class="status-dot offline" title="节点未找到"></span>'
    result = await ssh.test_connection(node)
    if result.get("ok"):
        return f'<span class="status-dot online" title="在线: {result.get("hostname", "")} (UFW {result.get("ufw_status", "")})"></span>'
    else:
        return f'<span class="status-dot offline" title="离线: {result.get("error", "unknown error")}"></span>'


# ---------------------------------------------------------------------------
# API: UFW Service Ports Cards Grid (所见即所得)
# ---------------------------------------------------------------------------

@app.get("/api/nodes/{node_id}/ports", response_class=HTMLResponse)
async def api_port_cards_grid(request: Request, node_id: int):
    """Fetch live rules from VPS and construct the Port Cards Grid."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    wl_result = await ssh.get_whitelist(node)
    if not wl_result.get("ok"):
        return f'<div class="empty-state" style="color:var(--accent-red); font-weight:600; padding:24px;">❌ 获取防火墙规则失败: {wl_result.get("error")}</div>'

    rules = wl_result.get("rules", [])
    
    # Group rules by port number
    port_data = {}
    for r in rules:
        port = str(r.get("port"))
        proto = r.get("proto", "all")
        
        if port not in port_data:
            port_data[port] = {
                "port": port,
                "protocol_label": proto,
                "rules": []
            }
        
        if r.get("ip"):
            port_data[port]["rules"].append(r)

    # Standardize protocol labels
    for p, p_info in port_data.items():
        protos = {r["proto"] for r in p_info["rules"]}
        if "tcp" in protos and "udp" in protos:
            p_info["protocol_label"] = "tcp+udp"
        elif "tcp" in protos:
            p_info["protocol_label"] = "tcp"
        elif "udp" in protos:
            p_info["protocol_label"] = "udp"
        else:
            p_info["protocol_label"] = "all"

    return templates.TemplateResponse(
        "partials/port_cards_grid.html",
        {"request": request, "node": node, "port_data": port_data},
    )


@app.post("/api/nodes/{node_id}/ports", response_class=HTMLResponse)
async def api_open_port(
    request: Request,
    node_id: int,
    port: int = Form(...),
    protocol: str = Form("both"),
    tag: str = Form("Custom Rule"),
    initial_ip: str = Form(""),
    initial_ip_group_id: str = Form(""),
):
    """Open a UFW service port and return updated Port Cards Grid."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="Invalid port number")

    parsed_group_id = None
    if initial_ip_group_id.strip():
        try:
            parsed_group_id = int(initial_ip_group_id)
        except ValueError:
            pass

    success = True
    added_targets = []
    error_msg = ""

    # Determine whitelist targets
    targets = []
    if initial_ip and initial_ip.strip():
        targets.append((initial_ip.strip(), "Initial IP"))
    elif parsed_group_id:
        group = await db.get_ip_group(parsed_group_id)
        if group:
            for item in group.get("ips", []):
                targets.append((item["ip_cidr"], f"Group: {group['name']}"))
    else:
        # Default: open to Anywhere
        targets.append(("anywhere", "Public Access"))

    # Execute on remote node via SSH
    for ip, desc in targets:
        if not validate_ip_cidr(ip):
            success = False
            error_msg = f"无效的 IP/CIDR 地址: {ip}"
            break
        
        result = await ssh.run(node, f"add {ip} {port} {protocol}")
        if not result.get("ok"):
            success = False
            error_msg = result.get("error", "添加规则失败")
            break
        added_targets.append(ip)

    # Log operation
    log_detail = f"开通端口 {port}/{protocol} ({tag}). 授权: {', '.join(added_targets) if added_targets else 'Anywhere'}"
    if not success:
        log_detail += f" (失败: {error_msg})"
    await db.add_op_log(node_id, node["name"], "OPEN_PORT", f"{port}", log_detail, success)

    # Fetch updated grid
    toast = None
    if not success:
        toast = {"type": "error", "message": f"❌ 开通端口失败: {error_msg}"}
    else:
        toast = {"type": "success", "message": f"✅ 已成功开放端口 {port} 并部署放行规则！"}

    # Re-render ports grid with toast trigger
    return await render_ports_grid_with_toast(request, node, toast)


@app.delete("/api/nodes/{node_id}/ports/{port}", response_class=HTMLResponse)
async def api_close_port(request: Request, node_id: int, port: int):
    """Delete all rules associated with a port on the remote node."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    # Query live rules to extract matching rule numbers
    wl_result = await ssh.get_whitelist(node)
    if not wl_result.get("ok"):
        toast = {"type": "error", "message": f"❌ 关闭端口失败: 无法拉取 UFW 状态 ({wl_result.get('error')})"}
        return await render_ports_grid_with_toast(request, node, toast)

    # Filter rules matching the port
    rules = [r for r in wl_result.get("rules", []) if str(r.get("port")) == str(port)]
    
    # Sort rule indexes descending to avoid shift errors
    rule_nums = sorted([r["num"] for r in rules], reverse=True)

    success = True
    error_msg = ""
    deleted_count = 0

    for num in rule_nums:
        result = await ssh.run(node, f"delete_num {num}")
        if not result.get("ok"):
            success = False
            error_msg = result.get("error", "删除失败")
            break
        deleted_count += 1

    # Log operation
    log_detail = f"关闭服务端口 {port}，删除了 {deleted_count} 条 UFW 规则。"
    if not success:
        log_detail += f" (中途失败: {error_msg})"
    await db.add_op_log(node_id, node["name"], "CLOSE_PORT", f"{port}", log_detail, success)

    toast = None
    if not success:
        toast = {"type": "error", "message": f"❌ 部分规则删除失败: {error_msg}"}
    else:
        toast = {"type": "success", "message": f"✅ 端口 {port} 已成功关闭并清理规则！"}

    return await render_ports_grid_with_toast(request, node, toast)


# Helper to re-render the grid
async def render_ports_grid_with_toast(request: Request, node: dict, toast: dict | None):
    wl_result = await ssh.get_whitelist(node)
    rules = wl_result.get("rules", []) if wl_result.get("ok") else []
    port_data = {}
    for r in rules:
        port = str(r.get("port"))
        proto = r.get("proto", "all")
        if port not in port_data:
            port_data[port] = {"port": port, "protocol_label": proto, "rules": []}
        if r.get("ip"):
            port_data[port]["rules"].append(r)
            
    for p, p_info in port_data.items():
        protos = {r["proto"] for r in p_info["rules"]}
        if "tcp" in protos and "udp" in protos:
            p_info["protocol_label"] = "tcp+udp"
        elif "tcp" in protos:
            p_info["protocol_label"] = "tcp"
        elif "udp" in protos:
            p_info["protocol_label"] = "udp"
        else:
            p_info["protocol_label"] = "all"

    return templates.TemplateResponse(
        "partials/port_cards_grid.html",
        {"request": request, "node": node, "port_data": port_data, "toast": toast},
    )


# ---------------------------------------------------------------------------
# API: Port Card Whitelist Operations
# ---------------------------------------------------------------------------

@app.post("/api/nodes/{node_id}/ports/{port}/ips", response_class=HTMLResponse)
async def api_whitelist_ip(
    request: Request,
    node_id: int,
    port: int,
    ip_cidr: str = Form(...),
):
    """Whitelist a single IP/CIDR or expand an entire IP Group on this port card."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    ip_cidr = ip_cidr.strip()
    success = True
    added_ips = []
    error_msg = ""

    # Check if input matches an IP Group name
    groups = await db.get_all_ip_groups()
    matching_group = None
    for g in groups:
        if g["name"].lower() == ip_cidr.lower():
            matching_group = g
            break

    if matching_group:
        # Expand group and add all IPs
        for item in matching_group["ips"]:
            ip = item["ip_cidr"]
            result = await ssh.run(node, f"add {ip} {port} both")
            if not result.get("ok"):
                success = False
                error_msg = result.get("error")
                break
            added_ips.append(ip)
        log_detail = f"批量授权 IP 分组「{matching_group['name']}」到端口 {port}。IP列表: {', '.join(added_ips)}"
    else:
        # Standalone IP/CIDR
        if not validate_ip_cidr(ip_cidr):
            success = False
            error_msg = f"无效的 IP/CIDR 地址: {ip_cidr}"
        else:
            result = await ssh.run(node, f"add {ip_cidr} {port} both")
            if not result.get("ok"):
                success = False
                error_msg = result.get("error")
            else:
                added_ips.append(ip_cidr)
        log_detail = f"授权 {ip_cidr} 到端口 {port}。"

    if not success:
        log_detail += f" (失败: {error_msg})"
    await db.add_op_log(node_id, node["name"], "ALLOW_IP", f"{ip_cidr}:{port}", log_detail, success)

    toast = None
    if not success:
        toast = {"type": "error", "message": f"❌ 授权失败: {error_msg}"}
    else:
        group_tag = f" 分组「{matching_group['name']}」" if matching_group else ""
        toast = {"type": "success", "message": f"✅ 已成功将{group_tag} {ip_cidr} 放行到端口 {port}"}

    # Re-render single port card
    return await render_single_port_card(request, node, port, toast)


@app.delete("/api/nodes/{node_id}/ports/{port}/rules/{num}", response_class=HTMLResponse)
async def api_remove_rule(request: Request, node_id: int, port: int, num: int):
    """Remove a single specific rule number from UFW and re-render card."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    # Run command
    result = await ssh.run(node, f"delete_num {num}")
    success = result.get("ok", False)
    error_msg = result.get("error", "删除失败") if not success else ""

    # Log operation
    log_detail = f"删除端口 {port} 下的 UFW 规则 #{num}"
    if not success:
        log_detail += f" (失败: {error_msg})"
    await db.add_op_log(node_id, node["name"], "REMOVE_IP", f"Rule #{num}", log_detail, success)

    toast = None
    if not success:
        toast = {"type": "error", "message": f"❌ 删除规则失败: {error_msg}"}
    else:
        toast = {"type": "success", "message": f"✅ 规则 #{num} 已被成功移除"}

    return await render_single_port_card(request, node, port, toast)


# Helper to re-render single card
async def render_single_port_card(request: Request, node: dict, port: int, toast: dict | None):
    wl_result = await ssh.get_whitelist(node)
    rules = wl_result.get("rules", []) if wl_result.get("ok") else []
    
    # Filter rules for this port
    port_rules = [r for r in rules if str(r.get("port")) == str(port)]
    protos = {r["proto"] for r in port_rules}
    
    if "tcp" in protos and "udp" in protos:
        proto_label = "tcp+udp"
    elif "tcp" in protos:
        proto_label = "tcp"
    elif "udp" in protos:
        proto_label = "udp"
    else:
        proto_label = "both"

    data = {
        "port": port,
        "protocol_label": proto_label,
        "rules": port_rules
    }

    resp = templates.TemplateResponse(
        "partials/port_card.html",
        {"request": request, "node": node, "data": data, "toast": toast},
    )
    resp.headers["HX-Trigger"] = "rules-updated"
    return resp


# ---------------------------------------------------------------------------
# API: IP Group Library Operations
# ---------------------------------------------------------------------------

@app.post("/api/ip-groups", response_class=HTMLResponse)
async def api_create_ip_group(
    request: Request,
    name: str = Form(...),
    remark: str = Form(""),
):
    """Create a new IP group in library."""
    group_id = await db.create_ip_group(name, remark)
    groups = await db.get_all_ip_groups()
    
    toast = {"type": "success", "message": f"✅ IP 分组「{name}」已创建！"}
    return templates.TemplateResponse(
        "partials/ip_group_list.html",
        {
            "request": request,
            "groups": groups,
            "new_group_id": group_id,
            "toast": toast,
        },
    )


@app.delete("/api/ip-groups/{group_id}", response_class=HTMLResponse)
async def api_delete_ip_group(request: Request, group_id: int):
    """Delete an IP group."""
    group = await db.get_ip_group(group_id)
    if not group:
        raise HTTPException(status_code=404)
        
    await db.delete_ip_group(group_id)
    groups = await db.get_all_ip_groups()
    
    toast = {"type": "success", "message": f"🗑️ IP 分组「{group['name']}」已删除"}
    return templates.TemplateResponse(
        "partials/ip_group_list.html",
        {"request": request, "groups": groups, "toast": toast},
    )


@app.post("/api/ip-groups/{group_id}/ips", response_class=HTMLResponse)
async def api_add_group_ip(
    request: Request,
    group_id: int,
    ip_cidr: str = Form(...),
    note: str = Form(""),
):
    """Add an IP/CIDR to a group."""
    ip_cidr = ip_cidr.strip()
    if not validate_ip_cidr(ip_cidr):
        groups = await db.get_all_ip_groups()
        return templates.TemplateResponse(
            "partials/ip_group_list.html",
            {
                "request": request,
                "groups": groups,
                "new_group_id": group_id,
                "toast": {"type": "error", "message": f"❌ 无效的 IP/CIDR 格式: {ip_cidr}"},
            },
        )
        
    try:
        await db.add_ip_group_item(group_id, ip_cidr, note)
    except Exception as exc:
        if "UNIQUE" in str(exc):
            groups = await db.get_all_ip_groups()
            return templates.TemplateResponse(
                "partials/ip_group_list.html",
                {
                    "request": request,
                    "groups": groups,
                    "new_group_id": group_id,
                    "toast": {"type": "error", "message": f"❌ IP {ip_cidr} 已经存在于该分组中！"},
                },
            )
        raise

    groups = await db.get_all_ip_groups()
    toast = {"type": "success", "message": f"✅ IP {ip_cidr} 已成功添加到分组中"}
    return templates.TemplateResponse(
        "partials/ip_group_list.html",
        {
            "request": request,
            "groups": groups,
            "new_group_id": group_id,
            "toast": toast,
        },
    )


@app.delete("/api/ip-groups/{group_id}/ips/{ip_id}", response_class=HTMLResponse)
async def api_delete_group_ip(request: Request, group_id: int, ip_id: int):
    """Delete an IP from an IP group."""
    await db.delete_ip_group_item(ip_id)
    groups = await db.get_all_ip_groups()
    
    toast = {"type": "success", "message": "✅ IP 已从分组中移除"}
    return templates.TemplateResponse(
        "partials/ip_group_list.html",
        {
            "request": request,
            "groups": groups,
            "new_group_id": group_id,
            "toast": toast,
        },
    )


# ---------------------------------------------------------------------------
# API: Node CRUD (Nodes Management Page)
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
    country, country_code = await get_ip_country(host)
    node_id = await db.create_node(
        name=name,
        host=host.strip(),
        ssh_port=ssh_port,
        ssh_user=ssh_user.strip(),
        snell_port=snell_port,
        snell_conf=snell_conf.strip(),
        remark=remark.strip(),
        country=country,
        country_code=country_code,
    )
    await db.add_op_log(node_id, name, "ADD_NODE", host.strip(), f"手动添加端口 {snell_port}，归属地: {country}")
    
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
            "toast": {"type": "success", "message": f"✅ 节点 {name} 已成功添加"},
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
            "toast": {"type": "success", "message": f"✅ 节点 {name} 配置已成功更新"},
        },
    )


@app.delete("/api/nodes/{node_id}", response_class=HTMLResponse)
async def api_delete_node(request: Request, node_id: int):
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
            "toast": {"type": "success", "message": f"🗑️ 节点 {node['name']} 已被移除"},
        },
    )


# ---------------------------------------------------------------------------
# API: Setup Script & Discover Node
# ---------------------------------------------------------------------------

@app.post("/api/nodes/discover", response_class=HTMLResponse)
async def api_discover_node(
    request: Request,
    host: str = Form(...),
    ssh_port: int = Form(22),
    snell_port: str = Form(""),
):
    try:
        parsed_snell_port = int(snell_port) if snell_port.strip() else 0
    except ValueError:
        parsed_snell_port = 0

    node_stub = {
        "host": host.strip(),
        "ssh_port": ssh_port,
        "ssh_user": "snellmgr",
        "snell_port": parsed_snell_port,
    }

    # Test SSH connection
    status = await ssh.test_connection(node_stub)
    if not status.get("ok"):
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
                "toast": {"type": "error", "message": f"❌ SSH 连接失败: {status.get('error', 'unknown')}"},
            },
        )

    if parsed_snell_port > 0:
        final_snell_port = parsed_snell_port
    else:
        node_stub["snell_conf"] = config.snell.default_conf_path
        port_result = await ssh.get_snell_port(node_stub)
        final_snell_port = port_result.get("port", 28261) if port_result.get("ok") else 28261

    hostname = status.get("hostname", host.strip())

    country, country_code = await get_ip_country(host)
    # Create node
    node_id = await db.create_node(
        name=hostname,
        host=host.strip(),
        ssh_port=ssh_port,
        ssh_user="snellmgr",
        snell_port=final_snell_port,
        snell_conf=config.snell.default_conf_path,
        country=country,
        country_code=country_code,
    )
    await db.add_op_log(node_id, hostname, "DISCOVER", host.strip(), f"自动发现并添加节点，默认端口: {final_snell_port}，归属地: {country}")

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
            "toast": {"type": "success", "message": f"✅ 已成功发现并添加节点: {hostname} (SNELL 端口: {final_snell_port})"},
        },
    )


@app.get("/partials/nodes/{node_id}/row", response_class=HTMLResponse)
async def partial_node_row(request: Request, node_id: int):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return templates.TemplateResponse(
        "partials/node_row.html",
        {"request": request, "node": node},
    )


@app.get("/partials/nodes/{node_id}/edit", response_class=HTMLResponse)
async def partial_node_edit(request: Request, node_id: int):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return templates.TemplateResponse(
        "partials/node_edit_row.html",
        {"request": request, "node": node},
    )


@app.get("/api/nodes/setup-script", response_class=PlainTextResponse)
async def api_setup_script():
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()

    # Read snell-fwctl script content
    fwctl_path = NODE_DIR / "snell-fwctl"
    try:
        fwctl_content = fwctl_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fwctl_content = "#!/bin/bash\necho '{\"ok\":false,\"error\":\"snell-fwctl not deployed\"}'"

    script = f"""#!/bin/bash
# VPS UFW Firewall Manager — Node Setup Script
# Generated by controller. Run as root on the target node.

set -euo pipefail

PUBKEY='{pubkey}'
CTRL_IP='{ctrl_ip}'

echo "══════════════════════════════════════════"
echo " VPS UFW Firewall Manager — 节点初始化"
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

# 6. Ensure UFW is installed, configured, and active
echo "  配置 UFW 防火墙... "
if ! command -v ufw &>/dev/null; then
    echo "    未检测到 UFW，正在安装... "
    apt-get update -qq && apt-get install -y ufw >/dev/null
    echo "    UFW 安装完成 ✓"
fi

if command -v ufw &>/dev/null; then
    # Detect SSH ports to prevent lockouts
    ssh_ports=("22")
    if [ -f /etc/ssh/sshd_config ]; then
        config_port=$(grep -i '^Port ' /etc/ssh/sshd_config | awk '{{print $2}}' || true)
        if [ -n "$config_port" ]; then
            ssh_ports+=("$config_port")
        fi
    fi
    if [ -d /etc/ssh/sshd_config.d ]; then
        d_port=$(grep -rh -i '^Port ' /etc/ssh/sshd_config.d/ 2>/dev/null | awk '{{print $2}}' || true)
        if [ -n "$d_port" ]; then
            ssh_ports+=("$d_port")
        fi
    fi
    if [ -n "${{SSH_CONNECTION:-}}" ]; then
        conn_port=$(echo "$SSH_CONNECTION" | awk '{{print $4}}')
        if [ -n "$conn_port" ]; then
            ssh_ports+=("$conn_port")
        fi
    fi

    # Allow detected SSH ports
    ufw allow ssh &>/dev/null || true
    for p in "${{ssh_ports[@]}}"; do
        if [ -n "$p" ] && [[ "$p" =~ ^[0-9]+$ ]]; then
            ufw allow "$p"/tcp &>/dev/null || true
        fi
    done

    # Enable UFW if inactive
    if ! ufw status | grep -q "Status: active"; then
        ufw --force enable &>/dev/null
    fi

    # Enable logging
    ufw logging on &>/dev/null || true
    echo "    UFW 已启用并配置安全规则 ✓"
else
    echo "    ⚠️ 警告：无法安装或找到 UFW，请手动安装！"
fi

# 7. Test
echo -n "  测试 snell-fwctl... "
RESULT=$(sudo -u snellmgr sudo /usr/local/sbin/snell-fwctl status 2>&1) || true
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
    pubkey = ssh.get_public_key()
    ctrl_ip = ssh.get_controller_ip()
    
    # Resolve client public IP from request headers or remote connection host
    client_ip = request.headers.get("x-forwarded-for", request.client.host if request.client else "未知")
    if "," in client_ip:
        client_ip = client_ip.split(",")[0].strip()
        
    fwctl_path = NODE_DIR / "snell-fwctl"
    try:
        fwctl_content = fwctl_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        fwctl_content = "# snell-fwctl not found"

    return templates.TemplateResponse(
        "partials/setup_script.html",
        {
            "request": request, 
            "pubkey": pubkey, 
            "ctrl_ip": ctrl_ip, 
            "client_ip": client_ip,
            "fwctl_content": fwctl_content
        },
    )


# ---------------------------------------------------------------------------
# API: Node Access and Operations Logging
# ---------------------------------------------------------------------------

@app.get("/partials/nodes/{node_id}/access-log", response_class=HTMLResponse)
async def partial_access_log(request: Request, node_id: int, hours: int = 24):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
        
    result = await ssh.get_candidates(node, hours)
    if result.get("ok"):
        tz_offset = result.get("tz_offset", "+0000")
        for c in result.get("candidates", []):
            orig_seen = c.get("last_seen", "")
            if orig_seen:
                c["last_seen"] = convert_to_taiwan_time(orig_seen, tz_offset)
    
    # Fetch live whitelist to see what IPs are already allowed on the node's snell port
    wl_result = await ssh.get_whitelist(node)
    allowed_set = set()
    if wl_result.get("ok"):
        for r in wl_result.get("rules", []):
            if str(r.get("port")) == str(node["snell_port"]):
                allowed_set.add(r.get("ip"))

    ip_groups = await db.get_all_ip_groups()
    return templates.TemplateResponse(
        "partials/access_log.html",
        {
            "request": request,
            "node": node,
            "result": result,
            "allowed_set": allowed_set,
            "all_groups": ip_groups,
        },
    )


@app.post("/api/nodes/{node_id}/quick-add", response_class=HTMLResponse)
async def api_quick_add(
    request: Request,
    node_id: int,
    ip_cidr: str = Form(...),
    group_id: str = Form(...),
    new_group_name: str | None = Form(None),
):
    ip_cidr = ip_cidr.strip()
    if not validate_ip_cidr(ip_cidr):
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": f"无效 IP: {ip_cidr}"}},
        )

    resolved_group_id = None
    group_name = ""

    if group_id == "__new__":
        if not new_group_name or not new_group_name.strip():
            return templates.TemplateResponse(
                "partials/toast.html",
                {"request": request, "toast": {"type": "error", "message": "新分组名称不能为空"}},
            )
        new_group_name = new_group_name.strip()
        try:
            existing_groups = await db.get_all_ip_groups()
            existing_g = None
            for g in existing_groups:
                if g["name"].lower() == new_group_name.lower():
                    existing_g = g
                    break
            
            if existing_g:
                resolved_group_id = existing_g["id"]
                group_name = existing_g["name"]
            else:
                resolved_group_id = await db.create_ip_group(new_group_name, "从安全日志拦截列表快速创建")
                group_name = new_group_name
        except Exception as exc:
            return templates.TemplateResponse(
                "partials/toast.html",
                {"request": request, "toast": {"type": "error", "message": f"创建新分组失败: {exc}"}},
            )
    else:
        try:
            resolved_group_id = int(group_id)
        except ValueError:
            return templates.TemplateResponse(
                "partials/toast.html",
                {"request": request, "toast": {"type": "error", "message": "无效的分组 ID"}},
            )
        group = await db.get_ip_group(resolved_group_id)
        if not group:
            return templates.TemplateResponse(
                "partials/toast.html",
                {"request": request, "toast": {"type": "error", "message": "IP 分组不存在"}},
            )
        group_name = group["name"]

    try:
        await db.add_ip_group_item(resolved_group_id, ip_cidr, "快速添加")
    except Exception as exc:
        if "UNIQUE" in str(exc):
            return templates.TemplateResponse(
                "partials/toast.html",
                {"request": request, "toast": {"type": "warning", "message": f"{ip_cidr} 已在组 {group_name} 中"}},
            )
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": f"添加失败: {exc}"}},
        )

    node = await db.get_node(node_id)
    await db.add_op_log(
        node_id, node["name"] if node else "unknown", "QUICK_ADD",
        ip_cidr, f"快速加入 IP 分组: {group_name}",
        success=True
    )

    resp = templates.TemplateResponse(
        "partials/toast.html",
        {
            "request": request,
            "toast": {
                "type": "success",
                "message": f"已将 {ip_cidr} 快速加入 IP 分组「{group_name}」",
            },
        },
    )
    resp.headers["HX-Trigger"] = "rules-updated"
    return resp


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )
