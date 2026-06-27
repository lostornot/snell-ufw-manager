# snell-ufw-control

`snell-ufw-control` is a local-only Control Center for Snell Server node management and Snell-port UFW allowlist control. It is not a general VPS panel and not a public web panel.

## Scope

- Add, edit, and delete Snell VPS nodes.
- Manage Snell install, config, status, start/stop/restart, logs, backup, and restore through a restricted node tool.
- Manage UFW allow rules for Snell TCP and UDP ports.
- Add, edit, and delete relay groups; add and delete relay IP/CIDR entries.
- Manage node policies, access candidates, current Snell-port UFW allowlists, and audit logs.
- Promote a suspected access source into a relay group only after explicit confirmation.
- Preserve unrelated UFW rules.

## Access Model

The controller binds to `127.0.0.1:8898` by default. Access it through SSH Tunnel:

```bash
ssh -L 8898:127.0.0.1:8898 controller-host
```

Then open:

```text
http://127.0.0.1:8898
```

The controller creates a signed local session cookie automatically and requires CSRF protection for state-changing requests.

## Controller Install

```bash
git clone -b GPT-5.5 https://github.com/lostornot/snell-ufw-manager.git snell-ufw-manager-by-gpt
cd snell-ufw-manager-by-gpt
sudo scripts/install-controller.sh
```

The installer uses `/opt/snell-ufw-manager-by-gpt` by default, creates `data/` with mode `700`, stores the SQLite database with mode `600`, and generates `SESSION_SECRET` in `.env` when absent.

On startup, the controller creates missing tables and applies lightweight SQLite column migrations for existing databases. Keep a copy of `data/snell-ufw-control.db` before major upgrades.

The controller service runs as the restricted `snell-ufw-control` system user. Put controller-side SSH config and keys under:

```text
/opt/snell-ufw-manager-by-gpt/.ssh
```

For example:

```bash
sudo install -d -m 700 -o snell-ufw-control -g snell-ufw-control /opt/snell-ufw-manager-by-gpt/.ssh
sudo install -m 600 -o snell-ufw-control -g snell-ufw-control ~/.ssh/snell_control_ed25519 /opt/snell-ufw-manager-by-gpt/.ssh/snell_control_ed25519
sudo install -m 600 -o snell-ufw-control -g snell-ufw-control ~/.ssh/config /opt/snell-ufw-manager-by-gpt/.ssh/config
```

## Node Install

```bash
git clone -b GPT-5.5 https://github.com/lostornot/snell-ufw-manager.git snell-ufw-manager-by-gpt
cd snell-ufw-manager-by-gpt
sudo scripts/install-node.sh
```

The node installer creates the `snellmgr` user and installs:

```text
/usr/local/sbin/snell-fwctl
/usr/local/lib/snell-ufw-control/snellctl
/usr/local/lib/snell-ufw-control/ufwctl
```

`sudoers` grants only:

```text
snellmgr ALL=(root) NOPASSWD: /usr/local/sbin/snell-fwctl
```

The security boundary is the restricted command allowlist, root-owned tool files, JSON stdin validation, and no arbitrary shell support.

To remove only the managed node-side tools and sudoers entry:

```bash
sudo scripts/uninstall-node.sh
```

To also remove the `snellmgr` user created by the node installer:

```bash
sudo REMOVE_USER=1 scripts/uninstall-node.sh
```

The uninstaller intentionally does not stop Snell, delete Snell config, or modify UFW rules.

In the controller UI, adding a node only records its desired state and SSH connection information. For a new VPS, open the node detail page and use the `节点初始化` section:

1. Run `scripts/install-node.sh` on the VPS to install the restricted node tools.
2. Return to the controller and click `检查节点环境`.
3. Install Snell Server from the node detail page.
4. Apply Snell config and UFW allowlist rules.

## SSH Alias

Prefer OpenSSH config aliases and do not store private key material in SQLite:

```sshconfig
Host us-snell-1
    HostName 203.0.113.10
    User snellmgr
    Port 22
    IdentityFile ~/.ssh/snell_control_ed25519
```

Use `ssh_alias=us-snell-1` when adding the node.

## Snell Version

Snell version is desired state. Do not blindly install latest. V1 supports explicit choices such as `v4.1.1`, `v5.x`, or a controlled custom binary path.

The controller UI stores desired Snell config per node. Users can start from a default config, paste their own config, reuse PSKs across nodes when intended, and apply the saved config through the restricted node tool.

## UFW Safety

`ufw apply` writes managed allow rules but does not enable UFW. If UFW is inactive, the UI must show:

```text
UFW inactive: current whitelist rules are not enforcing access.
```

Enabling UFW is a separate dangerous action requiring SSH lockout checks and confirmation.

The node detail page exposes `启用 UFW` separately from `应用白名单`. It requires:

- confirming SSH access is already allowed;
- entering an emergency SSH CIDR;
- explicit confirmation before the node tool runs `ufw --force enable`.

Managed comments use:

```text
snell-control:node:<node_id>:group:<group_id>:port:<port>:proto:<tcp|udp>
```

Only matching managed rules may be deleted.

## Backups

Before modifying UFW, node tools back up:

```text
/etc/ufw/user.rules
/etc/ufw/user6.rules
```

Before applying Snell config, node tools back up the existing Snell config and roll back when restart fails.

## Audit Redaction

Audit logs redact PSKs, passwords, private keys, raw config text, desired config text, and Snell config lines containing `psk`.
