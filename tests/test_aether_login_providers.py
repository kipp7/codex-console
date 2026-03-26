import asyncio

from src.web.routes.upload import aether_services


class DummyRequest:
    def __init__(self, api_url: str, email: str, password: str):
        self.api_url = api_url
        self.email = email
        self.password = password


def test_login_aether_token_returns_provider_list(monkeypatch):
    def fake_login_aether_admin(*, api_url: str, email: str, password: str):
        return True, {
            "access_token": "token-123",
            "device_id": "device-123",
            "token_type": "bearer",
            "expires_in": 3600,
            "email": email,
            "username": "tester",
            "role": "admin",
        }

    def fake_fetch_aether_providers(*, api_url: str, api_token: str, device_id: str):
        return True, {
            "items": [
                {
                    "id": "provider-001",
                    "name": "Codex-1",
                    "provider_type": "codex",
                    "is_active": True,
                }
            ]
        }

    monkeypatch.setattr(aether_services, "login_aether_admin", fake_login_aether_admin)
    monkeypatch.setattr(aether_services, "fetch_aether_providers", fake_fetch_aether_providers)

    result = asyncio.run(
        aether_services.login_aether_token(
            DummyRequest(
                api_url="http://example.com/admin",
                email="admin@example.com",
                password="secret",
            )
        )
    )

    assert result["success"] is True
    assert result["access_token"] == "token-123"
    assert result["providers"][0]["id"] == "provider-001"
    assert result["providers"][0]["name"] == "Codex-1"
