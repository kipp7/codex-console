"""
代理工具
处理容器环境下本机回环地址不可达的问题。
"""

from __future__ import annotations

import os
from urllib.parse import SplitResult, urlsplit, urlunsplit


_LOCAL_PROXY_HOSTS = {"127.0.0.1", "localhost", "::1"}
_DOCKER_HOST_ALIAS = os.getenv("DOCKER_HOST_PROXY", "host.docker.internal")


def is_running_in_container() -> bool:
    """粗略判断当前进程是否运行在容器内。"""
    return os.path.exists("/.dockerenv") or os.getenv("RUNNING_IN_DOCKER") == "1"


def normalize_proxy_url(proxy_url: str | None) -> str | None:
    """
    在容器环境中将回环代理地址改写为宿主机地址。

    例如: http://127.0.0.1:7897 -> http://host.docker.internal:7897
    """
    if not proxy_url or not is_running_in_container():
        return proxy_url

    try:
        parsed = urlsplit(proxy_url)
        if parsed.hostname not in _LOCAL_PROXY_HOSTS:
            return proxy_url

        auth = ""
        if parsed.username:
            auth = parsed.username
            if parsed.password:
                auth = f"{auth}:{parsed.password}"
            auth = f"{auth}@"

        port = f":{parsed.port}" if parsed.port else ""
        normalized = SplitResult(
            scheme=parsed.scheme,
            netloc=f"{auth}{_DOCKER_HOST_ALIAS}{port}",
            path=parsed.path,
            query=parsed.query,
            fragment=parsed.fragment,
        )
        return urlunsplit(normalized)
    except Exception:
        return proxy_url
