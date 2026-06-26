# Node Bootstrap Wizard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a safe node initialization section that explains how to install the restricted node tool and lets the controller check whether a node is ready.

**Architecture:** Add a narrow `system check` subcommand to `snell-fwctl` and a matching controller action. The UI shows copyable install-node steps and the latest check result from audit logs; it does not bootstrap a root VPS or run arbitrary shell.

**Tech Stack:** Python FastAPI, Jinja2, SQLite audit logs, OpenSSH subprocess executor, Python node scripts, pytest.

---

### Task 1: Node Tool System Check

**Files:**
- Modify: `node/snell-fwctl`
- Create: `node/systemctl`
- Test: `tests_node/test_systemctl.py`
- Test: `tests_node/test_snell_fwctl.py`

- [ ] Write tests proving `snell-fwctl system check` is allowed and returns JSON with `snell_fwctl`, `snellctl`, `ufwctl`, `running_user`, `effective_user`, `snell_binary`, `ufw_binary`, and `ufw_active`.
- [ ] Verify the tests fail because `system` is not an allowed namespace.
- [ ] Implement `node/systemctl` with only a `check` subcommand.
- [ ] Update `snell-fwctl` allowlist and dispatcher to call `systemctl`.
- [ ] Run node tests and confirm they pass.

### Task 2: Controller Remote Check Action

**Files:**
- Modify: `app/services/ssh_executor.py`
- Modify: `app/services/remote_actions.py`
- Modify: `app/main.py`
- Test: `tests/test_ssh_executor.py`
- Test: `tests/test_remote_actions.py`
- Test: `tests/test_node_detail_actions.py`

- [ ] Write tests proving `system check` is allowed in the SSH executor.
- [ ] Write tests proving `check_node_environment()` sends `system/check`, audits `node.check`, and returns remote JSON.
- [ ] Write tests proving node detail renders a `/nodes/{id}/check-environment` form and POST redirects back to the node page.
- [ ] Implement the allowlist, service function, import, and route.
- [ ] Run targeted controller tests and confirm they pass.

### Task 3: Initialization UI

**Files:**
- Modify: `app/main.py`
- Modify: `app/templates/nodes/detail.html`
- Modify: `app/static/app.css`
- Test: `tests/test_node_detail_actions.py`

- [ ] Write tests proving node detail shows “节点初始化”, install-node deployment steps, and latest `node.check` audit results.
- [ ] Pass `latest_node_check` to the detail template.
- [ ] Render bootstrap instructions and a compact status table.
- [ ] Run targeted UI tests and confirm they pass.

### Task 4: Verification and Push

**Files:**
- Modify: repository state only.

- [ ] Run `.venv/bin/pytest -q`.
- [ ] Run `bash -n scripts/install-controller.sh`.
- [ ] Run `bash -n scripts/install-node.sh`.
- [ ] Run `python3 -m py_compile node/snell-fwctl node/snellctl node/ufwctl node/systemctl`.
- [ ] Commit the implementation.
- [ ] Push `GPT-5.5` to origin.
