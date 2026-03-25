"""
Aether 上传功能
"""

import json
import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from curl_cffi import requests as cffi_requests

from ...config.settings import get_settings
from ...database.models import Account
from ...database.session import get_db

logger = logging.getLogger(__name__)


def _should_relogin(message: str) -> bool:
    text = (message or "").lower()
    markers = (
        "无效的token",
        "设备标识",
        "权限不足",
        "missing administrator credential",
        "invalid token",
        "unauthorized",
        "forbidden",
    )
    return any(marker in text for marker in markers)


def _normalize_aether_base_url(api_url: str) -> str:
    """将用户填写的 Aether 地址规范化为站点根地址。"""
    normalized = (api_url or "").strip().rstrip("/")
    lower_url = normalized.lower()

    for suffix in ("/admin/pool", "/admin", "/swagger"):
        if lower_url.endswith(suffix):
            return normalized[: -len(suffix)]
    return normalized


def _parse_api_formats(api_formats: Optional[str]) -> List[str]:
    formats = [item.strip() for item in (api_formats or "").split(",")]
    return [item for item in formats if item]


def _generate_device_id() -> str:
    return str(uuid.uuid4())


def _build_headers(api_token: str, *, device_id: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }
    if device_id:
        headers["X-Client-Device-Id"] = device_id
    return headers


def _extract_error(response) -> str:
    try:
        data = response.json()
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict):
                return error.get("message") or error.get("type") or f"HTTP {response.status_code}"
            return data.get("detail") or data.get("message") or f"HTTP {response.status_code}"
    except Exception:
        pass
    return f"HTTP {response.status_code}: {response.text[:200]}"


def _request_with_reauth(
    *,
    api_url: str,
    api_token: Optional[str],
    device_id: Optional[str],
    admin_email: Optional[str],
    admin_password: Optional[str],
    func,
):
    """
    使用现有 token/device_id 发请求；若失效则自动重登后重试一次。
    func(token, device_id) 应返回 (ok, payload)
    """
    current_token = api_token
    current_device_id = device_id or _generate_device_id()

    if current_token:
        ok, payload = func(current_token, current_device_id)
        if ok:
            return True, payload, current_token, current_device_id
        if not (admin_email and admin_password and _should_relogin(str(payload))):
            return False, payload, current_token, current_device_id

    if not (admin_email and admin_password):
        return False, "Aether API Token 未配置", current_token, current_device_id

    login_ok, login_data = login_aether_admin(
        api_url=api_url,
        email=admin_email,
        password=admin_password,
    )
    if not login_ok:
        return False, login_data, current_token, current_device_id

    current_token = login_data.get("access_token")
    current_device_id = login_data.get("device_id")
    ok, payload = func(current_token, current_device_id)
    return ok, payload, current_token, current_device_id


def list_aether_keys(
    *,
    api_url: str,
    api_token: Optional[str],
    provider_id: str,
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
) -> Tuple[bool, Any]:
    """列出指定 Aether provider 下的 key。"""
    if not api_url:
        return False, "Aether API URL 不能为空"
    if not provider_id:
        return False, "Aether Provider ID 不能为空"

    base_url = _normalize_aether_base_url(api_url)
    endpoint = f"{base_url}/api/admin/endpoints/providers/{provider_id}/keys"

    def _do_request(token: str, current_device_id: str):
        response = cffi_requests.get(
            endpoint,
            headers=_build_headers(token, device_id=current_device_id),
            params={"skip": 0, "limit": 500},
            timeout=20,
            impersonate="chrome120",
        )
        if response.status_code != 200:
            return False, _extract_error(response)
        data = response.json()
        if isinstance(data, list):
            return True, data
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return True, items
        return False, "Aether key 列表返回格式不支持"

    try:
        ok, payload, _, _ = _request_with_reauth(
            api_url=api_url,
            api_token=api_token,
            device_id=device_id,
            admin_email=admin_email,
            admin_password=admin_password,
            func=_do_request,
        )
        return ok, payload
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到 Aether 服务器: {exc}"
    except cffi_requests.exceptions.Timeout:
        return False, "获取 Aether key 列表超时"
    except Exception as exc:
        return False, f"获取 Aether key 列表失败: {exc}"


def delete_aether_key(
    *,
    api_url: str,
    api_token: Optional[str],
    key_id: str,
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
) -> Tuple[bool, str]:
    """删除指定 Aether key。"""
    if not api_url:
        return False, "Aether API URL 不能为空"
    if not key_id:
        return False, "Aether Key ID 不能为空"

    base_url = _normalize_aether_base_url(api_url)
    endpoint = f"{base_url}/api/admin/endpoints/keys/{key_id}"

    def _do_request(token: str, current_device_id: str):
        response = cffi_requests.delete(
            endpoint,
            headers=_build_headers(token, device_id=current_device_id),
            timeout=20,
            impersonate="chrome120",
        )
        if response.status_code in (200, 204):
            return True, "删除成功"
        return False, _extract_error(response)

    try:
        ok, payload, _, _ = _request_with_reauth(
            api_url=api_url,
            api_token=api_token,
            device_id=device_id,
            admin_email=admin_email,
            admin_password=admin_password,
            func=_do_request,
        )
        return ok, str(payload)
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到 Aether 服务器: {exc}"
    except cffi_requests.exceptions.Timeout:
        return False, "删除 Aether key 超时"
    except Exception as exc:
        return False, f"删除 Aether key 失败: {exc}"


def cleanup_aether_keys_by_email(
    *,
    api_url: str,
    api_token: Optional[str],
    provider_id: str,
    email: str,
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
) -> Tuple[bool, str]:
    """删除同 provider 下与邮箱匹配的旧 key。"""
    ok, payload = list_aether_keys(
        api_url=api_url,
        api_token=api_token,
        provider_id=provider_id,
        device_id=device_id,
        admin_email=admin_email,
        admin_password=admin_password,
    )
    if not ok:
        return False, str(payload)

    deleted = 0
    for item in payload:
        if not isinstance(item, dict):
            continue
        key_id = str(item.get("key_id") or item.get("id") or "")
        name = str(item.get("key_name") or item.get("name") or "")
        key_email = str(item.get("email") or "")
        oauth_email = str(item.get("oauth_email") or "")
        if not key_id:
            continue
        if name == email or key_email == email or oauth_email == email:
            del_ok, del_msg = delete_aether_key(
                api_url=api_url,
                api_token=api_token,
                key_id=key_id,
                device_id=device_id,
                admin_email=admin_email,
                admin_password=admin_password,
            )
            if not del_ok:
                return False, del_msg
            deleted += 1
    return True, f"已删除 {deleted} 条旧记录"


def fetch_aether_providers(
    *,
    api_url: str,
    api_token: Optional[str],
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
) -> Tuple[bool, Any]:
    """拉取 Aether Provider 列表。"""
    if not api_url:
        return False, "Aether API URL 不能为空"
    base_url = _normalize_aether_base_url(api_url)
    endpoint = f"{base_url}/api/admin/providers/summary"

    def _request(token: str, current_device_id: str):
        response = cffi_requests.get(
            endpoint,
            headers=_build_headers(token, device_id=current_device_id),
            timeout=20,
            impersonate="chrome120",
        )
        if response.status_code != 200:
            return False, _extract_error(response)
        data = response.json()
        if isinstance(data, dict):
            items = data.get("items")
            if isinstance(items, list):
                return True, items
        if isinstance(data, list):
            return True, data
        return False, "Aether Provider 列表返回格式不支持"

    try:
        ok, data, used_token, used_device_id = _request_with_reauth(
            api_url=api_url,
            api_token=api_token,
            device_id=device_id,
            admin_email=admin_email,
            admin_password=admin_password,
            func=_request,
        )
        if ok:
            return True, {"items": data, "api_token": used_token, "device_id": used_device_id}
        return False, data
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到 Aether 服务器: {exc}"
    except cffi_requests.exceptions.Timeout:
        return False, "获取 Provider 列表超时"
    except Exception as exc:
        return False, f"获取 Provider 列表失败: {exc}"


def login_aether_admin(
    *,
    api_url: str,
    email: str,
    password: str,
) -> Tuple[bool, Any]:
    """使用管理员邮箱密码登录 Aether，换取 access_token。"""
    if not api_url:
        return False, "Aether API URL 不能为空"
    if not email:
        return False, "管理员邮箱不能为空"
    if not password:
        return False, "管理员密码不能为空"

    base_url = _normalize_aether_base_url(api_url)
    endpoint = f"{base_url}/api/auth/login"
    device_id = _generate_device_id()
    try:
        response = cffi_requests.post(
            endpoint,
            json={"email": email, "password": password, "device_id": device_id},
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Client-Device-Id": device_id,
            },
            timeout=20,
            impersonate="chrome120",
        )
        if response.status_code != 200:
            return False, _extract_error(response)

        data = response.json()
        if not isinstance(data, dict):
            return False, "Aether 登录返回格式不支持"

        access_token = data.get("access_token")
        if not access_token:
            return False, "登录成功，但响应中没有 access_token"
        data["device_id"] = device_id
        return True, data
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到 Aether 服务器: {exc}"
    except cffi_requests.exceptions.Timeout:
        return False, "Aether 登录超时"
    except Exception as exc:
        return False, f"Aether 登录失败: {exc}"


def _merge_extra_payload(payload: Dict[str, Any], extra_payload: Optional[str]) -> Dict[str, Any]:
    if not extra_payload:
        return payload
    try:
        extra = json.loads(extra_payload)
    except json.JSONDecodeError as exc:
        raise ValueError(f"extra_payload 不是合法 JSON: {exc}") from exc
    if not isinstance(extra, dict):
        raise ValueError("extra_payload 必须是 JSON 对象")
    payload.update(extra)
    return payload


def _build_aether_payload(
    account: Account,
    *,
    auth_type: str = "oauth",
    api_formats: Optional[str] = None,
    extra_payload: Optional[str] = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "name": account.email,
        "auth_type": auth_type,
        "api_formats": _parse_api_formats(api_formats) or ["openai:cli"],
        "pool_enabled": True,
        "is_active": True,
        "email": account.email,
    }

    auth_type = (auth_type or "oauth").strip().lower()
    if auth_type == "oauth":
        if not account.refresh_token:
            raise ValueError("账号缺少 refresh_token，无法按 OAuth 方式上传到 Aether")
        payload["refresh_token"] = account.refresh_token
        if account.access_token:
            payload["access_token"] = account.access_token
        if account.expires_at:
            payload["expires_at"] = account.expires_at.isoformat()
        if account.id_token:
            payload["id_token"] = account.id_token
    elif auth_type == "api_key":
        if not account.access_token:
            raise ValueError("账号缺少 access_token，无法按 API Key 方式上传到 Aether")
        payload["api_key"] = account.access_token
    elif auth_type == "service_account":
        auth_config = account.extra_data.get("auth_config") if isinstance(account.extra_data, dict) else None
        if not auth_config:
            raise ValueError("账号缺少 auth_config，无法按 Service Account 方式上传到 Aether")
        payload["auth_config"] = auth_config
    else:
        raise ValueError(f"不支持的 Aether auth_type: {auth_type}")

    if account.account_id:
        payload["account_id"] = account.account_id
    if account.workspace_id:
        payload["workspace_id"] = account.workspace_id
    if account.cookies:
        payload["cookies"] = account.cookies

    return _merge_extra_payload(payload, extra_payload)


def upload_to_aether(
    account: Account,
    *,
    api_url: str,
    api_token: Optional[str],
    provider_id: str,
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
    api_formats: Optional[str] = None,
    auth_type: str = "oauth",
    extra_payload: Optional[str] = None,
) -> Tuple[bool, str]:
    """上传单个账号到 Aether。"""
    if not api_url:
        return False, "Aether API URL 未配置"
    if not provider_id:
        return False, "Aether Provider ID 未配置"

    base_url = _normalize_aether_base_url(api_url)
    endpoint = f"{base_url}/api/admin/endpoints/providers/{provider_id}/keys"
    current_device_id = device_id or _generate_device_id()

    try:
        cleanup_ok, cleanup_msg = cleanup_aether_keys_by_email(
            api_url=api_url,
            api_token=api_token,
            provider_id=provider_id,
            email=account.email,
            device_id=device_id,
            admin_email=admin_email,
            admin_password=admin_password,
        )
        if not cleanup_ok:
            logger.warning("Aether 旧记录清理失败: %s", cleanup_msg)

        payload = _build_aether_payload(
            account,
            auth_type=auth_type,
            api_formats=api_formats,
            extra_payload=extra_payload,
        )
        def _request(token: str, request_device_id: str):
            response = cffi_requests.post(
                endpoint,
                headers=_build_headers(token, device_id=request_device_id),
                json=payload,
                timeout=30,
                impersonate="chrome120",
            )
            if response.status_code in (200, 201):
                return True, "上传成功"
            return False, _extract_error(response)

        ok, msg, _, _ = _request_with_reauth(
            api_url=api_url,
            api_token=api_token,
            device_id=current_device_id,
            admin_email=admin_email,
            admin_password=admin_password,
            func=_request,
        )
        return ok, msg
    except Exception as exc:
        logger.error("Aether 上传异常: %s", exc)
        return False, f"上传异常: {exc}"


def batch_upload_to_aether(
    account_ids: List[int],
    *,
    api_url: str,
    api_token: Optional[str],
    provider_id: str,
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
    api_formats: Optional[str] = None,
    auth_type: str = "oauth",
    extra_payload: Optional[str] = None,
) -> Dict[str, Any]:
    """批量上传账号到 Aether。"""
    results = {
        "success_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "details": [],
    }

    with get_db() as db:
        for account_id in account_ids:
            account = db.query(Account).filter(Account.id == account_id).first()
            if not account:
                results["failed_count"] += 1
                results["details"].append({"id": account_id, "email": None, "success": False, "error": "账号不存在"})
                continue

            success, message = upload_to_aether(
                account,
                api_url=api_url,
                api_token=api_token,
                provider_id=provider_id,
                device_id=device_id,
                admin_email=admin_email,
                admin_password=admin_password,
                api_formats=api_formats,
                auth_type=auth_type,
                extra_payload=extra_payload,
            )
            if success:
                account.aether_uploaded = True
                account.aether_uploaded_at = datetime.utcnow()
                db.commit()
                results["success_count"] += 1
                results["details"].append({"id": account_id, "email": account.email, "success": True, "message": message})
            else:
                if "缺少" in message:
                    results["skipped_count"] += 1
                else:
                    results["failed_count"] += 1
                results["details"].append({"id": account_id, "email": account.email, "success": False, "error": message})

    return results


def test_aether_connection(
    *,
    api_url: str,
    api_token: Optional[str],
    provider_id: str,
    device_id: Optional[str] = None,
    admin_email: Optional[str] = None,
    admin_password: Optional[str] = None,
) -> Tuple[bool, str]:
    """测试 Aether 服务连通性和凭据。"""
    if not api_url:
        return False, "Aether API URL 不能为空"
    if not provider_id:
        return False, "Aether Provider ID 不能为空"

    base_url = _normalize_aether_base_url(api_url)
    endpoint = f"{base_url}/api/admin/endpoints/providers/{provider_id}/keys"
    current_device_id = device_id or _generate_device_id()
    try:
        def _request(token: str, request_device_id: str):
            response = cffi_requests.get(
                endpoint,
                headers=_build_headers(token, device_id=request_device_id),
                params={"skip": 0, "limit": 1},
                timeout=15,
                impersonate="chrome120",
            )
            if response.status_code == 200:
                return True, "Aether 连接测试成功"
            if response.status_code in (401, 403):
                return False, "连接成功，但管理员 Token 无效或权限不足"
            if response.status_code == 404:
                return False, "未找到指定 Provider，请检查 Provider ID 是否正确"
            return False, _extract_error(response)

        ok, msg, _, _ = _request_with_reauth(
            api_url=api_url,
            api_token=api_token,
            device_id=current_device_id,
            admin_email=admin_email,
            admin_password=admin_password,
            func=_request,
        )
        return ok, msg
    except cffi_requests.exceptions.ConnectionError as exc:
        return False, f"无法连接到 Aether 服务器: {exc}"
    except cffi_requests.exceptions.Timeout:
        return False, "连接超时，请检查 Aether 服务地址"
    except Exception as exc:
        return False, f"连接测试失败: {exc}"
