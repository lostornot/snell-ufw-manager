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

from app import database as db
from app.config import load_config
from app.ssh_executor import SSHExecutor

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

def _sync_get_ip_geo(host: str) -> tuple[str, str, str, str]:
    """Blocking sync call to ip-api using urllib, returning (country, country_code, city, asn)."""
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
                    country = data.get("country", "未知地区")
                    country_code = data.get("countryCode", "XX")
                    city = data.get("city", "")
                    asn = data.get("as", "")  # e.g., "AS13335 Cloudflare, Inc."
                    return country, country_code, city, asn
    except Exception:
        pass
    return "未知地区", "XX", "", ""


async def get_ip_geo_info(ip: str) -> dict:
    """Get IP geo location and ASN info, hitting local cache database first, and auto-bypassing '未知地区' dirty records."""
    h = ip.strip()
    if "/" in h:
        h = h.split("/")[0]
        
    if h.lower() in ("localhost", "127.0.0.1", "::1", "any", "anywhere", "anywhere") or h.startswith("192.168.") or h.startswith("10.") or h.startswith("172.16."):
        return {
            "country": "局域网/回环",
            "country_code": "CN",
            "flag": "💻",
            "city": "本地",
            "asn": "Private IP",
            "asn_code": "",
            "asn_org": "Private IP"
        }

    # 1. Check database cache
    try:
        cached = await db.get_cached_ip_geo(h)
        # ONLY accept cache if it has valid resolved values (not "未知地区" or empty)
        if cached and cached.get("country") not in ("未知地区", "未知", "") and cached.get("country_code") not in ("XX", ""):
            asn_full = cached.get("asn") or ""
            asn_code = ""
            asn_org = ""
            if asn_full:
                parts = asn_full.split(" ", 1)
                asn_code = parts[0]
                if len(parts) > 1:
                    asn_org = parts[1]
            return {
                "country": cached.get("country"),
                "country_code": cached.get("country_code"),
                "flag": get_flag_emoji(cached.get("country_code")),
                "city": cached.get("city") or "",
                "asn": asn_full,
                "asn_code": asn_code,
                "asn_org": asn_org
            }
    except Exception as e:
        logger.error(f"Error fetching cached ip geo for {h}: {e}")

    # 2. Call external API (concurrency protected by thread pool)
    country, country_code, city, asn = await asyncio.to_thread(_sync_get_ip_geo, h)
    
    # 3. Store into database cache (even if failed, we cache it, but subsequent reads will bypass it if it's '未知地区')
    try:
        await db.cache_ip_geo(h, country, country_code, city, asn)
    except Exception as e:
        logger.error(f"Error caching ip geo for {h}: {e}")
        
    asn_full = asn or ""
    asn_code = ""
    asn_org = ""
    if asn_full:
        parts = asn_full.split(" ", 1)
        asn_code = parts[0]
        if len(parts) > 1:
            asn_org = parts[1]

    return {
        "country": country,
        "country_code": country_code,
        "flag": get_flag_emoji(country_code),
        "city": city,
        "asn": asn_full,
        "asn_code": asn_code,
        "asn_org": asn_org
    }


async def get_ip_country(host: str) -> tuple[str, str]:
    """Resolve IP or domain to country and country_code. Maintained for backward compatibility."""
    geo = await get_ip_geo_info(host)
    return geo["country"], geo["country_code"]


async def get_bulk_ip_geo(ips: list[str]) -> dict[str, dict]:
    """Resolve a list of IPs concurrently with caching, returning a map of {ip: geo_dict}."""
    valid_ips = []
    for ip in set(ips):
        if not ip:
            continue
        ip_strip = ip.strip()
        if ip_strip.lower() in ("any", "anywhere", "all", "未知"):
            continue
        valid_ips.append(ip_strip)
        
    if not valid_ips:
        return {}
        
    results = await asyncio.gather(*[get_ip_geo_info(ip) for ip in valid_ips])
    return {ip: res for ip, res in zip(valid_ips, results)}


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
    """Validate an IPv4/IPv6 address, CIDR notation, or anywhere keywords."""
    value = value.strip().lower()
    if value in ("any", "anywhere", "all"):
        return True
    try:
        if "/" in value:
            try:
                ipaddress.IPv4Network(value, strict=False)
            except (ipaddress.AddressValueError, ipaddress.NetmaskValueError, ValueError):
                ipaddress.IPv6Network(value, strict=False)
        else:
            try:
                ipaddress.IPv4Address(value)
            except (ipaddress.AddressValueError, ValueError):
                ipaddress.IPv6Address(value)
        return True
    except Exception:
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
async def dashboard(request: Request, group: str = "none"):
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

    # Group by country logic
    grouped_nodes = {}
    if group == "country":
        for node in nodes:
            c = node.get("country") or "未知地区"
            c_code = node.get("country_code") or "XX"
            key = (c, c_code)
            if key not in grouped_nodes:
                grouped_nodes[key] = []
            grouped_nodes[key].append(node)
        # Sort groups by country name, but put "未知" at the end if exists
        sorted_groups = sorted(
            grouped_nodes.items(),
            key=lambda x: (x[0][0] in ("未知地区", "未知"), x[0][0])
        )
    else:
        sorted_groups = []
        
    logs = await db.get_op_logs(limit=10)
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request, 
            "nodes": nodes, 
            "logs": logs,
            "group": group,
            "sorted_groups": sorted_groups,
        },
    )



@app.get("/ip-manage", response_class=HTMLResponse)
async def ip_manage_page(request: Request):
    """IP address management page (replaces legacy IP groups)."""
    ip_addresses = await db.get_all_ip_addresses()
    all_tags = await db.get_all_tags()
    
    # Get bulk IP geography details
    ips = [ip["ip_cidr"] for ip in ip_addresses]
    ip_geos = await get_bulk_ip_geo(ips)
    
    return templates.TemplateResponse(
        "ip_groups.html",
        {
            "request": request, 
            "ip_addresses": ip_addresses, 
            "all_tags": all_tags,
            "ip_geos": ip_geos
        },
    )


# Legacy redirect for old bookmarks
@app.get("/ip-groups", response_class=HTMLResponse)
async def ip_groups_redirect(request: Request):
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ip-manage", status_code=301)


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
            
    all_tags = await db.get_all_tags()
    all_nodes = await db.get_all_nodes()
    return templates.TemplateResponse(
        "node_detail.html",
        {
            "request": request,
            "node": node,
            "all_tags": all_tags,
            "all_nodes": all_nodes,
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
    """SSH query node status and environment, return card summary."""
    node = await db.get_node(node_id)
    if not node:
        return f'<div class="glass-card">节点不存在 ({node_id})</div>'

    result = await ssh.test_connection(node)
    if result.get("ok"):
        # Fetch environment details (docker, tailscale, ports)
        env_result = await ssh.detect_environment(node)
        ports = []
        docker_risk = "none"
        docker_active = False
        tailscale_ip = ""
        
        if env_result.get("ok"):
            snell_info = env_result.get("snell", {})
            if snell_info.get("port"):
                ports.append(str(snell_info["port"]))
            
            docker_info = env_result.get("docker", {})
            docker_active = docker_info.get("running", False)
            docker_risk = docker_info.get("risk", "none")
            
            ts_info = env_result.get("tailscale", {})
            tailscale_ip = ts_info.get("ip", "")

            # Sync node state in DB
            await db.update_node(
                node_id,
                nftables_active=1 if result.get("nftables_active") else 0,
                docker_detected=1 if docker_active else 0,
                docker_risk=docker_risk,
                tailscale_ip=tailscale_ip,
                last_checked_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
        status = {
            "online": True,
            "ufw_status": "inactive" if result.get("nftables_active") else "active", # Compatibility label
            "nftables_active": result.get("nftables_active", False),
            "uptime": result.get("uptime", "unknown"),
            "kernel": result.get("kernel", "unknown"),
            "ports": ports,
            "docker_active": docker_active,
            "docker_risk": docker_risk,
            "tailscale_ip": tailscale_ip
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
    """Fetch live policies for the node and construct the Service Policies Grid."""
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    # 1. Fetch node environment details (like active listening status)
    env_result = await ssh.detect_environment(node)
    
    # 2. Get local policies assigned to this node
    policies = await db.get_node_policies(node_id)
    
    # Initialize standard default policies if none assigned yet
    if not policies:
        snell_port = node["snell_port"]
        # Create standard Snell policy
        snell_policy_id = await db.create_policy(
            name="Snell 代理服务",
            service="snell",
            port=snell_port,
            protocol="tcp+udp",
            allow_sets="relay_ips,direct_ips",
            default_action="drop"
        )
        await db.link_node_policy(node_id, snell_policy_id)

        # Create standard SSH policy
        ssh_port = node.get("ssh_port", 22)
        ssh_policy_id = await db.create_policy(
            name="SSH 管理访问",
            service="ssh",
            port=ssh_port,
            protocol="tcp",
            allow_sets="tailscale_ips,direct_ips",
            default_action="drop"
        )
        await db.link_node_policy(node_id, ssh_policy_id)
        
        # Reload policies
        policies = await db.get_node_policies(node_id)

    # 3. Structure policy data for templating
    # We will pass policy items as structured card items
    port_data = {}
    for p in policies:
        svc = p["service"]
        port_data[svc] = {
            "id": p["id"],
            "name": p["name"],
            "service": svc,
            "port": p["port"],
            "protocol": p["protocol"],
            "allow_sets": [s.strip() for s in p["allow_sets"].split(",") if s.strip()],
            "default_action": p["default_action"],
            "enabled": p["node_enabled"],
            "last_applied_at": p["last_applied_at"],
            "last_apply_status": p["last_apply_status"],
            "last_error": p["last_error"]
        }

    # Fetch geo info maps for display if required
    ip_remarks = await db.get_ip_remarks_map()

    return templates.TemplateResponse(
        "partials/port_cards_grid.html",
        {
            "request": request, 
            "node": node, 
            "port_data": port_data, 
            "env_status": env_result.get("snell", {}) if env_result.get("ok") else {},
            "docker_status": env_result.get("docker", {}) if env_result.get("ok") else {},
            "ip_remarks": ip_remarks
        },
    )


@app.post("/api/nodes/{node_id}/ports", response_class=HTMLResponse)
async def api_apply_policy(
    request: Request,
    node_id: int,
    snell_allow: list[str] = Form(default=[]),
    ssh_allow: list[str] = Form(default=[]),
    iperf3_allow: list[str] = Form(default=[]),
):
    """
    Apply unified nftables firewall policy to the node.
    Includes anti-lockout SSH connection validation:
    1. Apply policy temporarily (lock is active for 15s)
    2. Try connecting back via SSH. If succeeded within 5s, confirm policy.
    3. If failed, allow automatic rollback.
    """
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)

    # 1. Fetch IP lists for each active source set from db
    relay_items = await db.get_ips_by_tag("relay_ips")
    direct_items = await db.get_ips_by_tag("direct_ips")
    ts_items = await db.get_ips_by_tag("tailscale_ips")
    cn_items = await db.get_ips_by_tag("cn_ips")
    temp_items = await db.get_ips_by_tag("temp_ips")

    relay_ips = [item["ip_cidr"] for item in relay_items]
    direct_ips = [item["ip_cidr"] for item in direct_items]
    ts_ips = [item["ip_cidr"] for item in ts_items]
    cn_ips = [item["ip_cidr"] for item in cn_items]
    temp_ips = [item["ip_cidr"] for item in temp_items]

    # Package policy schema
    policy_data = {
        "service": "combined",
        "relay_ips": relay_ips,
        "direct_ips": direct_ips,
        "tailscale_ips": ts_ips,
        "cn_ips": cn_ips,
        "temp_ips": temp_ips,
        "policies": [
            {
                "service": "snell",
                "relay_ips": True if "relay_ips" in snell_allow else False,
                "direct_ips": True if "direct_ips" in snell_allow else False,
                "cn_ips": True if "cn_ips" in snell_allow else False,
                "temp_ips": True if "temp_ips" in snell_allow else False,
            },
            {
                "service": "ssh",
                "tailscale_ips": True if "tailscale_ips" in ssh_allow else False,
                "direct_ips": True if "direct_ips" in ssh_allow else False,
            },
            {
                "service": "iperf3",
                "temp_ips": True if "temp_ips" in iperf3_allow else False,
            }
        ]
    }
    policy_json = json.dumps(policy_data)

    # 2. Plan check (dry-run)
    plan_res = await ssh.plan_policy(node, policy_json)
    if not plan_res.get("ok"):
        toast = {"type": "error", "message": f"❌ 规则校验失败: {plan_res.get('error')}"}
        return await render_ports_grid_with_toast(request, node, toast)

    # 3. Apply Policy Temporarily
    apply_res = await ssh.apply_policy(node, policy_json)
    if not apply_res.get("ok"):
        toast = {"type": "error", "message": f"❌ 策略加载失败: {apply_res.get('error')}"}
        return await render_ports_grid_with_toast(request, node, toast)

    # 4. Perform Anti-lockout validation (try connecting again)
    validation_success = False
    await asyncio.sleep(1.0) # Let rule load settle down
    
    try:
        # We test connection with a short timeout to confirm SSH is still up
        test_res = await asyncio.wait_for(ssh.test_connection(node), timeout=5.0)
        if test_res.get("ok"):
            validation_success = True
    except Exception:
        pass

    # 5. Confirm or Let Rollback
    if validation_success:
        confirm_res = await ssh.confirm_policy(node)
        if confirm_res.get("ok"):
            toast = {"type": "success", "message": "✅ 防火墙策略应用并持久化成功！已验证 SSH 通道正常！"}
            # Log success
            await db.add_op_log(
                node_id, node["name"], "APPLY_POLICY", "all",
                f"成功应用 nftables 策略。Snell 允许: {','.join(snell_allow)}; SSH 允许: {','.join(ssh_allow)}",
                True
            )
            
            # Sync local policies table (Standard Snell + SSH + iPerf3)
            # Find and update local database states
            db_policies = await db.get_node_policies(node_id)
            for db_p in db_policies:
                svc = db_p["service"]
                allow_str = ""
                if svc == "snell":
                    allow_str = ",".join(snell_allow)
                elif svc == "ssh":
                    allow_str = ",".join(ssh_allow)
                elif svc == "iperf3":
                    allow_str = ",".join(iperf3_allow)
                
                await db.update_node_policy_status(node_id, db_p["id"], "applied")
        else:
            toast = {"type": "error", "message": f"❌ 确认失败: {confirm_res.get('error')}"}
    else:
        toast = {
            "type": "error",
            "message": "⚠️ 警告：检测到 SSH 连接可能被防火墙拦截，已自动执行安全回退（Rollback）！"
        }
        await db.add_op_log(
            node_id, node["name"], "APPLY_POLICY", "all",
            "应用策略后 SSH 检测超时，触发防锁死安全回退。",
            False
        )

    return await render_ports_grid_with_toast(request, node, toast)


async def render_ports_grid_with_toast(request: Request, node: dict, toast: dict | None, all_tags: list | None = None):
    """Helper to re-render the port/policy cards grid with feedback message."""
    env_result = await ssh.detect_environment(node)
    policies = await db.get_node_policies(node["id"])
    
    port_data = {}
    for p in policies:
        svc = p["service"]
        port_data[svc] = {
            "id": p["id"],
            "name": p["name"],
            "service": svc,
            "port": p["port"],
            "protocol": p["protocol"],
            "allow_sets": [s.strip() for s in p["allow_sets"].split(",") if s.strip()],
            "default_action": p["default_action"],
            "enabled": p["node_enabled"],
            "last_applied_at": p["last_applied_at"],
            "last_apply_status": p["last_apply_status"],
            "last_error": p["last_error"]
        }

    ip_remarks = await db.get_ip_remarks_map()

    return templates.TemplateResponse(
        "partials/port_cards_grid.html",
        {
            "request": request, 
            "node": node, 
            "port_data": port_data, 
            "env_status": env_result.get("snell", {}) if env_result.get("ok") else {},
            "docker_status": env_result.get("docker", {}) if env_result.get("ok") else {},
            "toast": toast,
            "ip_remarks": ip_remarks,
            "all_tags": all_tags
        },
    )


# ---------------------------------------------------------------------------
# API: IP Address Management (replaces legacy IP Group operations)
# ---------------------------------------------------------------------------

async def render_ip_address_list(request: Request, toast: dict | None = None):
    """Helper to fetch all IP addresses with geocoding info and render the list partial."""
    ip_addresses = await db.get_all_ip_addresses()
    ips = [ip["ip_cidr"] for ip in ip_addresses]
    ip_geos = await get_bulk_ip_geo(ips)
    return templates.TemplateResponse(
        "partials/ip_address_list.html",
        {
            "request": request, 
            "ip_addresses": ip_addresses, 
            "toast": toast, 
            "ip_geos": ip_geos
        },
    )


@app.post("/api/ip-addresses", response_class=HTMLResponse)
async def api_create_ip_address(
    request: Request,
    ip_cidr: str = Form(...),
    tag: str = Form(""),
):
    """Add a new IP address to the registry."""
    ip_cidr = ip_cidr.strip()
    tag = tag.strip()
    if not validate_ip_cidr(ip_cidr):
        toast = {"type": "error", "message": f"❌ 无效的 IP/CIDR 格式: {ip_cidr}"}
        return await render_ip_address_list(request, toast)

    try:
        await db.upsert_ip_address(ip_cidr, tag, "manual")
    except Exception as exc:
        toast = {"type": "error", "message": f"❌ 添加失败: {exc}"}
        return await render_ip_address_list(request, toast)

    toast = {"type": "success", "message": f"✅ IP {ip_cidr} 已添加" + (f"，标签: {tag}" if tag else "")}
    return await render_ip_address_list(request, toast)


@app.put("/api/ip-addresses/{ip_id}", response_class=HTMLResponse)
async def api_update_ip_address(
    request: Request,
    ip_id: int,
    tag: str = Form(""),
):
    """Update an IP address tag."""
    await db.update_ip_address(ip_id, tag=tag.strip())
    toast = {"type": "success", "message": "✅ 标签已更新"}
    return await render_ip_address_list(request, toast)


@app.delete("/api/ip-addresses/{ip_id}", response_class=HTMLResponse)
async def api_delete_ip_address(request: Request, ip_id: int):
    """Delete an IP address record."""
    await db.delete_ip_address(ip_id)
    toast = {"type": "success", "message": "✅ IP 地址已删除"}
    return await render_ip_address_list(request, toast)


@app.get("/partials/ip-tag-edit", response_class=HTMLResponse)
async def partial_ip_tag_edit(request: Request, ip: str):
    """Return inline edit input form for an IP tag, wrapped with check and cancel buttons."""
    remarks = await db.get_ip_remarks_map()
    current_tag = remarks.get(ip, "")
    
    html = f"""
    <div class="inline-edit-container" style="display: inline-flex; align-items: center; gap: 4px; vertical-align: middle;">
        <input type="hidden" name="ip" value="{ip}">
        <input type="text" name="tag" value="{current_tag}" 
               class="form-input"
               placeholder="标签"
               style="font-size: 0.68rem; height: 22px; width: 70px; padding: 1px 4px; background: var(--bg-primary); color: var(--text-primary); border: 1px solid var(--border-glass); border-radius: 3px; outline: none; margin: 0;"
               onkeydown="if(event.key==='Enter') {{ this.nextElementSibling.click(); }}"
               focus-me>
        <!-- Save Button -->
        <button type="button"
                hx-put="/api/ip-addresses/inline-edit" 
                hx-include="closest .inline-edit-container"
                hx-target="closest .inline-edit-container" 
                hx-swap="outerHTML" 
                class="btn btn-primary" 
                style="height: 22px; width: 22px; padding: 0; min-height: unset; display: inline-flex; align-items: center; justify-content: center; font-size: 0.75rem; border-radius: 3px; background: var(--accent-purple); border: none; color: white;" 
                title="保存">
            ✓
        </button>
        <!-- Cancel Button -->
        <button type="button"
                hx-get="/api/ip-addresses/inline-cancel?ip={ip}&current_tag={current_tag}" 
                hx-target="closest .inline-edit-container" 
                hx-swap="outerHTML" 
                class="btn btn-secondary" 
                style="height: 22px; width: 22px; padding: 0; min-height: unset; display: inline-flex; align-items: center; justify-content: center; font-size: 0.72rem; border-radius: 3px; background: rgba(15, 23, 42, 0.05); border: 1px solid rgba(15, 23, 42, 0.1); color: var(--text-secondary);" 
                title="取消">
            ✕
        </button>
    </div>
    <script>
        setTimeout(function() {{
            var inputs = document.querySelectorAll('input[focus-me]');
            if(inputs.length > 0) {{
                var lastInput = inputs[inputs.length - 1];
                lastInput.focus();
                lastInput.removeAttribute('focus-me');
            }}
        }}, 50);
    </script>
    """
    return HTMLResponse(content=html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


@app.put("/api/ip-addresses/inline-edit", response_class=HTMLResponse)
async def api_ip_inline_edit(request: Request, ip: str = Form(...), tag: str = Form("")):
    """Update IP tag inline and trigger list refreshes with toast feedback."""
    ip = ip.strip()
    tag = tag.strip()
    
    success = True
    error_msg = ""
    try:
        if ip and ip not in ("any", "anywhere", "all"):
            await db.upsert_ip_address(ip, tag, "manual")
    except Exception as exc:
        success = False
        error_msg = str(exc)

    if not success:
        resp_html = f"""
        <div class="toast-trigger hidden" data-message="❌ 标签更新失败: {error_msg}" data-type="error"></div>
        <span class="ip-tag-badge-trigger" 
              hx-get="/partials/ip-tag-edit?ip={ip}" 
              hx-trigger="click" 
              hx-target="this" 
              hx-swap="outerHTML"
              style="cursor: pointer; font-size: 0.68rem; padding: 1px 5px; border-radius: 3px; white-space: nowrap; background: rgba(239, 68, 68, 0.1); color: var(--error); display: inline-flex; align-items: center; gap: 4px;"
              title="点击编辑标签">
            标签失败
        </span>
        """
        return HTMLResponse(content=resp_html)

    resp_html = f"""
    <div class="toast-trigger hidden" data-message="✅ 标签已更新" data-type="success"></div>
    <span class="ip-tag-badge-trigger" 
          hx-get="/partials/ip-tag-edit?ip={ip}" 
          hx-trigger="click" 
          hx-target="this" 
          hx-swap="outerHTML"
          style="cursor: pointer; font-size: 0.68rem; padding: 1px 5px; border-radius: 3px; white-space: nowrap; background: rgba(139, 92, 246, 0.06); color: var(--text-secondary); display: inline-flex; align-items: center; gap: 4px;"
          title="点击编辑标签">
    """
    if tag:
        resp_html += f"{tag}</span>"
    else:
        resp_html += """<span style="border: 1px dashed rgba(15, 23, 42, 0.15); color: var(--text-muted); padding: 0 3px;">+ 标签</span></span>"""
        
    resp = HTMLResponse(content=resp_html)
    resp.headers["HX-Trigger"] = "rules-updated"
    return resp


@app.get("/api/ip-addresses/inline-cancel", response_class=HTMLResponse)
async def api_ip_inline_cancel(ip: str, current_tag: str = ""):
    """Cancel inline edit and restore the previous tag badge."""
    resp_html = f"""
    <span class="ip-tag-badge-trigger" 
          hx-get="/partials/ip-tag-edit?ip={ip}" 
          hx-trigger="click" 
          hx-target="this" 
          hx-swap="outerHTML"
          style="cursor: pointer; font-size: 0.68rem; padding: 1px 5px; border-radius: 3px; white-space: nowrap; background: rgba(139, 92, 246, 0.06); color: var(--text-secondary); display: inline-flex; align-items: center; gap: 4px;"
          title="点击编辑标签">
    """
    if current_tag:
        resp_html += f"{current_tag}</span>"
    else:
        resp_html += """<span style="border: 1px dashed rgba(15, 23, 42, 0.15); color: var(--text-muted); padding: 0 3px;">+ 标签</span></span>"""
    return HTMLResponse(content=resp_html, headers={"Cache-Control": "no-store, no-cache, must-revalidate, max-age=0"})


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
    tags: str = Form(""),
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
        tags=tags.strip(),
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
    tags: str = Form(""),
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
        tags=tags.strip(),
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


@app.get("/partials/nodes/{node_id}/header", response_class=HTMLResponse)
async def partial_node_header(request: Request, node_id: int):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return templates.TemplateResponse(
        "partials/node_detail_header.html",
        {"request": request, "node": node},
    )


@app.get("/partials/nodes/{node_id}/header/edit", response_class=HTMLResponse)
async def partial_node_header_edit(request: Request, node_id: int):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return templates.TemplateResponse(
        "partials/node_detail_header_edit.html",
        {"request": request, "node": node},
    )


@app.put("/api/nodes/{node_id}/header", response_class=HTMLResponse)
async def api_update_node_header(
    request: Request,
    node_id: int,
    name: str = Form(...),
    host: str = Form(...),
    ssh_port: int = Form(22),
    ssh_user: str = Form("snellmgr"),
    snell_port: int = Form(...),
    snell_conf: str = Form(""),
    tags: str = Form(""),
    remark: str = Form(""),
):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    
    country = node.get("country", "")
    country_code = node.get("country_code", "")
    if host.strip() != node["host"]:
        country, country_code = await get_ip_country(host)
        
    await db.update_node(
        node_id,
        name=name.strip(),
        host=host.strip(),
        ssh_port=ssh_port,
        ssh_user=ssh_user.strip(),
        snell_port=snell_port,
        snell_conf=snell_conf.strip(),
        tags=tags.strip(),
        remark=remark.strip(),
        country=country,
        country_code=country_code,
    )
    
    updated_node = await db.get_node(node_id)
    toast = {"type": "success", "message": f"✅ 节点 {name} 的配置已成功更新"}
    return templates.TemplateResponse(
        "partials/node_detail_header.html",
        {"request": request, "node": updated_node, "toast": toast},
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

# 0. Configure Timezone
echo -n "  设置系统时区为台湾时间 (Asia/Taipei)... "
if command -v timedatectl &>/dev/null; then
    timedatectl set-timezone Asia/Taipei || true
else
    ln -sf /usr/share/zoneinfo/Asia/Taipei /etc/localtime || true
fi
echo "完成 ✓"

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
async def partial_access_log(request: Request, node_id: int, hours: int = 24, port: str = "default"):
    node = await db.get_node(node_id)
    if not node:
        raise HTTPException(status_code=404)
        
    # Fetch live whitelist to see allowed IPs and extract all allowed ports
    wl_result = await ssh.get_whitelist(node)
    allowed_set = set()
    open_ports = set()
    if wl_result.get("ok"):
        for r in wl_result.get("rules", []):
            if str(r.get("port")) == str(node["snell_port"]):
                allowed_set.add(r.get("ip"))
            p_val = r.get("port")
            if p_val:
                open_ports.add(str(p_val))
                
    # Fallback to SNELL and SSH ports if no whitelist could be loaded
    if not open_ports:
        open_ports.add(str(node["snell_port"]))
        open_ports.add("22")
        
    if port == "default":
        query_port = str(node["snell_port"])
    elif port == "all":
        query_port = ",".join(open_ports)
    else:
        query_port = port
        
    result = await ssh.get_candidates(node, hours, query_port)
    candidates = []
    if result.get("ok"):
        tz_offset = result.get("tz_offset", "+0000")
        candidates = result.get("candidates", [])
        for c in candidates:
            orig_seen = c.get("last_seen", "")
            if orig_seen:
                c["last_seen"] = convert_to_taiwan_time(orig_seen, tz_offset)
        # Sort candidates by last_seen descending (newest first)
        candidates.sort(key=lambda x: x.get("last_seen", ""), reverse=True)

    # Get bulk IP geography details
    candidate_ips = [c.get("ip") for c in candidates if c.get("ip")]
    ip_geos = await get_bulk_ip_geo(candidate_ips)

    all_tags = await db.get_all_tags()
    ip_remarks = await db.get_ip_remarks_map()
    response = templates.TemplateResponse(
        "partials/access_log.html",
        {
            "request": request,
            "node": node,
            "result": result,
            "allowed_set": allowed_set,
            "all_tags": all_tags,
            "current_port": port,
            "ip_remarks": ip_remarks,
            "ip_geos": ip_geos,
        },
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


@app.post("/api/nodes/{node_id}/quick-add", response_class=HTMLResponse)
async def api_quick_add(
    request: Request,
    node_id: int,
    ip_cidr: str = Form(...),
    tag: str = Form(""),
):
    """Quick-add an IP from the access log with a tag."""
    ip_cidr = ip_cidr.strip()
    tag = tag.strip()
    if not validate_ip_cidr(ip_cidr):
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": f"无效 IP: {ip_cidr}"}},
        )

    try:
        await db.upsert_ip_address(ip_cidr, tag, "quick_add")
    except Exception as exc:
        return templates.TemplateResponse(
            "partials/toast.html",
            {"request": request, "toast": {"type": "error", "message": f"添加失败: {exc}"}},
        )

    node = await db.get_node(node_id)
    await db.add_op_log(
        node_id, node["name"] if node else "unknown", "QUICK_ADD",
        ip_cidr, f"快速注册 IP 到地址管理" + (f"，标签: {tag}" if tag else ""),
        success=True
    )

    resp = templates.TemplateResponse(
        "partials/toast.html",
        {
            "request": request,
            "toast": {
                "type": "success",
                "message": f"已将 {ip_cidr} 注册到 IP 地址管理" + (f"，标签「{tag}」" if tag else ""),
            },
        },
    )
    resp.headers["HX-Trigger"] = "rules-updated"
    return resp


@app.post("/api/ip-addresses/update-cn", response_class=HTMLResponse)
async def api_update_cn_ips(request: Request):
    """Fetch latest China IPv4 blocks and update local database's cn_ips tag."""
    import httpx
    
    urls = [
        "https://raw.githubusercontent.com/herrbischoff/country-ip-blocks/master/ipv4/cn.zone",
        "https://fastly.jsdelivr.net/gh/herrbischoff/country-ip-blocks@master/ipv4/cn.zone",
        "https://cdn.jsdelivr.net/gh/herrbischoff/country-ip-blocks@master/ipv4/cn.zone"
    ]
    
    content = ""
    error_msg = ""
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for url in urls:
            try:
                response = await client.get(url)
                if response.status_code == 200:
                    content = response.text
                    break
            except Exception as exc:
                error_msg = str(exc)
                continue
                
    if not content:
        toast = {"type": "error", "message": f"❌ 无法下载中国 IP 数据库，错误: {error_msg}"}
        return await render_ip_address_list(request, toast)
        
    # Parse CIDR lines
    cidrs = []
    for line in content.splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            cidrs.append(line)
            
    if not cidrs:
        toast = {"type": "error", "message": "❌ 解析 IP 数据库发现数据为空"}
        return await render_ip_address_list(request, toast)
        
    try:
        # Commit to DB
        await db.batch_reset_cn_ips(cidrs)
        toast = {"type": "success", "message": f"✅ 中国 IP 库已成功更新（共收录 {len(cidrs)} 条 CIDR 段）！"}
    except Exception as exc:
        toast = {"type": "error", "message": f"❌ 数据库写入失败: {exc}"}
        
    return await render_ip_address_list(request, toast)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=config.server.host,
        port=config.server.port,
        reload=False,
    )
