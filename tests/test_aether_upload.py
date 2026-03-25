from types import SimpleNamespace

from src.core.upload import aether_upload


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json payload")
        return self._payload


def make_account(**overrides):
    base = {
        "email": "tester@example.com",
        "refresh_token": "refresh-token",
        "access_token": "access-token",
        "id_token": "id-token",
        "expires_at": None,
        "account_id": "acc-1",
        "workspace_id": "ws-1",
        "cookies": None,
        "extra_data": {},
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_upload_to_aether_accepts_admin_pool_url(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(status_code=201)

    monkeypatch.setattr(aether_upload.cffi_requests, "post", fake_post)

    success, message = aether_upload.upload_to_aether(
        make_account(),
        api_url="http://example.com:8084/admin/pool",
        api_token="token-123",
        provider_id="provider-001",
        api_formats="openai:cli,openai:chat",
    )

    assert success is True
    assert message == "上传成功"
    assert calls[0]["url"] == "http://example.com:8084/api/admin/endpoints/providers/provider-001/keys"
    assert calls[0]["kwargs"]["headers"]["Authorization"] == "Bearer token-123"
    assert calls[0]["kwargs"]["json"]["auth_type"] == "oauth"
    assert calls[0]["kwargs"]["json"]["api_formats"] == ["openai:cli", "openai:chat"]
    assert calls[0]["kwargs"]["json"]["refresh_token"] == "refresh-token"


def test_upload_to_aether_merges_extra_payload(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append(kwargs["json"])
        return FakeResponse(status_code=200)

    monkeypatch.setattr(aether_upload.cffi_requests, "post", fake_post)

    success, _ = aether_upload.upload_to_aether(
        make_account(),
        api_url="http://example.com:8084",
        api_token="token-123",
        provider_id="provider-001",
        extra_payload='{"note":"from-codex","pool_enabled":false}',
    )

    assert success is True
    assert calls[0]["note"] == "from-codex"
    assert calls[0]["pool_enabled"] is False


def test_test_aether_connection_uses_provider_keys_endpoint(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append({"url": url, "kwargs": kwargs})
        return FakeResponse(status_code=200, payload=[])

    monkeypatch.setattr(aether_upload.cffi_requests, "get", fake_get)

    success, message = aether_upload.test_aether_connection(
        api_url="http://example.com:8084/admin",
        api_token="token-123",
        provider_id="provider-001",
    )

    assert success is True
    assert message == "Aether 连接测试成功"
    assert calls[0]["url"] == "http://example.com:8084/api/admin/endpoints/providers/provider-001/keys"
    assert calls[0]["kwargs"]["params"] == {"skip": 0, "limit": 1}
