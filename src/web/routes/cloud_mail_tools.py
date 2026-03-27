"""
Cloud Mail 工具台 API
将 12_Pool-of-numbers 项目的脚本能力接入当前控制台
"""

from __future__ import annotations

import json
import secrets
import subprocess
import sys
import threading
import time
import uuid
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import requests
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field


router = APIRouter()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = Path(__file__).resolve().parents[4]
PYTHON = sys.executable


def _default_cloud_mail_repo() -> str:
    return str(get_toolkit_root() / "cloud-mail")


DEFAULT_DIGITALPLAT_API_KEY = "dp_live_li1ZkICQlRj1i4im7AieIeYN"
DEFAULT_CLOUDFLARE_API_TOKEN = "cfat_QaXV5zE4DjRZgtGKnlxIS7vUnGYaChDy8d5rKKTf9a66e2be"
DEFAULT_CLOUDFLARE_ACCOUNT_ID = "4b43de7d2636147dbc38ef2ca08d9911"
DEFAULT_MAIL_API_BASE = "https://api.tempmail.lol"
DEFAULT_TURNSTILE_TOKEN = "invalid-test-token"
DEFAULT_DIGITALPLAT_BASE_URL = "https://domain-api.digitalplat.org/api/v1"


def get_toolkit_root() -> Path:
    override = os.environ.get("CLOUD_MAIL_TOOLKIT_ROOT", "").strip()
    candidates = []
    if override:
        candidates.append(Path(override))
    candidates.extend([
        WORKSPACE_ROOT / "12_Pool-of-numbers",
        PROJECT_ROOT.parent / "12_Pool-of-numbers",
    ])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def _auto_secret(length: int = 24) -> str:
    return secrets.token_urlsafe(length)[:length]


def _auto_prefix(length: int = 6) -> str:
    alphabet = "abcdefghijklmnopqrstuvwxyz0123456789"
    return "".join(secrets.choice(alphabet) for _ in range(length))


WORKFLOW_DEFS: dict[str, dict[str, Any]] = {
    "bootstrap_existing": {
        "label": "完整部署 / 已有域名",
        "description": "已有域名时，直接部署 cloud-mail。",
        "script": "bootstrap_cloud_mail_domain.py",
        "cwd": "",
        "fields": [
            {"name": "domain", "label": "域名", "type": "text", "required": True, "placeholder": "mail.qzz.io"},
            {"name": "cloudflare_api_token", "label": "Cloudflare API Token", "type": "password", "required": False, "default": DEFAULT_CLOUDFLARE_API_TOKEN},
            {"name": "cloudflare_account_id", "label": "Cloudflare Account ID", "type": "text", "required": False, "default": DEFAULT_CLOUDFLARE_ACCOUNT_ID},
            {"name": "jwt_secret", "label": "JWT Secret", "type": "text", "required": False, "default": "自动生成"},
            {"name": "admin_localpart", "label": "管理员前缀", "type": "text", "default": "admin"},
            {"name": "repo_root", "label": "cloud-mail 仓库目录", "type": "text", "default": _default_cloud_mail_repo()},
            {"name": "skip_r2", "label": "跳过 R2", "type": "boolean", "default": True},
            {"name": "worker_name", "label": "Worker 名称", "type": "text"},
            {"name": "d1_name", "label": "D1 名称", "type": "text"},
            {"name": "kv_name", "label": "KV 名称", "type": "text"},
            {"name": "r2_name", "label": "R2 名称", "type": "text"},
        ],
    },
    "bootstrap_new": {
        "label": "完整部署 / 新注册域名",
        "description": "注册域名、接入 Cloudflare、完成部署。",
        "script": "bootstrap_cloud_mail_domain.py",
        "cwd": "",
        "fields": [
            {"name": "digitalplat_api_key", "label": "DigitalPlat API Key", "type": "password", "required": False, "default": DEFAULT_DIGITALPLAT_API_KEY},
            {"name": "cloudflare_api_token", "label": "Cloudflare API Token", "type": "password", "required": False, "default": DEFAULT_CLOUDFLARE_API_TOKEN},
            {"name": "cloudflare_account_id", "label": "Cloudflare Account ID", "type": "text", "required": False, "default": DEFAULT_CLOUDFLARE_ACCOUNT_ID},
            {"name": "suffix", "label": "后缀", "type": "select", "default": "qzz.io", "options": ["qzz.io", "dpdns.org"]},
            {"name": "prefix", "label": "前缀", "type": "text", "required": False, "default": "自动生成", "placeholder": "留空随机生成"},
            {"name": "jwt_secret", "label": "JWT Secret", "type": "text", "required": False, "default": "自动生成"},
            {"name": "start", "label": "起始编号", "type": "number", "default": 1},
            {"name": "count", "label": "候选数量", "type": "number", "default": 20},
            {"name": "padding", "label": "补零位数", "type": "number", "default": 3},
            {"name": "registration_output", "label": "注册结果 CSV", "type": "text", "default": "bootstrap_registration.csv"},
            {"name": "admin_localpart", "label": "管理员前缀", "type": "text", "default": "admin"},
            {"name": "repo_root", "label": "cloud-mail 仓库目录", "type": "text", "default": _default_cloud_mail_repo()},
            {"name": "records_file", "label": "DNS 模板文件", "type": "text"},
            {"name": "digitalplat_proxy", "label": "DigitalPlat 代理", "type": "text", "placeholder": "http://127.0.0.1:7890"},
            {"name": "digitalplat_cookie", "label": "DigitalPlat Cookie", "type": "textarea", "placeholder": "cf_clearance=...; other=..."},
            {"name": "digitalplat_user_agent", "label": "DigitalPlat User-Agent", "type": "text"},
            {"name": "skip_r2", "label": "跳过 R2", "type": "boolean", "default": True},
        ],
    },
    "register_pipeline": {
        "label": "仅注册链路",
        "description": "只做域名注册和 Cloudflare 接入。",
        "script": "register_to_cloudflare_pipeline.py",
        "cwd": "",
        "fields": [
            {"name": "digitalplat_api_key", "label": "DigitalPlat API Key", "type": "password", "required": False, "default": DEFAULT_DIGITALPLAT_API_KEY},
            {"name": "cloudflare_api_token", "label": "Cloudflare API Token", "type": "password", "required": False, "default": DEFAULT_CLOUDFLARE_API_TOKEN},
            {"name": "cloudflare_account_id", "label": "Cloudflare Account ID", "type": "text", "required": False, "default": DEFAULT_CLOUDFLARE_ACCOUNT_ID},
            {"name": "suffix", "label": "后缀", "type": "select", "default": "qzz.io", "options": ["qzz.io", "dpdns.org"]},
            {"name": "prefix", "label": "前缀", "type": "text", "required": False, "default": "自动生成", "placeholder": "留空随机生成"},
            {"name": "start", "label": "起始编号", "type": "number", "default": 1},
            {"name": "count", "label": "候选数量", "type": "number", "default": 20},
            {"name": "padding", "label": "补零位数", "type": "number", "default": 3},
            {"name": "output", "label": "输出 CSV", "type": "text", "default": "domain_cloudflare_pipeline_results.csv"},
            {"name": "sleep_seconds", "label": "间隔秒数", "type": "number", "default": 0},
            {"name": "records_file", "label": "DNS 模板文件", "type": "text"},
            {"name": "digitalplat_proxy", "label": "DigitalPlat 代理", "type": "text", "placeholder": "http://127.0.0.1:7890"},
            {"name": "digitalplat_cookie", "label": "DigitalPlat Cookie", "type": "textarea", "placeholder": "cf_clearance=...; other=..."},
            {"name": "digitalplat_user_agent", "label": "DigitalPlat User-Agent", "type": "text"},
            {"name": "dry_run", "label": "仅预览", "type": "boolean", "default": False},
        ],
    },
    "deploy_worker": {
        "label": "仅部署 Worker",
        "description": "单独执行 cloud-mail Worker 部署。",
        "script": "deploy_cloud_mail_worker.py",
        "cwd": "",
        "fields": [
            {"name": "repo_root", "label": "cloud-mail 仓库目录", "type": "text", "default": _default_cloud_mail_repo()},
            {"name": "cloudflare_api_token", "label": "Cloudflare API Token", "type": "password", "required": False, "default": DEFAULT_CLOUDFLARE_API_TOKEN},
            {"name": "cloudflare_account_id", "label": "Cloudflare Account ID", "type": "text", "required": False, "default": DEFAULT_CLOUDFLARE_ACCOUNT_ID},
            {"name": "domain", "label": "域名", "type": "text", "required": True},
            {"name": "admin_email", "label": "管理员邮箱", "type": "text", "required": True},
            {"name": "jwt_secret", "label": "JWT Secret", "type": "text", "required": False, "default": "自动生成"},
            {"name": "admin_password", "label": "管理员密码", "type": "text", "default": "Admin123456"},
            {"name": "location", "label": "区域", "type": "text", "default": "apac"},
            {"name": "skip_r2", "label": "跳过 R2", "type": "boolean", "default": True},
            {"name": "skip_deploy", "label": "只生成不部署", "type": "boolean", "default": False},
            {"name": "skip_email_routing", "label": "跳过 Email Routing", "type": "boolean", "default": False},
            {"name": "skip_init", "label": "跳过初始化", "type": "boolean", "default": False},
            {"name": "skip_admin_setup", "label": "跳过管理员设置", "type": "boolean", "default": False},
            {"name": "worker_name", "label": "Worker 名称", "type": "text"},
            {"name": "d1_name", "label": "D1 名称", "type": "text"},
            {"name": "kv_name", "label": "KV 名称", "type": "text"},
            {"name": "r2_name", "label": "R2 名称", "type": "text"},
        ],
    },
    "dashboard_register": {
        "label": "面板注册 + 自动验证",
        "description": "注册 DigitalPlat 面板账号并自动收码验证。",
        "script": "dashboard_client.py",
        "cwd": "",
        "fields": [
            {"name": "base_url", "label": "面板地址", "type": "text", "default": "https://dash.domain.digitalplat.org"},
            {"name": "turnstile_token", "label": "Turnstile Token", "type": "text", "required": True, "default": DEFAULT_TURNSTILE_TOKEN, "placeholder": "当前默认值用于宽松校验场景，失效时再手动替换"},
            {"name": "mail_provider", "label": "邮箱服务", "type": "select", "default": "tempmail-api", "options": ["tempmail-api", "temp-mail", "1secmail"]},
            {"name": "referral_code", "label": "邀请码", "type": "text", "default": "wCj8Mk39yS"},
            {"name": "timeout", "label": "超时秒数", "type": "number", "default": 30},
            {"name": "verification_wait_seconds", "label": "等待秒数", "type": "number", "default": 180},
            {"name": "verification_poll_interval", "label": "轮询间隔", "type": "number", "default": 10},
            {"name": "auto_verify_mailbox", "label": "自动收码验证", "type": "boolean", "default": True},
            {"name": "mail_api_base", "label": "邮箱 API 地址", "type": "textarea", "default": DEFAULT_MAIL_API_BASE, "placeholder": "每行一个，留空则使用默认值。"},
            {"name": "mail_api_key", "label": "邮箱 API Key", "type": "text"},
            {"name": "mailbox_token", "label": "邮箱 Token", "type": "text"},
            {"name": "mailbox_prefix", "label": "邮箱前缀", "type": "text"},
            {"name": "mailbox_domain", "label": "邮箱域名", "type": "text"},
            {"name": "username", "label": "用户名", "type": "text"},
            {"name": "fullname", "label": "姓名", "type": "text"},
            {"name": "email", "label": "邮箱", "type": "text"},
            {"name": "phone", "label": "电话", "type": "text"},
            {"name": "address", "label": "地址", "type": "text"},
            {"name": "password", "label": "密码", "type": "text"},
            {"name": "email_domain", "label": "生成邮箱域名", "type": "text", "default": "example.com"},
            {"name": "main_account_panel_session", "label": "主账号 panel_session", "type": "text"},
        ],
    },
}


class TaskCreateRequest(BaseModel):
    workflow: str
    params: dict[str, Any] = Field(default_factory=dict)


class MainDomainItem(BaseModel):
    domain: str
    status: str | None = None
    created_at: str | None = None
    expires_at: str | None = None
    nameservers: list[str] = Field(default_factory=list)
    api_url: str
    admin_email: str
    admin_password: str


class MainDomainsResponse(BaseModel):
    total: int
    items: list[MainDomainItem]


@dataclass(slots=True)
class CloudMailTask:
    id: str
    workflow: str
    label: str
    command: list[str]
    pretty_command: str
    cwd: str
    status: str = "queued"
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    exit_code: int | None = None
    logs: list[str] = field(default_factory=list)
    result_text: str = ""
    result_json: Any | None = None
    error: str | None = None


class CloudMailTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, CloudMailTask] = {}
        self._lock = threading.Lock()

    def create(self, task: CloudMailTask) -> CloudMailTask:
        with self._lock:
            self._tasks[task.id] = task
        return task

    def get(self, task_id: str) -> CloudMailTask | None:
        with self._lock:
            return self._tasks.get(task_id)

    def list(self) -> list[CloudMailTask]:
        with self._lock:
            return sorted(self._tasks.values(), key=lambda item: item.created_at, reverse=True)

    def update(self, task_id: str, updater) -> CloudMailTask | None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return None
            updater(task)
            return task


TASK_STORE = CloudMailTaskStore()


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    return value


def _bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _num(value: Any, default: int | float | None = None) -> str | None:
    if value is None or value == "":
        return None if default is None else str(default)
    if isinstance(value, (int, float)):
        return str(value)
    stripped = str(value).strip()
    return stripped or (str(default) if default is not None else None)


def _split_lines(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [line.strip() for line in str(value).splitlines() if line.strip()]


def _append_optional(command: list[str], flag: str, value: Any) -> None:
    if value is None:
        return
    text = str(value).strip()
    if text:
        command.extend([flag, text])


def _append_bool(command: list[str], flag: str, enabled: bool) -> None:
    if enabled:
        command.append(flag)


def _require(params: dict[str, Any], *keys: str) -> None:
    missing = [key for key in keys if not str(params.get(key, "")).strip()]
    if missing:
        raise ValueError(f"缺少必填项：{', '.join(missing)}")


def _coalesce(value: Any, fallback: str = "") -> str:
    text = str(value or "").strip()
    return text or fallback


def _is_auto(value: Any) -> bool:
    text = str(value or "").strip().lower()
    return text in {"", "auto", "自动", "自动生成"}


def format_command(command: list[str]) -> str:
    rendered: list[str] = []
    for index, part in enumerate(command):
        escaped = part if all(char not in part for char in ' \t"') else f'"{part}"'
        if index == 0:
            rendered.append(escaped)
        elif part.startswith("--") or part in {"register", "verify", "resend"}:
            rendered.append(" \\\n  " + escaped)
        else:
            rendered.append(" " + escaped)
    return "".join(rendered)


def build_command(workflow: str, raw_params: dict[str, Any]) -> dict[str, Any]:
    if workflow not in WORKFLOW_DEFS:
        raise ValueError(f"不支持的流程：{workflow}")

    toolkit_root = get_toolkit_root()

    if not toolkit_root.exists():
        raise ValueError(f"未找到工具目录：{toolkit_root}")

    params = {key: _sanitize_value(value) for key, value in raw_params.items()}
    command = [PYTHON, str(toolkit_root / WORKFLOW_DEFS[workflow]["script"])]

    if workflow == "bootstrap_existing":
        _require(params, "domain")
        cloudflare_api_token = _coalesce(params.get("cloudflare_api_token"), DEFAULT_CLOUDFLARE_API_TOKEN)
        cloudflare_account_id = _coalesce(params.get("cloudflare_account_id"), DEFAULT_CLOUDFLARE_ACCOUNT_ID)
        jwt_secret = _auto_secret() if _is_auto(params.get("jwt_secret")) else _coalesce(params.get("jwt_secret"))
        if not cloudflare_api_token or not cloudflare_account_id or not jwt_secret:
            raise ValueError("缺少 Cloudflare 凭据或 JWT Secret")
        command += ["--domain", params["domain"]]
        command += ["--cloudflare-api-token", cloudflare_api_token]
        command += ["--cloudflare-account-id", cloudflare_account_id]
        command += ["--jwt-secret", jwt_secret]
        _append_optional(command, "--admin-localpart", params.get("admin_localpart"))
        _append_optional(command, "--repo-root", params.get("repo_root"))
        _append_optional(command, "--worker-name", params.get("worker_name"))
        _append_optional(command, "--d1-name", params.get("d1_name"))
        _append_optional(command, "--kv-name", params.get("kv_name"))
        _append_optional(command, "--r2-name", params.get("r2_name"))
        _append_bool(command, "--skip-r2", _bool(params.get("skip_r2"), True))

    elif workflow == "bootstrap_new":
        _require(params, "suffix")
        digitalplat_api_key = _coalesce(params.get("digitalplat_api_key"), DEFAULT_DIGITALPLAT_API_KEY)
        cloudflare_api_token = _coalesce(params.get("cloudflare_api_token"), DEFAULT_CLOUDFLARE_API_TOKEN)
        cloudflare_account_id = _coalesce(params.get("cloudflare_account_id"), DEFAULT_CLOUDFLARE_ACCOUNT_ID)
        prefix = _auto_prefix() if _is_auto(params.get("prefix")) else _coalesce(params.get("prefix"))
        jwt_secret = _auto_secret() if _is_auto(params.get("jwt_secret")) else _coalesce(params.get("jwt_secret"))
        if not digitalplat_api_key or not cloudflare_api_token or not cloudflare_account_id or not prefix or not jwt_secret:
            raise ValueError("缺少 DigitalPlat/Cloudflare 凭据，或前缀/JWT 无法生成")
        command += ["--digitalplat-api-key", digitalplat_api_key]
        command += ["--cloudflare-api-token", cloudflare_api_token]
        command += ["--cloudflare-account-id", cloudflare_account_id]
        command += ["--suffix", params["suffix"]]
        command += ["--prefix", prefix]
        for flag, key, default in (("--start", "start", 1), ("--count", "count", 20), ("--padding", "padding", 3)):
            value = _num(params.get(key), default)
            if value is not None:
                command += [flag, value]
        command += ["--jwt-secret", jwt_secret]
        _append_optional(command, "--registration-output", params.get("registration_output"))
        _append_optional(command, "--admin-localpart", params.get("admin_localpart"))
        _append_optional(command, "--repo-root", params.get("repo_root"))
        _append_optional(command, "--records-file", params.get("records_file"))
        _append_optional(command, "--digitalplat-proxy", params.get("digitalplat_proxy"))
        _append_optional(command, "--digitalplat-cookie", params.get("digitalplat_cookie"))
        _append_optional(command, "--digitalplat-user-agent", params.get("digitalplat_user_agent"))
        _append_bool(command, "--skip-r2", _bool(params.get("skip_r2"), True))

    elif workflow == "register_pipeline":
        _require(params, "suffix")
        digitalplat_api_key = _coalesce(params.get("digitalplat_api_key"), DEFAULT_DIGITALPLAT_API_KEY)
        cloudflare_api_token = _coalesce(params.get("cloudflare_api_token"), DEFAULT_CLOUDFLARE_API_TOKEN)
        cloudflare_account_id = _coalesce(params.get("cloudflare_account_id"), DEFAULT_CLOUDFLARE_ACCOUNT_ID)
        prefix = _auto_prefix() if _is_auto(params.get("prefix")) else _coalesce(params.get("prefix"))
        if not digitalplat_api_key or not cloudflare_api_token or not cloudflare_account_id or not prefix:
            raise ValueError("缺少 DigitalPlat/Cloudflare 凭据，或前缀无法生成")
        command += ["--digitalplat-api-key", digitalplat_api_key]
        command += ["--cloudflare-api-token", cloudflare_api_token]
        command += ["--cloudflare-account-id", cloudflare_account_id]
        command += ["--suffix", params["suffix"]]
        command += ["--prefix", prefix]
        for flag, key, default in (
            ("--start", "start", 1),
            ("--count", "count", 20),
            ("--padding", "padding", 3),
            ("--sleep-seconds", "sleep_seconds", 0),
        ):
            value = _num(params.get(key), default)
            if value is not None:
                command += [flag, value]
        _append_optional(command, "--output", params.get("output"))
        _append_optional(command, "--records-file", params.get("records_file"))
        _append_optional(command, "--digitalplat-proxy", params.get("digitalplat_proxy"))
        _append_optional(command, "--digitalplat-cookie", params.get("digitalplat_cookie"))
        _append_optional(command, "--digitalplat-user-agent", params.get("digitalplat_user_agent"))
        _append_bool(command, "--dry-run", _bool(params.get("dry_run"), False))

    elif workflow == "deploy_worker":
        _require(params, "domain", "admin_email")
        cloudflare_api_token = _coalesce(params.get("cloudflare_api_token"), DEFAULT_CLOUDFLARE_API_TOKEN)
        cloudflare_account_id = _coalesce(params.get("cloudflare_account_id"), DEFAULT_CLOUDFLARE_ACCOUNT_ID)
        jwt_secret = _auto_secret() if _is_auto(params.get("jwt_secret")) else _coalesce(params.get("jwt_secret"))
        if not cloudflare_api_token or not cloudflare_account_id or not jwt_secret:
            raise ValueError("缺少 Cloudflare 凭据或 JWT Secret")
        command += ["--cloudflare-api-token", cloudflare_api_token]
        command += ["--cloudflare-account-id", cloudflare_account_id]
        command += ["--domain", params["domain"]]
        command += ["--admin-email", params["admin_email"]]
        command += ["--jwt-secret", jwt_secret]
        _append_optional(command, "--repo-root", params.get("repo_root"))
        _append_optional(command, "--admin-password", params.get("admin_password"))
        _append_optional(command, "--worker-name", params.get("worker_name"))
        _append_optional(command, "--d1-name", params.get("d1_name"))
        _append_optional(command, "--kv-name", params.get("kv_name"))
        _append_optional(command, "--r2-name", params.get("r2_name"))
        _append_optional(command, "--location", params.get("location"))
        _append_bool(command, "--skip-r2", _bool(params.get("skip_r2"), True))
        _append_bool(command, "--skip-deploy", _bool(params.get("skip_deploy"), False))
        _append_bool(command, "--skip-email-routing", _bool(params.get("skip_email_routing"), False))
        _append_bool(command, "--skip-init", _bool(params.get("skip_init"), False))
        _append_bool(command, "--skip-admin-setup", _bool(params.get("skip_admin_setup"), False))

    elif workflow == "dashboard_register":
        _require(params, "turnstile_token")
        command += ["--base-url", params.get("base_url") or "https://dash.domain.digitalplat.org"]
        command += ["--timeout", _num(params.get("timeout"), 30) or "30"]
        command.append("register")
        command += ["--turnstile-token", params["turnstile_token"]]
        for flag, key in (
            ("--username", "username"),
            ("--fullname", "fullname"),
            ("--email", "email"),
            ("--phone", "phone"),
            ("--address", "address"),
            ("--password", "password"),
            ("--email-domain", "email_domain"),
            ("--referral-code", "referral_code"),
            ("--main-account-panel-session", "main_account_panel_session"),
            ("--mail-provider", "mail_provider"),
            ("--mail-api-key", "mail_api_key"),
            ("--mailbox-token", "mailbox_token"),
            ("--mailbox-prefix", "mailbox_prefix"),
            ("--mailbox-domain", "mailbox_domain"),
        ):
            _append_optional(command, flag, params.get(key))
        for flag, key, default in (
            ("--verification-wait-seconds", "verification_wait_seconds", 180),
            ("--verification-poll-interval", "verification_poll_interval", 10),
        ):
            value = _num(params.get(key), default)
            if value is not None:
                command += [flag, value]
        for api_base in _split_lines(params.get("mail_api_base")):
            command += ["--mail-api-base", api_base]
        _append_bool(command, "--auto-verify-mailbox", _bool(params.get("auto_verify_mailbox"), True))

    return {
        "workflow": workflow,
        "cwd": str(toolkit_root),
        "command": command,
        "pretty_command": format_command(command),
    }


def fetch_main_domains() -> list[dict[str, Any]]:
    response = requests.get(
        f"{DEFAULT_DIGITALPLAT_BASE_URL}/domains",
        headers={
            "Authorization": f"Bearer {DEFAULT_DIGITALPLAT_API_KEY}",
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.7680.165 Safari/537.36",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise RuntimeError("DigitalPlat domains response is not an object")
    data = payload.get("data")
    if not isinstance(data, list):
        return []

    items: list[dict[str, Any]] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        domain = str(entry.get("domain") or "").strip().lower()
        if not domain:
            continue
        items.append(
            {
                "domain": domain,
                "status": str(entry.get("status") or "").strip() or None,
                "created_at": str(entry.get("created_at") or "").strip() or None,
                "expires_at": str(entry.get("expires_at") or "").strip() or None,
                "nameservers": [str(item).strip() for item in (entry.get("nameservers") or []) if str(item).strip()],
                "api_url": f"https://{domain}/api",
                "admin_email": f"admin@{domain}",
                "admin_password": "Admin123456",
            }
        )
    return items


def run_task(task_id: str) -> None:
    task = TASK_STORE.get(task_id)
    if task is None:
        return

    TASK_STORE.update(task_id, lambda item: setattr(item, "status", "running") or setattr(item, "started_at", time.time()))

    try:
        process = subprocess.Popen(
            task.command,
            cwd=task.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
    except Exception as exc:
        def fail(item: CloudMailTask) -> None:
            item.status = "failed"
            item.finished_at = time.time()
            item.error = str(exc)
            item.logs.append(f"[launcher] {exc}")

        TASK_STORE.update(task_id, fail)
        return

    collected: list[str] = []
    assert process.stdout is not None
    for line in process.stdout:
        text = line.rstrip("\n")
        collected.append(text)
        TASK_STORE.update(task_id, lambda item, entry=text: item.logs.append(entry))

    exit_code = process.wait()
    result_text = "\n".join(collected).strip()
    result_json: Any | None = None
    if result_text:
        try:
            result_json = json.loads(result_text)
        except json.JSONDecodeError:
            result_json = None

    def finalize(item: CloudMailTask) -> None:
        item.exit_code = exit_code
        item.finished_at = time.time()
        item.result_text = result_text
        item.result_json = result_json
        item.status = "completed" if exit_code == 0 else "failed"
        if exit_code != 0:
            item.error = result_text.splitlines()[-1] if result_text else f"进程退出码 {exit_code}"

    TASK_STORE.update(task_id, finalize)


def serialize_task(task: CloudMailTask, *, offset: int = 0) -> dict[str, Any]:
    safe_offset = max(offset, 0)
    return {
        "id": task.id,
        "workflow": task.workflow,
        "label": task.label,
        "status": task.status,
        "command": task.command,
        "pretty_command": task.pretty_command,
        "cwd": task.cwd,
        "created_at": task.created_at,
        "started_at": task.started_at,
        "finished_at": task.finished_at,
        "exit_code": task.exit_code,
        "error": task.error,
        "logs": task.logs[safe_offset:],
        "next_offset": len(task.logs),
        "result_text": task.result_text,
        "result_json": task.result_json,
    }


@router.get("/workflows")
async def get_workflows():
    return {
        "toolkit_root": str(get_toolkit_root()),
        "python": PYTHON,
        "workflows": WORKFLOW_DEFS,
    }


@router.get("/main-domains", response_model=MainDomainsResponse)
async def get_main_domains():
    try:
        items = fetch_main_domains()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"读取主号域名失败: {exc}") from exc
    return MainDomainsResponse(total=len(items), items=[MainDomainItem(**item) for item in items])


@router.post("/preview")
async def preview_command(payload: TaskCreateRequest):
    try:
        return build_command(payload.workflow, payload.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tasks")
async def create_task(payload: TaskCreateRequest):
    try:
        built = build_command(payload.workflow, payload.params)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    task = CloudMailTask(
        id=uuid.uuid4().hex,
        workflow=payload.workflow,
        label=WORKFLOW_DEFS[payload.workflow]["label"],
        command=built["command"],
        pretty_command=built["pretty_command"],
        cwd=built["cwd"],
    )
    TASK_STORE.create(task)
    thread = threading.Thread(target=run_task, args=(task.id,), daemon=True)
    thread.start()
    return serialize_task(task)


@router.get("/tasks")
async def list_tasks():
    return {"tasks": [serialize_task(task, offset=len(task.logs)) for task in TASK_STORE.list()]}


@router.get("/tasks/{task_id}")
async def get_task(task_id: str, offset: int = Query(default=0, ge=0)):
    task = TASK_STORE.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return serialize_task(task, offset=offset)
