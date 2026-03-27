from pathlib import Path

from fastapi.testclient import TestClient

from src.web.app import create_app
from src.web.routes import cloud_mail_tools


def make_toolkit(tmp_path: Path) -> Path:
    root = tmp_path / "12_Pool-of-numbers"
    root.mkdir(parents=True, exist_ok=True)
    for name in (
        "bootstrap_cloud_mail_domain.py",
        "register_to_cloudflare_pipeline.py",
        "deploy_cloud_mail_worker.py",
        "dashboard_client.py",
    ):
        (root / name).write_text("print('ok')\n", encoding="utf-8")
    return root


def test_toolkit_root_exists(tmp_path, monkeypatch):
    toolkit = make_toolkit(tmp_path)
    monkeypatch.setenv("CLOUD_MAIL_TOOLKIT_ROOT", str(toolkit))

    assert cloud_mail_tools.get_toolkit_root().exists()


def test_build_dashboard_register_command(tmp_path, monkeypatch):
    toolkit = make_toolkit(tmp_path)
    monkeypatch.setenv("CLOUD_MAIL_TOOLKIT_ROOT", str(toolkit))

    result = cloud_mail_tools.build_command(
        "dashboard_register",
        {
            "turnstile_token": "turnstile",
            "mail_provider": "tempmail-api",
            "auto_verify_mailbox": True,
        },
    )

    assert "dashboard_client.py" in result["command"][1]
    assert "register" in result["command"]
    assert "--auto-verify-mailbox" in result["command"]


def test_build_existing_bootstrap_command(tmp_path, monkeypatch):
    toolkit = make_toolkit(tmp_path)
    monkeypatch.setenv("CLOUD_MAIL_TOOLKIT_ROOT", str(toolkit))

    result = cloud_mail_tools.build_command(
        "bootstrap_existing",
        {
            "domain": "mail.qzz.io",
            "cloudflare_api_token": "cf-token",
            "cloudflare_account_id": "acct-id",
            "jwt_secret": "jwt-secret",
        },
    )

    assert "bootstrap_cloud_mail_domain.py" in result["command"][1]
    assert "--domain" in result["command"]
    assert "mail.qzz.io" in result["command"]


def test_cloud_mail_workflows_api():
    client = TestClient(create_app())
    response = client.get("/api/cloud-mail/workflows")

    assert response.status_code == 200
    payload = response.json()
    assert "workflows" in payload
    assert "bootstrap_existing" in payload["workflows"]
    assert "dashboard_register" in payload["workflows"]


def test_cloud_mail_preview_api(tmp_path, monkeypatch):
    toolkit = make_toolkit(tmp_path)
    monkeypatch.setenv("CLOUD_MAIL_TOOLKIT_ROOT", str(toolkit))

    client = TestClient(create_app())
    response = client.post(
        "/api/cloud-mail/preview",
        json={
            "workflow": "register_pipeline",
            "params": {
                "digitalplat_api_key": "dp",
                "cloudflare_api_token": "cf",
                "cloudflare_account_id": "acct",
                "suffix": "qzz.io",
                "prefix": "mail",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert "pretty_command" in payload
    assert "register_to_cloudflare_pipeline.py" in payload["pretty_command"]


def test_main_domains_api(monkeypatch):
    monkeypatch.setattr(
        cloud_mail_tools,
        "fetch_main_domains",
        lambda: [
            {
                "domain": "demo.qzz.io",
                "status": "ok",
                "created_at": "20260327",
                "expires_at": "20270327",
                "nameservers": ["ns1.example.com", "ns2.example.com"],
                "api_url": "https://demo.qzz.io/api",
                "admin_email": "admin@demo.qzz.io",
                "admin_password": "Admin123456",
            }
        ],
    )

    client = TestClient(create_app())
    response = client.get("/api/cloud-mail/main-domains")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["domain"] == "demo.qzz.io"
