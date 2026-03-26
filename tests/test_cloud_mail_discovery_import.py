import asyncio
from contextlib import contextmanager
from pathlib import Path

from src.database.models import Base, EmailService
from src.database.session import DatabaseSessionManager
from src.web.routes import email as email_routes


def make_mail_worker(tmp_path: Path) -> Path:
    worker_dir = tmp_path / "12_Pool-of-numbers" / "cloud-mail" / "mail-worker"
    worker_dir.mkdir(parents=True, exist_ok=True)
    (worker_dir / "wrangler.auto.toml").write_text(
        """
name = "cloud-mail-demo"

[[routes]]
pattern = "demo.example.com"
custom_domain = true

[vars]
domain = ["demo.example.com"]
admin = "admin@demo.example.com"
jwt_secret = "demo-jwt-secret"
""".strip(),
        encoding="utf-8",
    )
    return worker_dir


def test_discover_cloud_mail_configs_contains_current_auto_toml(tmp_path, monkeypatch):
    worker_dir = make_mail_worker(tmp_path)
    monkeypatch.setenv("CLOUD_MAIL_TOOLKIT_ROOT", str(worker_dir.parents[1]))
    items = email_routes.discover_cloud_mail_configs()

    assert items
    first = items[0]
    assert "domain" in first
    assert "base_url" in first
    assert "admin_email" in first
    assert "admin_password" in first
    assert first["admin_password"] == "Admin123456"
    assert first["domain"] == "demo.example.com"


def test_discover_cloud_mail_configs_skips_template_placeholders(tmp_path, monkeypatch):
    worker_dir = make_mail_worker(tmp_path)
    (worker_dir / "wrangler-dev.toml").write_text(
        """
name = "${NAME}"
[vars]
domain = ["${DOMAIN}"]
admin = "${ADMIN}"
jwt_secret = "${JWT_SECRET}"
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("CLOUD_MAIL_TOOLKIT_ROOT", str(worker_dir.parents[1]))
    items = email_routes.discover_cloud_mail_configs()

    assert all("${" not in item["domain"] for item in items)
    assert all("${" not in item["admin_email"] for item in items)


def test_import_cloud_mail_services_upserts_into_email_services(monkeypatch):
    runtime_dir = Path("tests_runtime")
    runtime_dir.mkdir(exist_ok=True)
    db_path = runtime_dir / "cloudmail_import.db"
    if db_path.exists():
        db_path.unlink()

    manager = DatabaseSessionManager(f"sqlite:///{db_path}")
    Base.metadata.create_all(bind=manager.engine)

    @contextmanager
    def fake_get_db():
        session = manager.SessionLocal()
        try:
            yield session
        finally:
            session.close()

    monkeypatch.setattr(email_routes, "get_db", fake_get_db)

    request = email_routes.CloudMailImportRequest(
        items=[
            email_routes.CloudMailImportItem(
                domain="demo.example.com",
                domains=["demo.example.com"],
                base_url="https://demo.example.com",
                admin_email="admin@demo.example.com",
                admin_password="Admin123456",
                config_path="wrangler.auto.toml",
                name="CloudMail demo.example.com",
            )
        ]
    )

    result = asyncio.run(email_routes.import_cloud_mail_services(request))

    assert result["success"] is True
    assert result["count"] == 1

    with manager.session_scope() as session:
        service = session.query(EmailService).filter(EmailService.service_type == "cloud_mail").first()
        assert service is not None
        assert service.name == "CloudMail demo.example.com"
        assert service.config["base_url"] == "https://demo.example.com"
        assert service.config["admin_email"] == "admin@demo.example.com"
        assert service.config["admin_password"] == "Admin123456"
