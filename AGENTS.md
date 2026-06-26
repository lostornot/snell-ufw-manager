# AGENTS.md

## Project Goal
- Build `snell-ufw-control`: a local-only control center for managing Snell Server nodes and Snell-port UFW allowlists across multiple VPS nodes.
- This is not a general VPS panel and not a public web admin panel.

## Current Status
- Requirements and V1 design are defined.
- Controller CRUD UI for nodes, profiles, relay groups, relay IP entries, policies, audit logs, desired Snell config, access candidate promotion, current UFW whitelist display, and node detail remote action forms for UFW plus full Snell lifecycle is implemented.
- Database models, validation, SSH executor, per-node operation locks, node-side UFW command planning/backups/candidate parsing, node-side Snell install/config/service/logs/restore helpers, packaging files, and tests are implemented.
- Snell binary downloads require an explicit `snell_download_url`; non-dry-run install without `custom_binary_path` or `snell_download_url` is refused.

## Setup and Run Commands
- Install local dev env: `python3 -m venv .venv && . .venv/bin/activate && pip install -e ".[dev]"`
- Run controller locally: `.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8899`
- Test all: `.venv/bin/pytest -v`
- Test M1 models/validation: `.venv/bin/pytest tests/test_models.py tests/test_validation.py -v`
- Syntax check scripts: `bash -n scripts/install-controller.sh && bash -n scripts/install-node.sh`
- Syntax check node tools: `python3 -m py_compile node/snell-fwctl node/snellctl node/ufwctl`

## Directory Guide
- `app/`: FastAPI application, business services, templates, static assets.
- `node/`: node-side restricted tools, including `snell-fwctl`, `snellctl`, and `ufwctl` assets.
- `systemd/`: controller systemd unit.
- `scripts/`: controller and node installation scripts.
- `data/`: local SQLite database and runtime data. Treat as sensitive.
- `docs/superpowers/specs/`: design specs and planning documents.

## Technology Choices
- Python FastAPI.
- SQLite.
- Jinja2 + HTMX.
- systemd.
- Remote execution through OpenSSH subprocess calls.
- No React, Vue, or Node.js for V1.

## Project-Specific Rules
- Web service must default to `127.0.0.1:8899`.
- Access is intended through SSH Tunnel.
- Controller must still require minimal authentication, session cookies, and CSRF protection for state-changing requests.
- Do not add a public management port.
- Control Center must not expose arbitrary shell execution.
- Remote node access uses a dedicated `snellmgr` user, not root SSH login.
- `sudoers` must only allow `snellmgr` to execute `/usr/local/sbin/snell-fwctl` with `NOPASSWD`; the security boundary is the restricted command allowlist, not an interactive sudo password.
- Node-side execution must be limited to fixed subcommands.
- Remote execution must use subprocess argument arrays only; never use `shell=True` or string-composed SSH commands.
- Prefer OpenSSH config aliases for node connections; do not store private key material or passphrases in SQLite.
- UFW management must only modify rules with comment prefix `snell-control:`.
- Always backup `/etc/ufw/user.rules` and `/etc/ufw/user6.rules` before modifying UFW.
- Snell configuration and PSK may be stored in SQLite; protect `data/` permissions.
- Audit logs must redact PSKs, passwords, private keys, raw config text, and Snell config lines containing `psk`.
- UFW apply must not automatically enable UFW. Enabling UFW is a separate dangerous action with lockout checks.
- Snell versions must be explicit or pinned; do not blindly install latest.
- Only one write operation per node may run at a time.

## Safety and Permissions
- Do not commit secrets, private keys, tokens, real VPS credentials, PSKs, or local database contents.
- Ask before changing the architecture or adding major dependencies.
- Avoid destructive operations on UFW, systemd, or Snell outside the explicit managed scope.

## Known Pitfalls
- Do not let the project drift into a general VPS monitoring/control panel.
- Do not use free-form remote shell commands for convenience.
- Do not batch-push profile edits to existing nodes automatically; profiles are for creation/copying in V1.
- Do not call candidate IPs "recommended"; they are only suspected access sources and require confirmation before promotion.

## Done Checklist
- Requirements remain aligned with the local-only security model.
- Tests/lint/typecheck pass once commands exist.
- Documentation updated when behavior changes.
- No secrets or unrelated files included.
