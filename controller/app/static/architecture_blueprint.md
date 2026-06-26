# Layered UFW-First Architecture Design Specification

This specification document outlines the design, schema refactoring, route structure, templating updates, styling specifications, and implementation code outlines for the **VPS UFW Firewall Manager**.

---

## 1. Architectural Principles (UFW-First)

The core philosophy of the **UFW-First Architecture** is that the firewall on each remote VPS is the **single source of truth** for rule configurations. 
* **State De-duplication**: The local controller database does not persist or replicate the list of active ports or rules per node. It only stores connection configuration for the nodes (IP, SSH details) and reusable IP Groups (collection of static IPs).
* **Live Querying**: When a user accesses the dashboard or node details page, the controller dynamically fetches UFW rules and connectivity status directly from the node via SSH.
* **No Database-Firewall Drift**: Because the database does not hold any "intended" firewall state, it is impossible for the UI and the remote node to get out of sync.

### Logical Layers
1. **Presentation Layer**: HTML5 + Jinja2 templates styled with custom CSS variables (dark mode first). Interactions are handled using **HTMX** to swap out partial HTML segments without page reloads.
2. **Application Layer (FastAPI)**: Translates REST API actions into database operations (for metadata and IP groups) and SSH execution workflows.
3. **Execution Layer (SSH Executor)**: Connects to nodes and invokes a restricted helper script `/usr/local/sbin/snell-fwctl` on the remote host.
4. **Data Layer (SQLite + aiosqlite)**: Stores configuration metadata (nodes, IP groups, operations logs).

---

## 2. Simplified Database Schema

The database schema is stripped of the intermediate association table (`node_relay_groups`) since nodes no longer associate directly with groups in the database; rather, groups of IPs are expanded and deployed directly as individual UFW rules on specified ports.

### Schema Schema Structure (SQL DDL)

```sql
-- 1. Nodes Connection Metadata
CREATE TABLE IF NOT EXISTS nodes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    host        TEXT NOT NULL,
    ssh_port    INTEGER DEFAULT 22,
    ssh_user    TEXT DEFAULT 'snellmgr',
    snell_port  INTEGER NOT NULL,
    snell_conf  TEXT DEFAULT '/root/snelldocker/snell-conf/snell.conf',
    remark      TEXT DEFAULT '',
    enabled     INTEGER DEFAULT 1,
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 2. Reusable IP Groups (renamed from relay_groups)
CREATE TABLE IF NOT EXISTS ip_groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    remark      TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now'))
);

-- 3. IP Group Items (renamed from relay_ips)
CREATE TABLE IF NOT EXISTS ip_group_items (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    group_id    INTEGER NOT NULL REFERENCES ip_groups(id) ON DELETE CASCADE,
    ip_cidr     TEXT NOT NULL,
    note        TEXT DEFAULT '',
    created_at  TEXT DEFAULT (datetime('now')),
    UNIQUE(group_id, ip_cidr)
);

-- 4. Centralized Operation Log
CREATE TABLE IF NOT EXISTS op_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    node_id     INTEGER REFERENCES nodes(id) ON DELETE SET NULL,
    node_name   TEXT,
    action      TEXT NOT NULL,
    target      TEXT,
    detail      TEXT,
    success     INTEGER NOT NULL,
    created_at  TEXT DEFAULT (datetime('now'))
);
```

### Table Relationships & Indexes
* **`ip_group_items`**: Linked via foreign key `group_id` with `ON DELETE CASCADE` to `ip_groups`. A unique constraint is placed on `(group_id, ip_cidr)` to prevent duplicate IP entries in the same group.
* **`op_logs`**: Weak association to `nodes`. Deleting a node preserves operation logs but sets the `node_id` to `NULL`.

---

## 3. Refactored API Routes in `main.py`

Routes are designed to handle page requests (returning full Jinja2 templates) and HTMX requests (returning HTML fragments).

### Detailed Route Specifications

| Method | Path | Payload (Form/Query) | Return Type | Logical Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **GET** | `/` | None | HTML (Full Page) | Renders the Dashboard listing nodes and recent global operations logs. |
| **GET** | `/nodes/{id}` | None | HTML (Full Page) | Renders the Node Details page containing container divs that load the live status and **Port Cards Grid** via HTMX. |
| **POST** | `/api/nodes/{id}/ports` | `port` (int), `protocol` (str: `tcp`/`udp`/`both`), `tag` (str: tag label), `initial_ip` (str, optional), `initial_ip_group_id` (int, optional) | HTML (Partial Grid) | Opens a port. If an initial IP is provided, it whitelists it. If an IP Group is selected, it expands it and whitelists all contained IPs. Returns the updated **Port Cards Grid** HTML fragment. |
| **DELETE** | `/api/nodes/{id}/ports/{port}` | None | HTML (Partial Grid) | Closes a port. Queries all rules on the port, sorts their rule numbers descending, deletes them sequentially on the remote node via SSH, and returns the updated **Port Cards Grid** HTML. |
| **POST** | `/api/nodes/{id}/ports/{port}/ips` | `ip_cidr` (str, optional), `group_id` (int, optional), `comment` (str, optional) | HTML (Port Card) | Whitelists an IP/CIDR or all IPs of a Group on this port. Instructs the node to add UFW rules. Returns the updated single **Port Card** HTML. |
| **DELETE** | `/api/nodes/{id}/ports/{port}/rules/{num}` | None | HTML (Port Card) | Deletes a specific UFW rule by its rule number `#num`. Reloads UFW on the node. Returns the updated single **Port Card** HTML. |
| **GET** | `/api/nodes/{id}/summary` | None | HTML (Partial Card) | Asynchronously fetches live UFW status and parses allowed ports. Used to populate node card information on the Dashboard. |

### SSH Command Mapping
The FastAPI router coordinates with the node's firewall by executing these specific commands:
* **Rule Retrieval**: `snell-fwctl list all`
* **Adding Rule**: `snell-fwctl add <ip> <port> [tcp|udp|both]`
* **Deleting Rule Number**: `snell-fwctl delete_num <rule_number>`
* **Status Check**: `snell-fwctl status`

---

## 4. Jinja2 Templating System Updates

To support the UFW-First architecture, the templates are refactored to focus on **ports** as the primary entity instead of flat rules lists.

### A. Dashboard (`dashboard.html`)
The node grid uses HTMX to lazy-load node statistics (status dot, port counts, and tags) to prevent blocking the initial page load:
```html
<!-- dashboard.html -->
<div class="node-grid">
  {% for node in nodes %}
  <a href="/nodes/{{ node.id }}" class="node-card-link">
    <div class="node-card" id="node-card-{{ node.id }}" 
         hx-get="/api/nodes/{{ node.id }}/summary" 
         hx-trigger="load" 
         hx-swap="outerHTML">
      <!-- Loading Skeleton -->
      <div class="node-card-header">
        <span class="spinner"></span>
        <span class="node-card-name">{{ node.name }}</span>
      </div>
      <div class="node-card-meta">
        <span class="mono text-secondary">{{ node.host }}</span>
        <span class="text-tertiary">正在获取 UFW 状态...</span>
      </div>
    </div>
  </a>
  {% endfor %}
</div>
```

### B. Node Summary Partial (`partials/node_summary.html`)
Returned by `/api/nodes/{id}/summary`:
```html
<div class="node-card">
  <div class="node-card-header">
    <span class="status-dot {% if status.online %}online{% else %}offline{% endif %}" 
          title="UFW Status: {{ status.ufw_status }}"></span>
    <span class="node-card-name">{{ node.name }}</span>
  </div>
  <div class="node-card-meta">
    <div class="row">🌐 <span class="mono">{{ node.host }}</span></div>
    <div class="row">⚡ Uptime: <span>{{ status.uptime }}</span></div>
    <div class="row">
      🔌 ports: 
      {% if status.ports %}
        {% for p in status.ports %}
          <span class="tag tag-info mono">{{ p }}</span>
        {% endfor %}
      {% else %}
        <span class="text-tertiary">无开放端口</span>
      {% endif %}
    </div>
  </div>
</div>
```

### C. Node Details (`node_detail.html`)
Renders the layout container, sticky sidebar for opening new ports, and loads the active **Port Cards Grid**:
```html
<!-- node_detail.html -->
<div class="node-detail-layout">
  <!-- Main Column: Port Cards Grid -->
  <div class="port-grid-section">
    <div class="section-header">
      <h2>开放服务端口</h2>
      <button class="btn btn-ghost btn-sm" 
              hx-get="/api/nodes/{{ node.id }}/ports" 
              hx-target="#port-cards-grid" 
              hx-swap="innerHTML">🔄 刷新端口</button>
    </div>
    <div id="port-cards-grid">
      <!-- Lazy load Port Cards Grid -->
      <div class="loading-overlay" 
           hx-get="/api/nodes/{{ node.id }}/ports" 
           hx-trigger="load" 
           hx-swap="outerHTML">
        <span class="spinner"></span> 正在读取 UFW 开放端口...
      </div>
    </div>
  </div>

  <!-- Sidebar Column: Open Port Form -->
  <div class="sidebar-section">
    <div class="card sticky">
      <h3>➕ 开启新端口</h3>
      <form hx-post="/api/nodes/{{ node.id }}/ports" 
            hx-target="#port-cards-grid" 
            hx-swap="innerHTML" 
            hx-indicator="#open-port-spinner">
        <div class="form-group">
          <label class="form-label">端口号</label>
          <input type="number" name="port" class="form-input mono" placeholder="如 8388" required min="1" max="65535">
        </div>
        <div class="form-group">
          <label class="form-label">协议</label>
          <select name="protocol" class="form-select">
            <option value="both">TCP + UDP (推荐)</option>
            <option value="tcp">TCP</option>
            <option value="udp">UDP</option>
          </select>
        </div>
        <div class="form-group">
          <label class="form-label">服务标签</label>
          <input type="text" name="tag" class="form-input" placeholder="如 Snell, Shadow, SSH">
        </div>
        
        <div class="divider"></div>
        
        <!-- Optional Initial Whitelist -->
        <h4 class="sub-header">安全限制（可选）</h4>
        <div class="form-group">
          <label class="form-label">单 IP 或 CIDR</label>
          <input type="text" name="initial_ip" class="form-input mono" placeholder="如 123.45.67.89">
        </div>
        <div class="form-group">
          <label class="form-label">或选择现有 IP 中转组</label>
          <select name="initial_ip_group_id" class="form-select">
            <option value="">-- 不关联中转组 --</option>
            {% for group in ip_groups %}
            <option value="{{ group.id }}">{{ group.name }} ({{ group.items_count }} IP)</option>
            {% endfor %}
          </select>
        </div>
        
        <button type="submit" class="btn btn-primary w-full">
          <span class="spinner htmx-indicator" id="open-port-spinner"></span>
          开启端口并授权
        </button>
      </form>
    </div>
  </div>
</div>
```

### D. Port Card Template (`partials/port_card.html`)
Modular component representing a single port card. It lists all active rules targeting this specific port.
```html
<!-- partials/port_card.html -->
<div class="port-card glass-card" id="port-card-{{ data.port }}">
  <!-- Card Header -->
  <div class="port-card-header">
    <div>
      <div class="port-number font-mono">
        {{ data.port }} <span class="proto-suffix">/{{ data.protocol_label }}</span>
      </div>
      <span class="service-tag tag tag-info">{{ data.tag | default('自定义规则') }}</span>
    </div>
    <button class="btn-close-port" 
            hx-delete="/api/nodes/{{ node.id }}/ports/{{ data.port }}" 
            hx-target="#port-cards-grid" 
            hx-confirm="确定要关闭端口 {{ data.port }} 并删除其下所有 UFW 规则吗？"
            title="关闭端口">✕</button>
  </div>

  <!-- Whitelisted IP List -->
  <div class="whitelist-section">
    <div class="section-label">已放行源地址</div>
    <div class="pill-container">
      {% for rule in data.rules %}
      <div class="ip-pill">
        <span class="ip-address font-mono">{{ rule.ip }}</span>
        <span class="ip-proto text-sm">{{ rule.proto | upper }}</span>
        <button class="btn-remove-ip" 
                hx-delete="/api/nodes/{{ node.id }}/ports/{{ data.port }}/rules/{{ rule.num }}" 
                hx-target="#port-card-{{ data.port }}" 
                hx-swap="outerHTML"
                title="删除此条规则">✕</button>
      </div>
      {% else %}
      <span class="no-rules text-tertiary">全端口开放 (Anywhere)</span>
      {% endfor %}
    </div>
  </div>

  <!-- Quick Add IP Form -->
  <div class="port-card-footer">
    <form hx-post="/api/nodes/{{ node.id }}/ports/{{ data.port }}/ips" 
          hx-target="#port-card-{{ data.port }}" 
          hx-swap="outerHTML" 
          class="form-quick-add">
      <input type="text" name="ip_cidr" class="form-input form-input-sm font-mono" placeholder="IP / CIDR 或中转组" required>
      <select name="group_id" class="form-select form-select-sm" style="display:none;">
        <!-- Hidden or toggled based on input prefix/type -->
      </select>
      <button type="submit" class="btn btn-secondary btn-sm">+ 放行</button>
    </form>
  </div>
</div>
```

---

## 5. Styling Details (`style.css`)

The interface uses a dark/light hybrid styling setup, using CSS Variables (`:root`) for color tokens. Below are the styling definitions that govern the layout of the port cards and UFW-first views.

### CSS Layout Rules & Tokens

```css
/* Custom properties additions */
:root {
  --port-card-bg: var(--bg-surface);
  --port-card-border: var(--border-default);
  --pill-bg: var(--bg-inset);
  --pill-text: var(--text-primary);
  --pill-border: var(--border-subtle);
  
  --shadow-port-card: 0 4px 20px rgba(0, 0, 0, 0.15);
}

[data-theme="dark"] {
  --port-card-bg: #161b22;
  --port-card-border: #30363d;
  --pill-bg: #21262d;
  --pill-text: #c9d1d9;
  --pill-border: #30363d;
}

/* Layout Grid */
.node-detail-layout {
  display: grid;
  grid-template-columns: 1fr 340px;
  gap: 24px;
  align-items: start;
}

.port-grid-section {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

#port-cards-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 16px;
}

/* Port Card Container */
.port-card {
  background: var(--port-card-bg);
  border: 1px solid var(--port-card-border);
  border-radius: var(--radius-lg);
  padding: 18px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  min-height: 220px;
  transition: all var(--transition-normal);
  box-shadow: var(--shadow-port-card);
  position: relative;
}

.port-card:hover {
  transform: translateY(-2px);
  border-color: var(--accent);
  box-shadow: 0 8px 30px rgba(110, 142, 251, 0.12);
}

/* Port Card Header */
.port-card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}

.port-number {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--text-primary);
  line-height: 1.2;
}

.port-number .proto-suffix {
  font-size: 0.8rem;
  font-weight: 500;
  color: var(--accent-text);
  margin-left: 2px;
}

.btn-close-port {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 1rem;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.btn-close-port:hover {
  color: var(--error);
  background: var(--error-bg);
}

/* Whitelist Section */
.whitelist-section {
  flex-grow: 1;
  margin-bottom: 18px;
}

.whitelist-section .section-label {
  font-size: 0.75rem;
  text-transform: uppercase;
  color: var(--text-secondary);
  font-weight: 700;
  letter-spacing: 0.5px;
  margin-bottom: 8px;
}

.pill-container {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  max-height: 120px;
  overflow-y: auto;
  padding-right: 4px;
}

/* IP Pill */
.ip-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: var(--pill-bg);
  border: 1px solid var(--pill-border);
  color: var(--pill-text);
  padding: 3px 8px;
  border-radius: var(--radius-sm);
  font-size: 0.8rem;
  transition: all var(--transition-fast);
}

.ip-pill:hover {
  border-color: var(--text-secondary);
}

.ip-pill .ip-proto {
  font-size: 0.7rem;
  opacity: 0.6;
}

.btn-remove-ip {
  background: transparent;
  border: none;
  color: var(--text-tertiary);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0 2px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.btn-remove-ip:hover {
  color: var(--error);
}

/* Footer / Quick-Add form */
.port-card-footer {
  border-top: 1px solid var(--border-subtle);
  padding-top: 12px;
}

.form-quick-add {
  display: flex;
  gap: 6px;
}

.form-quick-add .form-input {
  flex-grow: 1;
  font-size: 0.8rem;
  padding: 6px 10px;
}

/* Sidebar Box Styling */
.sidebar-section .card.sticky {
  position: sticky;
  top: 76px;
  z-index: 10;
}

.sidebar-section h3 {
  font-size: 1.1rem;
  font-weight: 700;
  margin-bottom: 16px;
}

.sidebar-section .divider {
  height: 1px;
  background: var(--border-subtle);
  margin: 16px 0;
}

.sidebar-section .sub-header {
  font-size: 0.85rem;
  font-weight: 600;
  color: var(--text-secondary);
  margin-bottom: 10px;
}

@media (max-width: 992px) {
  .node-detail-layout {
    grid-template-columns: 1fr;
  }
  .sidebar-section .card.sticky {
    position: static;
  }
}
```

---

## 6. Implementation Code Outlines

Below are structured Python outlines mapping out function signatures, type definitions, docstrings, and logic steps to guide the implementation.

### A. Code Outline for `database.py`

```python
"""SQLite database layer for Snell UFW Manager.
Refactored to support renamed ip_groups & ip_group_items.
"""

import os
from typing import List, Dict, Optional, Any
import aiosqlite

DB_PATH: str = os.environ.get("SNELL_DB", "data/snell_manager.db")

async def init_db() -> None:
    """Initialize SQLite database with WAL and foreign key support."""
    # Ensure folder path exists, run executescript(SCHEMA)
    pass

def _get_db() -> aiosqlite.Connection:
    """Returns database connection context manager."""
    return aiosqlite.connect(DB_PATH)

# ==========================================
# Nodes Operations
# ==========================================

async def get_all_nodes() -> List[Dict[str, Any]]:
    """Fetch all remote VPS node credentials from db."""
    # SELECT * FROM nodes ORDER BY id
    pass

async def get_node(node_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve details of a single node by id."""
    # SELECT * FROM nodes WHERE id = ?
    pass

async def create_node(
    name: str, host: str, ssh_port: int, ssh_user: str, snell_port: int, snell_conf: str, remark: str = ""
) -> int:
    """Insert new VPS details and return inserted ID."""
    pass

async def update_node(node_id: int, **kwargs: Any) -> None:
    """Dynamically update node properties."""
    pass

async def delete_node(node_id: int) -> None:
    """Delete a node from the database."""
    pass

# ==========================================
# IP Groups Operations (Renamed from Relay Groups)
# ==========================================

async def get_all_ip_groups() -> List[Dict[str, Any]]:
    """Get all groups and load their items recursively."""
    # SELECT * FROM ip_groups ORDER BY id
    # Loop over groups and fetch corresponding items from ip_group_items
    pass

async def get_ip_group(group_id: int) -> Optional[Dict[str, Any]]:
    """Fetch a single group along with its items list."""
    # SELECT * FROM ip_groups WHERE id = ?
    # SELECT * FROM ip_group_items WHERE group_id = ?
    pass

async def create_ip_group(name: str, remark: str = "") -> int:
    """Add a new IP group (e.g. 'Home IPs')."""
    # INSERT INTO ip_groups (name, remark)
    pass

async def update_ip_group(group_id: int, **kwargs: Any) -> None:
    """Update group details."""
    pass

async def delete_ip_group(group_id: int) -> None:
    """Delete group, cascade triggers delete of all items."""
    pass

async def add_ip_group_item(group_id: int, ip_cidr: str, note: str = "") -> int:
    """Insert an IP address or CIDR network into a group."""
    # INSERT INTO ip_group_items (group_id, ip_cidr, note)
    pass

async def delete_ip_group_item(item_id: int) -> None:
    """Remove a specific IP address from a group."""
    # DELETE FROM ip_group_items WHERE id = ?
    pass

# ==========================================
# Operation Logs
# ==========================================

async def add_op_log(
    node_id: Optional[int], node_name: str, action: str, target: str = "", detail: str = "", success: bool = True
) -> None:
    """Write an operation result into central log table."""
    pass

async def get_op_logs(node_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve log history for display."""
    pass
```

### B. Code Outline for `main.py`

```python
"""FastAPI Application Server — UFW-First Router implementation."""

from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from . import database as db
from .config import load_config
from .ssh_executor import SSHExecutor

app = FastAPI(title="Snell UFW Manager")
templates = Jinja2Templates(directory="templates")
config = load_config()
ssh = SSHExecutor(config)

# ==========================================
# Page Endpoints
# ==========================================

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Render Dashboard page.
    Nodes list is loaded from database, while their UFW status
    is loaded asynchronously via individual client HTMX requests.
    """
    # nodes = await db.get_all_nodes()
    # logs = await db.get_op_logs(limit=10)
    # return templates.TemplateResponse("dashboard.html", ...)
    pass

@app.get("/nodes/{node_id}", response_class=HTMLResponse)
async def node_detail(request: Request, node_id: int):
    """Render Node Detail page outline.
    Loads node configuration and available IP groups (for whitelist select dropdowns).
    """
    # node = await db.get_node(node_id)
    # ip_groups = await db.get_all_ip_groups()
    # logs = await db.get_op_logs(node_id=node_id, limit=10)
    # return templates.TemplateResponse("node_detail.html", ...)
    pass

# ==========================================
# HTMX Partials & Summary
# ==========================================

@app.get("/api/nodes/{node_id}/summary", response_class=HTMLResponse)
async def api_node_summary(request: Request, node_id: int):
    """SSH query node status and list ports, return card summary.
    Used for dashboard lazy loading.
    """
    # node = await db.get_node(node_id)
    # status = await ssh.test_connection(node)  # Contains hostname, ufw_status, uptime etc.
    # whitelist = await ssh.get_whitelist(node)
    # # Extract list of unique port numbers from UFW rules list
    # return templates.TemplateResponse("partials/node_summary.html", ...)
    pass

@app.get("/api/nodes/{node_id}/ports", response_class=HTMLResponse)
async def api_port_cards_grid(request: Request, node_id: int):
    """Retrieve live rules from VPS and construct the Port Cards Grid."""
    # node = await db.get_node(node_id)
    # raw_rules = await ssh.get_whitelist(node)
    # # Group raw_rules by port:
    # # port_data = {port: { "port": port, "protocol_label": "tcp/udp", "rules": [rule1, rule2] }}
    # # return templates.TemplateResponse("partials/port_cards_grid.html", ...)
    pass

# ==========================================
# Port Operations API
# ==========================================

@app.post("/api/nodes/{node_id}/ports", response_class=HTMLResponse)
async def api_open_port(
    request: Request,
    node_id: int,
    port: int = Form(...),
    protocol: str = Form("both"),
    tag: Optional[str] = Form(""),
    initial_ip: Optional[str] = Form(None),
    initial_ip_group_id: Optional[int] = Form(None)
):
    """Open a new UFW service port.
    1. Connect via SSH.
    2. Add initial IP if provided (run `add <ip> <port> <protocol>`).
    3. If initial_ip_group_id provided, fetch all items from database,
       and execute `add <ip> <port> <protocol>` for each item.
    4. Write operation log.
    5. Return updated port cards grid template response.
    """
    pass

@app.delete("/api/nodes/{node_id}/ports/{port}", response_class=HTMLResponse)
async def api_close_port(request: Request, node_id: int, port: int):
    """Close port completely.
    1. Fetch live whitelist rules for node.
    2. Filter rules matching the target port.
    3. Sort rule numbers DESCENDING.
    4. Loop and delete each rule by executing `delete_num <num>`.
    5. Write operation log.
    6. Return updated port cards grid.
    """
    pass

# ==========================================
# IP Whitelist Operations
# ==========================================

@app.post("/api/nodes/{node_id}/ports/{port}/ips", response_class=HTMLResponse)
async def api_whitelist_ip(
    request: Request,
    node_id: int,
    port: int,
    ip_cidr: str = Form(...)
):
    """Whitelist a single IP/CIDR or expand an entire IP Group on this port.
    1. Check if ip_cidr corresponds to an IP Group name in the database.
    2. If it matches a group, extract all IP items. Iterate and run SSH `add` for each.
    3. If it's a standalone IP/CIDR, run SSH `add <ip_cidr> <port>`.
    4. Write operation log.
    5. Re-query rules for this port.
    6. Return single updated port card HTML partial.
    """
    pass

@app.delete("/api/nodes/{node_id}/ports/{port}/rules/{num}", response_class=HTMLResponse)
async def api_remove_rule(request: Request, node_id: int, port: int, num: int):
    """Remove a single specific rule number from UFW.
    1. Run SSH `delete_num <num>` on node.
    2. Log operation.
    3. Re-query and construct port data.
    4. Return single updated port card HTML partial.
    """
    pass
```
