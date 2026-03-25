"""
Aether 服务管理 API 路由
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ....core.upload.aether_upload import fetch_aether_providers, login_aether_admin, test_aether_connection
from ....database import crud
from ....database.session import get_db

router = APIRouter()


class AetherServiceCreate(BaseModel):
    name: str
    api_url: str
    api_token: Optional[str] = None
    device_id: Optional[str] = None
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    provider_id: str
    api_formats: str = "openai:cli"
    auth_type: str = "oauth"
    extra_payload: Optional[str] = None
    enabled: bool = True
    priority: int = 0


class AetherServiceUpdate(BaseModel):
    name: Optional[str] = None
    api_url: Optional[str] = None
    api_token: Optional[str] = None
    device_id: Optional[str] = None
    admin_email: Optional[str] = None
    admin_password: Optional[str] = None
    provider_id: Optional[str] = None
    api_formats: Optional[str] = None
    auth_type: Optional[str] = None
    extra_payload: Optional[str] = None
    enabled: Optional[bool] = None
    priority: Optional[int] = None


class AetherServiceResponse(BaseModel):
    id: int
    name: str
    api_url: str
    device_id: Optional[str]
    admin_email: Optional[str]
    provider_id: str
    api_formats: str
    auth_type: str
    has_token: bool
    has_extra_payload: bool
    enabled: bool
    priority: int
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class AetherServiceTestRequest(BaseModel):
    api_url: Optional[str] = None
    api_token: Optional[str] = None
    device_id: Optional[str] = None
    provider_id: Optional[str] = None


class AetherProviderListRequest(BaseModel):
    api_url: Optional[str] = None
    api_token: Optional[str] = None
    device_id: Optional[str] = None


class AetherLoginRequest(BaseModel):
    api_url: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


def _to_response(svc) -> AetherServiceResponse:
    return AetherServiceResponse(
        id=svc.id,
        name=svc.name,
        api_url=svc.api_url,
        device_id=svc.device_id,
        admin_email=svc.admin_email,
        provider_id=svc.provider_id,
        api_formats=svc.api_formats or "openai:cli",
        auth_type=svc.auth_type or "oauth",
        has_token=bool(svc.api_token),
        has_extra_payload=bool(svc.extra_payload),
        enabled=svc.enabled,
        priority=svc.priority,
        created_at=svc.created_at.isoformat() if svc.created_at else None,
        updated_at=svc.updated_at.isoformat() if svc.updated_at else None,
    )


@router.get("", response_model=List[AetherServiceResponse])
async def list_aether_services(enabled: Optional[bool] = None):
    with get_db() as db:
        services = crud.get_aether_services(db, enabled=enabled)
        return [_to_response(s) for s in services]


@router.post("", response_model=AetherServiceResponse)
async def create_aether_service(request: AetherServiceCreate):
    if not request.api_token and not (request.admin_email and request.admin_password):
        raise HTTPException(status_code=400, detail="管理员 Token 或管理员邮箱/密码至少提供一种")

    api_token = request.api_token
    device_id = request.device_id
    if not api_token and request.admin_email and request.admin_password:
        ok, data = login_aether_admin(
            api_url=request.api_url,
            email=request.admin_email,
            password=request.admin_password,
        )
        if not ok:
            raise HTTPException(status_code=400, detail=f"Aether 登录失败: {data}")
        api_token = data.get("access_token")
        device_id = data.get("device_id")

    with get_db() as db:
        service = crud.create_aether_service(
            db,
            name=request.name,
            api_url=request.api_url,
            api_token=api_token,
            device_id=device_id,
            admin_email=request.admin_email,
            admin_password=request.admin_password,
            provider_id=request.provider_id,
            api_formats=request.api_formats,
            auth_type=request.auth_type,
            extra_payload=request.extra_payload,
            enabled=request.enabled,
            priority=request.priority,
        )
        return _to_response(service)


@router.get("/{service_id}", response_model=AetherServiceResponse)
async def get_aether_service(service_id: int):
    with get_db() as db:
        service = crud.get_aether_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Aether 服务不存在")
        return _to_response(service)


@router.get("/{service_id}/full")
async def get_aether_service_full(service_id: int):
    with get_db() as db:
        service = crud.get_aether_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Aether 服务不存在")
        return {
            "id": service.id,
            "name": service.name,
            "api_url": service.api_url,
            "api_token": service.api_token,
            "device_id": service.device_id,
            "admin_email": service.admin_email,
            "admin_password": service.admin_password,
            "provider_id": service.provider_id,
            "api_formats": service.api_formats,
            "auth_type": service.auth_type,
            "extra_payload": service.extra_payload,
            "enabled": service.enabled,
            "priority": service.priority,
        }


@router.patch("/{service_id}", response_model=AetherServiceResponse)
async def update_aether_service(service_id: int, request: AetherServiceUpdate):
    with get_db() as db:
        service = crud.get_aether_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Aether 服务不存在")

        update_data = {}
        for key in ("name", "api_url", "device_id", "admin_email", "provider_id", "api_formats", "auth_type", "extra_payload", "enabled", "priority"):
            value = getattr(request, key)
            if value is not None:
                update_data[key] = value
        if request.api_token:
            update_data["api_token"] = request.api_token
        if request.admin_password:
            update_data["admin_password"] = request.admin_password

        login_email = update_data.get("admin_email", service.admin_email)
        login_password = update_data.get("admin_password", service.admin_password)
        login_api_url = update_data.get("api_url", service.api_url)
        if not update_data.get("api_token") and login_email and login_password:
            ok, data = login_aether_admin(
                api_url=login_api_url,
                email=login_email,
                password=login_password,
            )
            if ok:
                update_data["api_token"] = data.get("access_token")
                update_data["device_id"] = data.get("device_id")

        service = crud.update_aether_service(db, service_id, **update_data)
        return _to_response(service)


@router.delete("/{service_id}")
async def delete_aether_service(service_id: int):
    with get_db() as db:
        service = crud.get_aether_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Aether 服务不存在")
        crud.delete_aether_service(db, service_id)
        return {"success": True, "message": f"Aether 服务 {service.name} 已删除"}


@router.post("/{service_id}/test")
async def test_aether_service(service_id: int):
    with get_db() as db:
        service = crud.get_aether_service_by_id(db, service_id)
        if not service:
            raise HTTPException(status_code=404, detail="Aether 服务不存在")
        success, message = test_aether_connection(
            api_url=service.api_url,
            api_token=service.api_token,
            device_id=service.device_id,
            admin_email=service.admin_email,
            admin_password=service.admin_password,
            provider_id=service.provider_id,
        )
        return {"success": success, "message": message}


@router.post("/test-connection")
async def test_aether_connection_direct(request: AetherServiceTestRequest):
    if not request.api_url or not request.api_token or not request.provider_id:
        raise HTTPException(status_code=400, detail="api_url、api_token 和 provider_id 不能为空")
    success, message = test_aether_connection(
        api_url=request.api_url,
        api_token=request.api_token,
        device_id=request.device_id,
        admin_email=None,
        admin_password=None,
        provider_id=request.provider_id,
    )
    return {"success": success, "message": message}


@router.post("/providers/fetch")
async def list_aether_providers(request: AetherProviderListRequest):
    if not request.api_url or not request.api_token:
        raise HTTPException(status_code=400, detail="api_url 和 api_token 不能为空")
    success, data = fetch_aether_providers(
        api_url=request.api_url,
        api_token=request.api_token,
        device_id=request.device_id,
    )
    if not success:
        return {"success": False, "message": data}

    providers = []
    for item in data:
        if not isinstance(item, dict):
            continue
        provider_id = str(item.get("id") or item.get("provider_id") or "").strip()
        name = str(item.get("name") or item.get("provider_name") or provider_id).strip()
        provider_type = str(item.get("provider_type") or item.get("type") or "").strip()
        if provider_id:
            providers.append({
                "id": provider_id,
                "name": name,
                "provider_type": provider_type,
                "is_active": item.get("is_active", True),
            })
    return {"success": True, "providers": providers}


@router.post("/auth/login")
async def login_aether_token(request: AetherLoginRequest):
    if not request.api_url or not request.email or not request.password:
        raise HTTPException(status_code=400, detail="api_url、email 和 password 不能为空")
    success, data = login_aether_admin(
        api_url=request.api_url,
        email=request.email,
        password=request.password,
    )
    if not success:
        return {"success": False, "message": data}
    return {
        "success": True,
        "access_token": data.get("access_token"),
        "device_id": data.get("device_id"),
        "token_type": data.get("token_type"),
        "expires_in": data.get("expires_in"),
        "role": data.get("role"),
        "email": data.get("email"),
        "username": data.get("username"),
    }
