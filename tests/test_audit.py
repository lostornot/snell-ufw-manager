from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db import Base
from app.services.audit import redact_sensitive, write_audit


def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_redact_sensitive_masks_keys_and_snell_psk_lines() -> None:
    redacted = redact_sensitive(
        {
            "psk": "secret",
            "nested": {"password": "pw", "ok": "visible"},
            "config_text": "listen = ::0:23456\npsk = secret\n",
            "lines": ["abc", "psk = another-secret"],
        }
    )

    assert redacted["psk"] == "********"
    assert redacted["nested"]["password"] == "********"
    assert redacted["nested"]["ok"] == "visible"
    assert redacted["config_text"] == "********"
    assert redacted["lines"] == ["abc", "psk = ********"]


def test_write_audit_redacts_payloads_before_storage() -> None:
    db = session()

    audit = write_audit(
        db,
        actor="admin",
        action="snell.config_apply",
        summary="apply config",
        success=True,
        request_json={"psk": "secret", "config_text": "psk = secret\n"},
        result_json={"private_key": "nope", "ok": True},
    )

    assert audit.request_json == {"psk": "********", "config_text": "********"}
    assert audit.result_json == {"private_key": "********", "ok": True}

