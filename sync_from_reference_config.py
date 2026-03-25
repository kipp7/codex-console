"""
将参考项目的 config.json 同步到 codex-console 数据库配置中。

默认读取路径：
    ../08_Self-built-project/config.json

用法：
    python sync_from_reference_config.py [config.json 路径]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse


def _load_config(config_path: Path) -> Dict[str, Any]:
    if not config_path.exists():
        raise FileNotFoundError(f"找不到配置文件: {config_path}")
    with config_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _derive_base_url(config: Dict[str, Any], admin_email: str) -> str:
    explicit = (
        config.get("cloud_mail_base_url")
        or config.get("cloud_mail_api_base")
        or config.get("skymail_api_base")
    )
    if explicit:
        return str(explicit).rstrip("/")
    if admin_email and "@" in admin_email:
        return f"https://{admin_email.split('@', 1)[1]}".rstrip("/")
    return ""


def _parse_proxy(proxy_url: str) -> Optional[Dict[str, Any]]:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    if not parsed.hostname:
        return None

    scheme = (parsed.scheme or "http").lower()
    port = parsed.port
    if port is None:
        if scheme in {"http"}:
            port = 80
        elif scheme in {"https"}:
            port = 443
        elif scheme.startswith("socks"):
            port = 1080

    return {
        "type": scheme,
        "host": parsed.hostname,
        "port": int(port) if port else 0,
        "username": parsed.username,
        "password": parsed.password,
    }


def _sync_settings(config: Dict[str, Any]) -> None:
    from src.database.init_db import initialize_database
    from src.config.settings import update_settings
    from src.database.session import get_db
    from src.database.models import EmailService as EmailServiceModel

    initialize_database()

    updates: Dict[str, Any] = {}

    oauth_client_id = config.get("oauth_client_id")
    oauth_redirect_uri = config.get("oauth_redirect_uri")
    oauth_issuer = config.get("oauth_issuer")

    if oauth_client_id:
        updates["openai_client_id"] = oauth_client_id
    if oauth_redirect_uri:
        updates["openai_redirect_uri"] = oauth_redirect_uri
    if oauth_issuer:
        issuer = str(oauth_issuer).rstrip("/")
        updates["openai_auth_url"] = f"{issuer}/oauth/authorize"
        updates["openai_token_url"] = f"{issuer}/oauth/token"

    proxy_url = config.get("proxy")
    if proxy_url:
        proxy_info = _parse_proxy(proxy_url)
        if proxy_info:
            updates.update(
                {
                    "proxy_enabled": True,
                    "proxy_type": proxy_info["type"],
                    "proxy_host": proxy_info["host"],
                    "proxy_port": proxy_info["port"],
                    "proxy_username": proxy_info["username"],
                    "proxy_password": proxy_info["password"],
                }
            )
    elif "proxy" in config:
        updates["proxy_enabled"] = False

    if updates:
        update_settings(**updates)
        print(f"已同步设置项: {', '.join(updates.keys())}")
    else:
        print("未检测到需要同步的基础设置")

    admin_email = (
        config.get("cloud_mail_admin_email")
        or config.get("skymail_admin_email")
        or ""
    )
    admin_password = (
        config.get("cloud_mail_admin_password")
        or config.get("skymail_admin_password")
        or ""
    )
    domains = (
        config.get("cloud_mail_domains")
        or config.get("skymail_domains")
        or []
    )

    base_url = _derive_base_url(config, admin_email)

    cloud_config: Dict[str, Any] = {
        "base_url": base_url,
        "admin_email": admin_email,
        "admin_password": admin_password,
        "domain": domains,
    }

    missing = [k for k, v in cloud_config.items() if not v]
    if missing:
        print(f"Cloud Mail 配置不完整，缺少: {missing}，跳过邮箱服务同步")
        return

    with get_db() as db:
        existing = (
            db.query(EmailServiceModel)
            .filter(EmailServiceModel.service_type == "cloud_mail")
            .first()
        )
        if existing:
            existing.name = existing.name or "cloud-mail"
            existing.config = {**(existing.config or {}), **cloud_config}
            existing.enabled = True
            db.commit()
            print("已更新 Cloud Mail 邮箱服务配置")
        else:
            service = EmailServiceModel(
                service_type="cloud_mail",
                name="cloud-mail",
                config=cloud_config,
                enabled=True,
                priority=0,
            )
            db.add(service)
            db.commit()
            print("已创建 Cloud Mail 邮箱服务配置")


def main() -> None:
    project_root = Path(__file__).resolve().parent
    default_reference = project_root.parent / "08_Self-built-project" / "config.json"
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_reference

    try:
        config = _load_config(config_path)
    except Exception as exc:
        print(f"读取配置失败: {exc}")
        sys.exit(1)

    # 确保项目根目录在 sys.path
    sys.path.insert(0, str(project_root))

    _sync_settings(config)


if __name__ == "__main__":
    main()