"""
Cloud Mail 域名状态持久化与同步工具。
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from ...database.models import EmailService as EmailServiceModel
from ...database.session import get_db


logger = logging.getLogger(__name__)
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]


def get_disabled_domains_file() -> Path:
    override = os.environ.get("CLOUD_MAIL_DISABLED_DOMAINS_FILE", "").strip()
    if override:
        return Path(override)
    return WORKSPACE_ROOT / "data" / "cloud_mail_disabled_domains.json"


def normalize_domain(domain: str) -> str:
    return str(domain or "").strip().lower()


def load_disabled_domains() -> set[str]:
    path = get_disabled_domains_file()
    if not path.exists():
        return set()

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("读取禁用域名列表失败 %s: %s", path, exc)
        return set()

    if isinstance(payload, dict):
        raw_domains = payload.get("domains") or []
    elif isinstance(payload, list):
        raw_domains = payload
    else:
        raw_domains = []

    return {
        normalized
        for item in raw_domains
        if (normalized := normalize_domain(str(item)))
    }


def save_disabled_domains(domains: Iterable[str]) -> list[str]:
    normalized = sorted({
        normalized
        for item in domains
        if (normalized := normalize_domain(str(item)))
    })
    path = get_disabled_domains_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"domains": normalized}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return normalized


def set_domain_disabled(domain: str, disabled: bool) -> dict[str, object]:
    normalized = normalize_domain(domain)
    if not normalized:
        raise ValueError("域名不能为空")

    domains = load_disabled_domains()
    if disabled:
        domains.add(normalized)
    else:
        domains.discard(normalized)
    saved = save_disabled_domains(domains)
    return {
        "domain": normalized,
        "disabled": disabled,
        "domains": saved,
        "count": len(saved),
    }


def is_domain_disabled(domain: str, disabled_domains: set[str] | None = None) -> bool:
    normalized = normalize_domain(domain)
    if not normalized:
        return False
    current = disabled_domains if disabled_domains is not None else load_disabled_domains()
    return normalized in current


def _service_matches_domain(service: EmailServiceModel, domain: str) -> bool:
    config = service.config or {}

    base_url = str(config.get("base_url") or "").strip()
    if base_url:
        parsed = urlparse(base_url)
        if normalize_domain(parsed.hostname or "") == domain:
            return True

    configured_domains = config.get("domain")
    if isinstance(configured_domains, list):
        return any(normalize_domain(item) == domain for item in configured_domains)
    return normalize_domain(str(configured_domains or "")) == domain


def sync_imported_cloud_mail_service_state(domain: str, enabled: bool) -> int:
    normalized = normalize_domain(domain)
    if not normalized:
        return 0

    updated = 0
    with get_db() as db:
        services = db.query(EmailServiceModel).filter(
            EmailServiceModel.service_type == "cloud_mail"
        ).all()
        for service in services:
            if not _service_matches_domain(service, normalized):
                continue
            service.enabled = enabled
            updated += 1

        if updated:
            db.commit()

    return updated
