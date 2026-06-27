from __future__ import annotations

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import SessionLocal, configure_database, init_db
from app.models import AccessCandidate, AuditLog, Node, RelayGroup
from app.security import (
    SESSION_COOKIE,
    create_session_cookie,
    get_session,
    verify_csrf,
)
from app.services.audit import write_audit
from app.services.candidates import promote_candidate
from app.services.nodes import (
    create_node,
    create_profile,
    delete_node,
    list_nodes,
    list_profiles,
    update_node,
    update_node_config,
)
from app.services.policies import build_ufw_apply_payload, create_policy, list_policies
from app.services.relay_groups import (
    add_relay_ip,
    create_relay_group,
    delete_relay_group,
    delete_relay_ip,
    list_relay_groups,
    update_relay_group,
)
from app.services.remote_actions import (
    check_node_environment,
    get_snell_config,
    install_snell,
    read_snell_logs,
    apply_snell_config,
    apply_ufw_policy,
    enable_ufw,
    refresh_access_candidates,
    refresh_node_status,
    refresh_ufw_list,
    restore_snell_config,
    run_snell_service_action,
)
from app.schemas import NodeCreate, NodePolicyCreate, RelayGroupCreate, RelayIPCreate, SnellConfigProfileCreate

templates = Jinja2Templates(directory="app/templates")


def get_session_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_app() -> FastAPI:
    get_settings.cache_clear()
    settings = get_settings()
    configure_database(settings.database_url)
    init_db()

    app = FastAPI(title="snell-ufw-control")
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory="app/static"), name="static")

    @app.exception_handler(ValidationError)
    def validation_error_handler(request: Request, exc: ValidationError) -> PlainTextResponse:
        return PlainTextResponse(str(exc), status_code=400)

    def set_local_session_cookie(response: Response, cookie_value: str | None) -> Response:
        if cookie_value is None:
            return response
        response.set_cookie(
            SESSION_COOKIE,
            cookie_value,
            httponly=True,
            samesite="lax",
        )
        return response

    def authenticated_context(request: Request, title: str) -> dict[str, object]:
        session = get_session(request)
        if session is None or session.get("authenticated") is not True:
            cookie_value, csrf_token = create_session_cookie(settings)
            request.state.local_session_cookie = cookie_value
            session = {"authenticated": True, "csrf_token": csrf_token}
        return {
            "title": title,
            "csrf_token": session["csrf_token"],
            "bind_address": f"{settings.host}:{settings.port}",
        }

    def render_authenticated(request: Request, template_name: str, context: dict[str, object]) -> HTMLResponse:
        response = templates.TemplateResponse(request, template_name, context)
        return set_local_session_cookie(response, getattr(request.state, "local_session_cookie", None))

    def node_connectivity(node: Node) -> dict[str, str]:
        if node.last_error:
            return {"key": "offline", "label": "离线", "badge_class": "badge-warn"}
        if node.last_seen_at:
            return {"key": "online", "label": "在线", "badge_class": "badge-ok"}
        return {"key": "unchecked", "label": "未检查", "badge_class": "badge-off"}

    def node_connectivity_map(nodes: list[Node]) -> dict[int, dict[str, str]]:
        return {node.id: node_connectivity(node) for node in nodes}

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request) -> Response:
        with SessionLocal() as db:
            nodes_ = list_nodes(db)
            status_map = node_connectivity_map(nodes_)
            status_counts = {
                "online": sum(1 for item in status_map.values() if item["key"] == "online"),
                "offline": sum(1 for item in status_map.values() if item["key"] == "offline"),
                "unchecked": sum(1 for item in status_map.values() if item["key"] == "unchecked"),
            }
            context = authenticated_context(request, "总览")
            context |= {
                "node_count": len(nodes_),
                "relay_group_count": db.query(RelayGroup).count(),
                "audit_count": db.query(AuditLog).count(),
                "nodes": nodes_,
                "node_status_map": status_map,
                "node_status_counts": status_counts,
            }
            return render_authenticated(request, "dashboard.html", context)

    @app.get("/nodes", response_class=HTMLResponse)
    def nodes(request: Request, db: Session = Depends(get_session_db)) -> HTMLResponse:
        context = authenticated_context(request, "节点")
        nodes_ = list_nodes(db)
        context["nodes"] = nodes_
        context["node_status_map"] = node_connectivity_map(nodes_)
        return render_authenticated(
            request,
            "nodes/index.html",
            context,
        )

    @app.post("/nodes", dependencies=[Depends(verify_csrf)])
    def nodes_create(
        name: str = Form(),
        host: str = Form(default=""),
        ssh_alias: str = Form(default=""),
        ssh_port: int | None = Form(default=22),
        ssh_user: str = Form(default="snellmgr"),
        snell_port: int = Form(),
        snell_version: str = Form(default=""),
        snell_sha256: str = Form(default=""),
        psk: str = Form(default=""),
        enable_tcp: str | None = Form(default=None),
        enable_udp: str | None = Form(default=None),
        enabled: str | None = Form(default=None),
        remark: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        data = NodeCreate(
            name=name,
            host=host or None,
            ssh_alias=ssh_alias or None,
            ssh_port=ssh_port,
            ssh_user=ssh_user or None,
            snell_port=snell_port,
            snell_version=snell_version or None,
            snell_sha256=snell_sha256 or None,
            psk=psk or None,
            enable_tcp=enable_tcp == "on",
            enable_udp=enable_udp == "on",
            enabled=enabled == "on",
            remark=remark or None,
        )
        node = create_node(db, data)
        write_audit(
            db,
            actor="admin",
            action="node.create",
            target_type="node",
            target_id=node.id,
            summary=f"created node {node.name}",
            request_json=data.model_dump(),
            result_json={"id": node.id},
            success=True,
        )
        return RedirectResponse(f"/nodes/{node.id}", status_code=303)

    @app.get("/nodes/{node_id}", response_class=HTMLResponse)
    def node_detail(
        node_id: int,
        request: Request,
        db: Session = Depends(get_session_db),
    ) -> HTMLResponse:
        node = db.get(Node, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="node not found")
        latest_ufw_list = (
            db.query(AuditLog)
            .filter(
                AuditLog.target_type == "node",
                AuditLog.target_id == node.id,
                AuditLog.action == "ufw.list",
                AuditLog.success.is_(True),
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        latest_node_check = (
            db.query(AuditLog)
            .filter(
                AuditLog.target_type == "node",
                AuditLog.target_id == node.id,
                AuditLog.action == "node.check",
                AuditLog.success.is_(True),
            )
            .order_by(AuditLog.id.desc())
            .first()
        )
        context = authenticated_context(request, node.name)
        context |= {
            "node": node,
            "policy_preview": build_ufw_apply_payload(node),
            "relay_groups": list_relay_groups(db),
            "latest_ufw_list": latest_ufw_list.result_json if latest_ufw_list else None,
            "latest_node_check": latest_node_check.result_json if latest_node_check else None,
            "candidates": db.query(AccessCandidate)
            .filter(AccessCandidate.node_id == node.id)
            .order_by(AccessCandidate.last_seen_at.desc())
            .limit(50)
            .all(),
            "audit_logs": db.query(AuditLog)
            .filter(AuditLog.target_type == "node", AuditLog.target_id == node.id)
            .order_by(AuditLog.id.desc())
            .limit(20)
            .all(),
        }
        return render_authenticated(request, "nodes/detail.html", context)

    @app.post("/nodes/{node_id}/edit", dependencies=[Depends(verify_csrf)])
    def node_edit(
        node_id: int,
        name: str = Form(),
        host: str = Form(default=""),
        ssh_alias: str = Form(default=""),
        ssh_port: int | None = Form(default=22),
        ssh_user: str = Form(default="snellmgr"),
        snell_port: int = Form(),
        snell_version: str = Form(default=""),
        snell_sha256: str = Form(default=""),
        psk: str = Form(default=""),
        enable_tcp: str | None = Form(default=None),
        enable_udp: str | None = Form(default=None),
        enabled: str | None = Form(default=None),
        remark: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        existing = db.get(Node, node_id)
        if existing is None:
            raise HTTPException(status_code=404, detail="node not found")
        data = NodeCreate(
            name=name,
            host=host or None,
            ssh_alias=ssh_alias or None,
            ssh_port=ssh_port,
            ssh_user=ssh_user or None,
            snell_port=snell_port,
            snell_version=snell_version or None,
            snell_sha256=snell_sha256 or None,
            psk=psk or None,
            enable_tcp=enable_tcp == "on",
            enable_udp=enable_udp == "on",
            enabled=enabled == "on",
            remark=remark or None,
            desired_config_text=existing.desired_config_text,
        )
        node = update_node(db, node_id, data)
        write_audit(
            db,
            actor="admin",
            action="node.update",
            target_type="node",
            target_id=node.id,
            summary=f"updated node {node.name}",
            request_json=data.model_dump(),
            result_json={"id": node.id},
            success=True,
        )
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/config", dependencies=[Depends(verify_csrf)])
    def node_config_update(
        node_id: int,
        desired_config_text: str = Form(default=""),
        psk: str = Form(default=""),
        snell_version: str = Form(default=""),
        snell_sha256: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        try:
            node = update_node_config(
                db,
                node_id,
                desired_config_text=desired_config_text or None,
                psk=psk or None,
                snell_version=snell_version or None,
                snell_sha256=snell_sha256 or None,
            )
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        write_audit(
            db,
            actor="admin",
            action="node.config_update",
            target_type="node",
            target_id=node.id,
            summary=f"updated desired Snell config for {node.name}",
            request_json={
                "desired_config_text": desired_config_text or None,
                "psk": psk or None,
                "snell_version": snell_version or None,
                "snell_sha256": snell_sha256 or None,
            },
            result_json={"id": node.id},
            success=True,
        )
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/delete", dependencies=[Depends(verify_csrf)])
    def node_delete(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        node = db.get(Node, node_id)
        if node is None:
            raise HTTPException(status_code=404, detail="node not found")
        node_name = node.name
        delete_node(db, node_id)
        write_audit(
            db,
            actor="admin",
            action="node.delete",
            target_type="node",
            target_id=node_id,
            summary=f"deleted node {node_name}",
            result_json={"id": node_id},
            success=True,
        )
        return RedirectResponse("/nodes", status_code=303)

    def run_node_action(action, db: Session, node_id: int) -> RedirectResponse:
        action(db, node_id)
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/refresh-status", dependencies=[Depends(verify_csrf)])
    def node_refresh_status(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(refresh_node_status, db, node_id)

    @app.post("/nodes/{node_id}/check-environment", dependencies=[Depends(verify_csrf)])
    def node_check_environment(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(check_node_environment, db, node_id)

    @app.post("/nodes/{node_id}/install-snell", dependencies=[Depends(verify_csrf)])
    def node_install_snell(
        node_id: int,
        custom_binary_path: str = Form(default=""),
        snell_download_url: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        install_snell(
            db,
            node_id,
            custom_binary_path=custom_binary_path or None,
            snell_download_url=snell_download_url or None,
        )
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/snell-start", dependencies=[Depends(verify_csrf)])
    def node_snell_start(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(lambda session, nid: run_snell_service_action(session, nid, "start"), db, node_id)

    @app.post("/nodes/{node_id}/snell-stop", dependencies=[Depends(verify_csrf)])
    def node_snell_stop(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(lambda session, nid: run_snell_service_action(session, nid, "stop"), db, node_id)

    @app.post("/nodes/{node_id}/snell-restart", dependencies=[Depends(verify_csrf)])
    def node_snell_restart(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(lambda session, nid: run_snell_service_action(session, nid, "restart"), db, node_id)

    @app.post("/nodes/{node_id}/snell-config-get", dependencies=[Depends(verify_csrf)])
    def node_snell_config_get(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(get_snell_config, db, node_id)

    @app.post("/nodes/{node_id}/snell-logs", dependencies=[Depends(verify_csrf)])
    def node_snell_logs(
        node_id: int,
        lines: int = Form(default=100),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        read_snell_logs(db, node_id, lines=lines)
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/snell-restore", dependencies=[Depends(verify_csrf)])
    def node_snell_restore(
        node_id: int,
        backup_path: str = Form(),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        restore_snell_config(db, node_id, backup_path)
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/ufw-list", dependencies=[Depends(verify_csrf)])
    def node_ufw_list(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(refresh_ufw_list, db, node_id)

    @app.post("/nodes/{node_id}/apply-ufw", dependencies=[Depends(verify_csrf)])
    def node_apply_ufw(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(apply_ufw_policy, db, node_id)

    @app.post("/nodes/{node_id}/enable-ufw", dependencies=[Depends(verify_csrf)])
    def node_enable_ufw(
        node_id: int,
        emergency_ssh_cidr: str = Form(default=""),
        ssh_allowed: str | None = Form(default=None),
        confirmed: str | None = Form(default=None),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        enable_ufw(
            db,
            node_id,
            emergency_ssh_cidr=emergency_ssh_cidr,
            ssh_allowed=ssh_allowed == "on",
            confirmed=confirmed == "on",
        )
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.post("/nodes/{node_id}/apply-config", dependencies=[Depends(verify_csrf)])
    def node_apply_config(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(apply_snell_config, db, node_id)

    @app.post("/nodes/{node_id}/candidates", dependencies=[Depends(verify_csrf)])
    def node_candidates(node_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        return run_node_action(refresh_access_candidates, db, node_id)

    @app.post("/nodes/{node_id}/candidates/{candidate_id}/promote", dependencies=[Depends(verify_csrf)])
    def node_candidate_promote(
        node_id: int,
        candidate_id: int,
        relay_group_id: int = Form(),
        confirmed: str | None = Form(default=None),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        candidate = db.get(AccessCandidate, candidate_id)
        if candidate is None or candidate.node_id != node_id:
            raise HTTPException(status_code=404, detail="candidate not found")
        if db.get(RelayGroup, relay_group_id) is None:
            raise HTTPException(status_code=404, detail="relay group not found")
        try:
            relay_ip = promote_candidate(
                db,
                candidate_id=candidate_id,
                relay_group_id=relay_group_id,
                confirmed=confirmed == "on",
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        write_audit(
            db,
            actor="admin",
            action="candidate.promote",
            target_type="node",
            target_id=node_id,
            summary=f"promoted candidate {candidate.ip} to relay group {relay_group_id}",
            request_json={"candidate_id": candidate_id, "relay_group_id": relay_group_id},
            result_json={"relay_ip_id": relay_ip.id, "value": relay_ip.value},
            success=True,
        )
        return RedirectResponse(f"/nodes/{node_id}", status_code=303)

    @app.get("/profiles", response_class=HTMLResponse)
    def profiles(request: Request, db: Session = Depends(get_session_db)) -> HTMLResponse:
        context = authenticated_context(request, "配置预设")
        context["profiles"] = list_profiles(db)
        return render_authenticated(request, "profiles/index.html", context)

    @app.post("/profiles", dependencies=[Depends(verify_csrf)])
    def profiles_create(
        name: str = Form(),
        snell_port: int = Form(),
        snell_version: str = Form(default=""),
        snell_sha256: str = Form(default=""),
        psk: str = Form(default=""),
        enable_tcp: str | None = Form(default=None),
        enable_udp: str | None = Form(default=None),
        config_text: str = Form(default=""),
        remark: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        data = SnellConfigProfileCreate(
            name=name,
            snell_port=snell_port,
            snell_version=snell_version or None,
            snell_sha256=snell_sha256 or None,
            psk=psk or None,
            enable_tcp=enable_tcp == "on",
            enable_udp=enable_udp == "on",
            config_text=config_text or None,
            remark=remark or None,
        )
        profile = create_profile(db, data)
        write_audit(
            db,
            actor="admin",
            action="profile.create",
            target_type="profile",
            target_id=profile.id,
            summary=f"created profile {profile.name}",
            request_json=data.model_dump(),
            result_json={"id": profile.id},
            success=True,
        )
        return RedirectResponse("/profiles", status_code=303)

    @app.get("/relay-groups", response_class=HTMLResponse)
    def relay_groups(request: Request, db: Session = Depends(get_session_db)) -> HTMLResponse:
        context = authenticated_context(request, "中转组")
        context["relay_groups"] = list_relay_groups(db)
        return render_authenticated(
            request,
            "relay_groups/index.html",
            context,
        )

    @app.post("/relay-groups", dependencies=[Depends(verify_csrf)])
    def relay_groups_create(
        name: str = Form(),
        remark: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        data = RelayGroupCreate(name=name, remark=remark or None)
        group = create_relay_group(db, data)
        write_audit(
            db,
            actor="admin",
            action="relay_group.create",
            target_type="relay_group",
            target_id=group.id,
            summary=f"created relay group {group.name}",
            request_json=data.model_dump(),
            result_json={"id": group.id},
            success=True,
        )
        return RedirectResponse("/relay-groups", status_code=303)

    @app.post("/relay-groups/{group_id}/edit", dependencies=[Depends(verify_csrf)])
    def relay_groups_edit(
        group_id: int,
        name: str = Form(),
        remark: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        data = RelayGroupCreate(name=name, remark=remark or None)
        try:
            group = update_relay_group(db, group_id, data)
        except ValueError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        write_audit(
            db,
            actor="admin",
            action="relay_group.update",
            target_type="relay_group",
            target_id=group.id,
            summary=f"updated relay group {group.name}",
            request_json=data.model_dump(),
            result_json={"id": group.id},
            success=True,
        )
        return RedirectResponse("/relay-groups", status_code=303)

    @app.post("/relay-groups/{group_id}/delete", dependencies=[Depends(verify_csrf)])
    def relay_groups_delete(group_id: int, db: Session = Depends(get_session_db)) -> RedirectResponse:
        group = db.get(RelayGroup, group_id)
        if group is None:
            raise HTTPException(status_code=404, detail="relay group not found")
        group_name = group.name
        delete_relay_group(db, group_id)
        write_audit(
            db,
            actor="admin",
            action="relay_group.delete",
            target_type="relay_group",
            target_id=group_id,
            summary=f"deleted relay group {group_name}",
            result_json={"id": group_id},
            success=True,
        )
        return RedirectResponse("/relay-groups", status_code=303)

    @app.post("/relay-groups/{group_id}/ips", dependencies=[Depends(verify_csrf)])
    def relay_ips_create(
        group_id: int,
        value: str = Form(),
        remark: str = Form(default=""),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        if db.get(RelayGroup, group_id) is None:
            raise HTTPException(status_code=404, detail="relay group not found")
        data = RelayIPCreate(relay_group_id=group_id, value=value, remark=remark or None)
        relay_ip = add_relay_ip(db, data)
        write_audit(
            db,
            actor="admin",
            action="relay_ip.create",
            target_type="relay_ip",
            target_id=relay_ip.id,
            summary=f"added relay IP {relay_ip.value}",
            request_json=data.model_dump(),
            result_json={"id": relay_ip.id},
            success=True,
        )
        return RedirectResponse("/relay-groups", status_code=303)

    @app.post("/relay-groups/{group_id}/ips/{relay_ip_id}/delete", dependencies=[Depends(verify_csrf)])
    def relay_ips_delete(
        group_id: int,
        relay_ip_id: int,
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        relay_ip = db.get(RelayGroup, group_id)
        if relay_ip is None:
            raise HTTPException(status_code=404, detail="relay group not found")
        ip_row = None
        for item in relay_ip.relay_ips:
            if item.id == relay_ip_id:
                ip_row = item
                break
        if ip_row is None:
            raise HTTPException(status_code=404, detail="relay IP not found")
        value = ip_row.value
        delete_relay_ip(db, relay_ip_id)
        write_audit(
            db,
            actor="admin",
            action="relay_ip.delete",
            target_type="relay_ip",
            target_id=relay_ip_id,
            summary=f"deleted relay IP {value}",
            result_json={"id": relay_ip_id, "value": value},
            success=True,
        )
        return RedirectResponse("/relay-groups", status_code=303)

    @app.get("/policies", response_class=HTMLResponse)
    def policies(request: Request, db: Session = Depends(get_session_db)) -> HTMLResponse:
        nodes = list_nodes(db)
        groups = list_relay_groups(db)
        policies_ = list_policies(db)
        previews = {node.id: build_ufw_apply_payload(node) for node in nodes}
        context = authenticated_context(request, "访问策略")
        context |= {
            "nodes": nodes,
            "relay_groups": groups,
            "policies": policies_,
            "previews": previews,
        }
        return render_authenticated(
            request,
            "policies/index.html",
            context,
        )

    @app.post("/policies", dependencies=[Depends(verify_csrf)])
    def policies_create(
        node_id: int = Form(),
        relay_group_id: int = Form(),
        enabled: str | None = Form(default=None),
        db: Session = Depends(get_session_db),
    ) -> RedirectResponse:
        data = NodePolicyCreate(
            node_id=node_id,
            relay_group_id=relay_group_id,
            enabled=enabled == "on",
        )
        policy = create_policy(db, data)
        write_audit(
            db,
            actor="admin",
            action="policy.create",
            target_type="policy",
            target_id=policy.id,
            summary=f"bound node {node_id} to relay group {relay_group_id}",
            request_json=data.model_dump(),
            result_json={"id": policy.id},
            success=True,
        )
        return RedirectResponse("/policies", status_code=303)

    @app.get("/audit-logs", response_class=HTMLResponse)
    def audit_logs(request: Request, db: Session = Depends(get_session_db)) -> HTMLResponse:
        context = authenticated_context(request, "操作日志")
        context["audit_logs"] = db.query(AuditLog).order_by(AuditLog.id.desc()).limit(100).all()
        return render_authenticated(
            request,
            "audit/index.html",
            context,
        )

    return app


app = create_app()
