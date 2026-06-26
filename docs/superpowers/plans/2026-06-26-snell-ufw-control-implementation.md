# snell-ufw-control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build V1 of a local-only Snell Server and UFW allowlist control center with restricted SSH-based node execution.

**Architecture:** FastAPI owns the local Web UI, SQLite stores desired state and audit logs, and OpenSSH subprocess calls invoke a single restricted remote sudo entry point. Node-side Python tools split Snell service management from UFW rule management while preserving one sudo command surface.

**Tech Stack:** Python, FastAPI, SQLite, SQLAlchemy, Jinja2, HTMX, pytest, OpenSSH subprocess, systemd, UFW.

---

## Source Documents

- Spec: `docs/superpowers/specs/2026-06-26-snell-ufw-control-design.md`
- Project rules: `AGENTS.md`

## Planned File Structure

- `pyproject.toml`: package metadata, dependencies, pytest config, formatting config.
- `app/main.py`: FastAPI app creation, router registration, static/template setup.
- `app/config.py`: environment config, bind host/port, data paths, auth secrets.
- `app/db.py`: SQLite engine/session setup and database initialization.
- `app/models.py`: SQLAlchemy models.
- `app/schemas.py`: Pydantic validation schemas.
- `app/security.py`: admin-token login, sessions, CSRF helpers.
- `app/locks.py`: per-node operation lock service.
- `app/services/audit.py`: audit writing and secret redaction.
- `app/services/nodes.py`: node CRUD, config profiles, status persistence.
- `app/services/relay_groups.py`: relay group and relay IP management.
- `app/services/policies.py`: node policy resolution and UFW payload generation.
- `app/services/ssh_executor.py`: OpenSSH subprocess runner.
- `app/services/ufw_parser.py`: managed UFW comment parsing and normalization helpers.
- `app/templates/`: Jinja2 templates for dashboard, login, nodes, profiles, relay groups, policies, audit logs.
- `app/static/`: minimal CSS and HTMX vendor file if vendored.
- `node/snell-fwctl`: restricted Python dispatcher.
- `node/snellctl`: Snell install/config/status/service/log tooling.
- `node/ufwctl`: UFW list/apply/backup/restore/candidates/enable tooling.
- `systemd/snell-ufw-control.service`: controller unit.
- `scripts/install-controller.sh`: controller installer.
- `scripts/install-node.sh`: node installer.
- `tests/`: controller tests.
- `tests_node/`: node-side tool tests with fixtures.

## Milestone M1: Database, Models, Validation, and Migrations

**Files:**
- Create: `pyproject.toml`
- Create: `app/__init__.py`
- Create: `app/config.py`
- Create: `app/db.py`
- Create: `app/models.py`
- Create: `app/schemas.py`
- Create: `tests/test_models.py`
- Create: `tests/test_validation.py`

- [ ] Create the Python project skeleton with FastAPI, SQLAlchemy, Pydantic, Jinja2, pytest, and httpx dependencies.

Run:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

Expected: editable install succeeds.

- [ ] Implement `app/config.py` with defaults `HOST=127.0.0.1`, `PORT=8898`, `DATA_DIR=data`, `DATABASE_URL=sqlite:///data/snell-ufw-control.db`, `ADMIN_TOKEN`, and `SESSION_SECRET`.

- [ ] Implement `app/db.py` with `engine`, `SessionLocal`, `Base`, `get_db()`, and `init_db()`.

- [ ] Implement SQLAlchemy models for `Node`, `SnellConfigProfile`, `RelayGroup`, `RelayIP`, `NodePolicy`, `AccessCandidate`, `AuditLog`, and `OperationLock`.

- [ ] Implement Pydantic schemas that validate:
  - `host` and `ssh_alias` do not begin with `-`;
  - `ssh_user` matches a conservative Linux username pattern;
  - `ssh_port` and `snell_port` are `1..65535`;
  - at least one of `enable_tcp` and `enable_udp` is true;
  - Relay IP values pass Python `ipaddress.ip_network(value, strict=False)`;
  - private key contents and passphrases are not accepted as model fields.

- [ ] Write tests proving valid node, profile, relay IP, and policy records can be created.

- [ ] Write tests proving invalid ports, invalid users, host values beginning with `-`, invalid CIDR strings, and both protocols disabled are rejected.

- [ ] Run:

```bash
pytest tests/test_models.py tests/test_validation.py -v
```

Expected: all M1 tests pass.

## Milestone M2: Controller UI Skeleton, Authentication, Sessions, and CSRF

**Files:**
- Create: `app/main.py`
- Create: `app/security.py`
- Create: `app/templates/base.html`
- Create: `app/templates/login.html`
- Create: `app/templates/dashboard.html`
- Create: `app/templates/nodes/index.html`
- Create: `app/templates/nodes/detail.html`
- Create: `app/templates/relay_groups/index.html`
- Create: `app/templates/policies/index.html`
- Create: `app/templates/audit/index.html`
- Create: `app/static/app.css`
- Create: `tests/test_auth.py`
- Create: `tests/test_templates.py`

- [ ] Implement FastAPI app setup with static files, Jinja2 templates, DB initialization hook, and routers grouped by UI area.

- [ ] Implement admin-token login:
  - GET `/login` renders a form;
  - POST `/login` accepts `ADMIN_TOKEN`;
  - successful login writes a signed session cookie;
  - failed login writes an audit entry without storing submitted token text.

- [ ] Implement CSRF:
  - session contains a CSRF token;
  - all state-changing POST routes require the token;
  - failed CSRF returns 403 and writes a redacted audit entry.

- [ ] Set session cookies to `HttpOnly` and `SameSite=Lax` or `SameSite=Strict`.

- [ ] Create read-only skeleton pages for dashboard, nodes, relay groups, policies, and audit logs.

- [ ] Add state-changing stub buttons/forms with CSRF hidden inputs but no remote execution yet.

- [ ] Write tests:
  - unauthenticated dashboard redirects to login;
  - valid token creates a session;
  - invalid token is rejected;
  - POST without CSRF is rejected;
  - POST with CSRF reaches a stub handler.

- [ ] Run:

```bash
pytest tests/test_auth.py tests/test_templates.py -v
```

Expected: all M2 tests pass.

## Milestone M3: SSH Executor and Connection Model

**Files:**
- Create: `app/services/ssh_executor.py`
- Modify: `app/models.py`
- Modify: `app/schemas.py`
- Create: `tests/test_ssh_executor.py`

- [ ] Implement `SSHCommandResult` with `returncode`, `stdout`, `stderr`, `parsed_json`, `timed_out`, and `json_error`.

- [ ] Implement namespace/subcommand allowlists matching the spec.

- [ ] Implement alias-based command construction:

```python
["ssh", alias, "sudo", "/usr/local/sbin/snell-fwctl", namespace, subcommand]
```

- [ ] Implement field-based command construction:

```python
["ssh", "-p", str(port), f"{user}@{host}", "sudo", "/usr/local/sbin/snell-fwctl", namespace, subcommand]
```

- [ ] Add optional `-i ssh_key_path` support when field-based mode is used. Validate path syntax and never accept key content.

- [ ] Use `subprocess.run(..., input=json_payload, text=True, capture_output=True, timeout=connect_timeout)` with no shell.

- [ ] Capture timeout, non-zero exit, stdout, stderr, and JSON parse failures.

- [ ] Write tests that monkeypatch `subprocess.run` and assert command arrays exactly match the expected lists.

- [ ] Write tests proving `shell=True`, `os.system`, and string-composed command paths are absent by code inspection or behavior.

- [ ] Write tests proving bad namespace, bad subcommand, host beginning with `-`, alias beginning with `-`, and invalid ports are rejected before subprocess execution.

- [ ] Run:

```bash
pytest tests/test_ssh_executor.py -v
```

Expected: all M3 tests pass.

## Milestone M4: Node-Side `snell-fwctl`, `snellctl`, and `ufwctl`

**Files:**
- Create: `node/snell-fwctl`
- Create: `node/snellctl`
- Create: `node/ufwctl`
- Create: `tests_node/test_snell_fwctl.py`
- Create: `tests_node/test_node_json_contract.py`

- [ ] Implement `node/snell-fwctl` as a Python dispatcher.

- [ ] Enforce namespace allowlist: `snell`, `ufw`.

- [ ] Enforce subcommand allowlists:
  - `snell`: `install`, `status`, `start`, `stop`, `restart`, `config-get`, `config-apply`, `logs`, `backup`, `restore`;
  - `ufw`: `list`, `apply`, `backup`, `restore`, `candidates`, `enable`.

- [ ] Read stdin as JSON for commands that accept payloads. Reject invalid JSON with normalized JSON error output.

- [ ] Run internal tools with argument arrays and fixed environment `PATH=/usr/sbin:/usr/bin:/sbin:/bin`.

- [ ] Implement normalized JSON success and error helpers shared by node tools.

- [ ] Implement `node/snellctl` command stubs that return structured JSON for each allowed subcommand.

- [ ] Implement `node/ufwctl` command stubs that return structured JSON for each allowed subcommand.

- [ ] Write tests proving unknown namespaces, unknown subcommands, extra pass-through arguments, invalid JSON, and internal command failures return normalized JSON.

- [ ] Run:

```bash
pytest tests_node/test_snell_fwctl.py tests_node/test_node_json_contract.py -v
```

Expected: all M4 tests pass.

## Milestone M5: UFW Policy Apply, Parsing, Backups, and Safety Tests

**Files:**
- Create: `app/services/ufw_parser.py`
- Modify: `app/services/policies.py`
- Modify: `node/ufwctl`
- Create: `tests/test_policies.py`
- Create: `tests/test_ufw_parser.py`
- Create: `tests_node/test_ufwctl.py`
- Create: `tests_node/fixtures/ufw_status_numbered.txt`
- Create: `tests_node/fixtures/user.rules`
- Create: `tests_node/fixtures/user6.rules`

- [ ] Implement managed comment format:

```text
snell-control:node:<node_id>:group:<group_id>:port:<port>:proto:<tcp|udp>
```

- [ ] Implement policy payload generation from `NodePolicy` and `RelayIP`, creating TCP and/or UDP entries based on node protocol flags.

- [ ] Implement `ufw list` to return active/inactive status, default incoming policy, SSH allow status, warnings, and current managed rules.

- [ ] Implement `ufw apply` to backup `/etc/ufw/user.rules` and `/etc/ufw/user6.rules` before mutation.

- [ ] Implement managed rule deletion that only matches:
  - `snell-control:` prefix;
  - same node id;
  - same port;
  - same protocol;
  - `allow` action.

- [ ] If using `ufw status numbered`, delete matching numbered rules in reverse numeric order.

- [ ] Preserve all unrelated rules, including unrelated rules for the same port without the managed comment.

- [ ] Add desired allow rules for each source/protocol pair and reload UFW only when UFW is active.

- [ ] Ensure `ufw apply` never runs `ufw enable`.

- [ ] Implement `ufw enable` as a separate command that refuses to proceed unless SSH allow and emergency SSH CIDR checks pass.

- [ ] Write tests proving unrelated rules are preserved, numbered deletions occur in reverse order, inactive UFW produces a warning, and unsafe enable is refused.

- [ ] Run:

```bash
pytest tests/test_policies.py tests/test_ufw_parser.py tests_node/test_ufwctl.py -v
```

Expected: all M5 tests pass.

## Milestone M6: Snell Install, Config, Status, Logs, and Version Pinning

**Files:**
- Modify: `node/snellctl`
- Modify: `app/services/nodes.py`
- Modify: `app/templates/nodes/detail.html`
- Create: `tests_node/test_snellctl.py`
- Create: `tests/test_nodes_service.py`

- [ ] Implement explicit Snell version/channel/architecture handling. Supported V1 choices include `v4.1.1`, `v5.x`, and controlled custom binary path.

- [ ] Refuse install payloads that request implicit `latest`.

- [ ] Implement config rendering with port, PSK, TCP/UDP flags, and advanced config text.

- [ ] Before config changes, backup current Snell config to a timestamped path.

- [ ] Implement install flow:
  - install requested binary;
  - verify checksum when available;
  - write config;
  - install or update systemd service;
  - run daemon reload;
  - enable and restart Snell;
  - run status check;
  - roll back config on failure when a known-good backup exists.

- [ ] Implement `status`, `start`, `stop`, `restart`, `config-get`, `config-apply`, `logs`, `backup`, and `restore`.

- [ ] Update node detail UI with install, start, stop, restart, apply config, and log controls using CSRF.

- [ ] Write tests proving version pinning is required, backup occurs before config write, failed restart rolls back config, and status output normalizes systemd results.

- [ ] Run:

```bash
pytest tests/test_nodes_service.py tests_node/test_snellctl.py -v
```

Expected: all M6 tests pass.

## Milestone M7: Audit Logs, Secret Redaction, Operation Locks, and Candidate Promotion

**Files:**
- Create: `app/services/audit.py`
- Create: `app/locks.py`
- Modify: `app/services/nodes.py`
- Modify: `app/services/policies.py`
- Modify: `app/templates/audit/index.html`
- Modify: `app/templates/nodes/detail.html`
- Create: `tests/test_audit.py`
- Create: `tests/test_locks.py`
- Create: `tests/test_candidates.py`

- [ ] Implement `redact_sensitive(obj)` for dicts, lists, strings, and nested values.

- [ ] Redact keys `psk`, `password`, `private_key`, `config_text`, `desired_config_text`, and future obvious secret markers.

- [ ] Redact any Snell config line containing `psk`.

- [ ] Ensure `AuditLog.request_json` and `AuditLog.result_json` are redacted before database insertion.

- [ ] Hide PSK display by default in UI and redact config previews.

- [ ] Implement SQLite-backed per-node operation lock for write operations.

- [ ] Apply locks to `snell install`, `snell config-apply`, `snell start`, `snell stop`, `snell restart`, `snell restore`, `ufw apply`, `ufw restore`, and `ufw enable`.

- [ ] Allow concurrent read operations: `status`, `logs`, `ufw list`, and `ufw candidates`.

- [ ] Implement candidate refresh/upsert and promotion flow.

- [ ] Label candidate UI as `疑似访问来源 / Access Candidates`.

- [ ] Require confirmation before candidate promotion into a relay group.

- [ ] Display IP, protocol, port, first seen, last seen, hit count, and source for each candidate.

- [ ] Write tests proving audit logs never store full PSKs, locks block concurrent writes, read operations bypass locks, and promotion requires confirmation.

- [ ] Run:

```bash
pytest tests/test_audit.py tests/test_locks.py tests/test_candidates.py -v
```

Expected: all M7 tests pass.

## Milestone M8: Packaging Scripts, systemd Units, README, and End-to-End Verification

**Files:**
- Create: `scripts/install-controller.sh`
- Create: `scripts/install-node.sh`
- Create: `systemd/snell-ufw-control.service`
- Create: `README.md`
- Modify: `AGENTS.md`
- Create: `tests/test_packaging_files.py`

- [ ] Implement `install-controller.sh`:
  - create app/data directories;
  - install Python dependencies;
  - create `data/` mode `700`;
  - create database file mode `600`;
  - generate `ADMIN_TOKEN` and `SESSION_SECRET` when absent;
  - install systemd service;
  - bind to `127.0.0.1:8898` by default.

- [ ] Implement `install-node.sh`:
  - check `python3`;
  - create `snellmgr`;
  - install `snell-fwctl`, `snellctl`, and `ufwctl`;
  - set `root:root` ownership;
  - remove group/world write permissions;
  - write sudoers rule for `NOPASSWD: /usr/local/sbin/snell-fwctl` only;
  - validate sudoers syntax;
  - print SSH config alias guidance.

- [ ] Implement `systemd/snell-ufw-control.service` with bind host `127.0.0.1` and port `8898`.

- [ ] Write README with:
  - project scope and non-goals;
  - SSH Tunnel access;
  - controller install;
  - node install;
  - SSH alias setup;
  - Snell version pinning;
  - UFW inactive warning;
  - backup/restore behavior;
  - security notes for `data/`.

- [ ] Write packaging tests that assert scripts contain required security settings and service does not bind `0.0.0.0`.

- [ ] Run full verification:

```bash
pytest -v
```

Expected: all tests pass.

- [ ] Run script syntax checks:

```bash
bash -n scripts/install-controller.sh
bash -n scripts/install-node.sh
python3 -m py_compile node/snell-fwctl node/snellctl node/ufwctl
```

Expected: all syntax checks pass.

## Final Verification Before Release

- [ ] Confirm web service defaults to `127.0.0.1:8898`.
- [ ] Confirm no React, Vue, or Node.js dependency was added.
- [ ] Confirm SSH executor never uses `shell=True`.
- [ ] Confirm sudoers grants only `/usr/local/sbin/snell-fwctl`.
- [ ] Confirm `snell-fwctl` rejects unknown namespace and subcommands.
- [ ] Confirm UFW apply preserves unrelated rules.
- [ ] Confirm UFW apply does not enable UFW.
- [ ] Confirm AuditLog stores redacted payloads.
- [ ] Confirm Snell install refuses implicit latest.
- [ ] Confirm candidate promotion requires confirmation.
- [ ] Confirm documentation reflects the final commands and security model.
