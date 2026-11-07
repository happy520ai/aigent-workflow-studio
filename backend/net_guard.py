# backend/net_guard.py —— T12：LLM/HTTP api_base 请求时 IP 固定（防 DNS rebinding）
"""出站请求防护工具集（自 perfect_engine 抽出，供引擎与算子注册表共用，避免循环导入）。

- resolve_and_pin_api_base：请求前实时解析复检，返回按公网 IPv4 直连的 URL；
- IPPinnedTransport：按已校验 IP 直连，同时保留 Host 头与 TLS SNI（证书校验不受影响）。
"""
import asyncio
import ipaddress
import socket

import httpx


def _looks_like_ip(host: str) -> bool:
    try:
        ipaddress.ip_address(host)
        return True
    except ValueError:
        return False


def _is_forbidden_ip(ip: "ipaddress.IPv4Address | ipaddress.IPv6Address") -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
    )


def _validate_ip_literal(host: str) -> None:
    """IP 字面量直检（http_request 等用户自填 URL 场景：字面量不经 DNS，必须就地校验）"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return
    if _is_forbidden_ip(ip):
        raise ValueError(f"目标指向内网/保留地址，已拒绝: {host}")


async def resolve_and_pin_api_base(
    api_base: str, allow_private: bool = False, validate_ip_literals: bool = False
) -> str:
    """请求前实时解析 api_base 主机名并复检全部地址，返回按首个公网 IPv4 直连的 URL。

    设置接口的 SSRF 校验（validate_llm_api_base_async）与真实请求之间存在 TOCTOU：
    攻击者可在两次解析之间把域名改指内网（DNS rebinding）。本函数在每次真实请求前
    重新解析并校验，唯一拨号目标即本次校验通过的 IP，从根上消除该窗口。
    抛 ValueError 时由调用方按请求失败/降级处理（不外呼任何地址）。

    validate_ip_literals=True 时对 IP 字面量主机也执行内网/保留段检查（用户自填 URL 的
    算子场景必须开启；LLM 引擎路径保持 False 以兼容本地 llama.cpp 等 127.0.0.1 部署，
    其安全性由 AIGENT_ALLOW_PRIVATE_LLM 与设置接口守卫约束）。
    """
    url = httpx.URL(api_base)
    host = url.host
    if not host:
        raise ValueError("api_base 缺少主机名")
    if _looks_like_ip(host):
        if validate_ip_literals and not allow_private:
            _validate_ip_literal(host)
        # IP 字面量：settings 校验已把关（内网/回环），或 AIGENT_ALLOW_PRIVATE_LLM 显式放行
        return api_base
    addr_infos = await asyncio.to_thread(socket.getaddrinfo, host, None)
    pinned_ipv4: str | None = None
    for info in addr_infos:
        ip_text = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        if not allow_private and _is_forbidden_ip(ip):
            raise ValueError(f"api_base 指向内网/保留地址，已拒绝: {ip_text}")
        if pinned_ipv4 is None and ip.version == 4:
            pinned_ipv4 = ip_text
    if pinned_ipv4 is None:
        raise ValueError("api_base 无可用 IPv4 地址")
    return str(url.copy_with(host=pinned_ipv4))


class IPPinnedTransport(httpx.AsyncHTTPTransport):
    """把请求 URL 的主机改写为已校验 IP 直连，同时保留 Host 头与 TLS SNI（证书校验不受影响）。

    inner 参数供测试注入 httpx.MockTransport。
    """

    def __init__(self, pinned_ip: str, inner: httpx.AsyncBaseTransport | None = None):
        super().__init__()
        self._pinned_ip = pinned_ip
        self._inner = inner

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        target = request
        host = request.url.host
        if host and host != self._pinned_ip and not _looks_like_ip(host):
            original_host = request.headers.get("Host", host)
            target = httpx.Request(
                method=request.method,
                url=request.url.copy_with(host=self._pinned_ip),
                headers=request.headers,
                stream=request.stream,
            )
            target.extensions.update(request.extensions)
            if request.url.scheme == "https":
                # httpcore 扩展：按原域名做 SNI 与证书校验，仅按已校验 IP 建立连接
                target.extensions["sni_hostname"] = original_host
        if self._inner is not None:
            return await self._inner.handle_async_request(target)
        return await super().handle_async_request(target)
