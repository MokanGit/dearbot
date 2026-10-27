import asyncio
import socket
import time
import ipaddress
from typing import Dict, Any, Optional
import httpx

# In-memory LRU cache for IP intelligence to ensure 0 ms latency on repeat queries
_IP_CACHE: Dict[str, Dict[str, Any]] = {}
_INFLIGHT_LOOKUPS: Dict[str, asyncio.Task] = {}
_MAX_CACHE_SIZE = 10000
_LOOKUP_SEMAPHORE = asyncio.Semaphore(30)
_IP_API_COOLDOWN_UNTIL: float = 0.0
_SHARED_HTTP_CLIENT: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _SHARED_HTTP_CLIENT
    if _SHARED_HTTP_CLIENT is None or _SHARED_HTTP_CLIENT.is_closed:
        _SHARED_HTTP_CLIENT = httpx.AsyncClient(
            timeout=httpx.Timeout(0.6, connect=0.4),
            limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
        )
    return _SHARED_HTTP_CLIENT


def is_private_or_local_ip(ip: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(ip)
        return ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved or ip_obj.is_link_local
    except ValueError:
        return True


async def resolve_reverse_dns(ip: str) -> Optional[str]:
    """Resolves reverse DNS hostname asynchronously without blocking the event loop."""
    try:
        loop = asyncio.get_running_loop()
        result = await asyncio.wait_for(
            loop.run_in_executor(None, lambda: socket.gethostbyaddr(ip)),
            timeout=0.5,
        )
        return result[0]
    except Exception:
        return None


async def _lookup_ip_once(ip: str) -> Dict[str, Any]:
    global _IP_API_COOLDOWN_UNTIL
    async with _LOOKUP_SEMAPHORE:
        if ip in _IP_CACHE:
            return _IP_CACHE[ip]

        reverse_dns_task = asyncio.create_task(resolve_reverse_dns(ip))
        geo_data: Dict[str, Any] = {}

        if time.time() >= _IP_API_COOLDOWN_UNTIL:
            try:
                url = f"http://ip-api.com/json/{ip}?fields=status,message,country,regionName,city,isp,org,as"
                client = _get_http_client()
                resp = await client.get(url)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("status") == "success":
                        geo_data = {
                            "organization": data.get("org") or data.get("isp"),
                            "isp": data.get("isp"),
                            "country": data.get("country"),
                            "city": data.get("city"),
                            "region": data.get("regionName"),
                            "asn": data.get("as"),
                        }
                elif resp.status_code == 429:
                    _IP_API_COOLDOWN_UNTIL = time.time() + 60.0
            except Exception:
                _IP_API_COOLDOWN_UNTIL = time.time() + 15.0

        reverse_dns = await reverse_dns_task

        result = {
            "organization": geo_data.get("organization") or reverse_dns or "Unknown Organization",
            "isp": geo_data.get("isp"),
            "country": geo_data.get("country"),
            "city": geo_data.get("city"),
            "region": geo_data.get("region"),
            "asn": geo_data.get("asn"),
            "reverse_dns": reverse_dns,
        }
        if len(_IP_CACHE) >= _MAX_CACHE_SIZE:
            _IP_CACHE.pop(next(iter(_IP_CACHE)), None)
        _IP_CACHE[ip] = result
        return result


async def enrich_ip_intelligence(ip: str) -> Dict[str, Any]:
    """
    Fetches organization, ISP, ASN, city, region and country for a given IP address.
    Caches results in memory and deduplicates concurrent in-flight lookups for the same IP.
    """
    if not ip or is_private_or_local_ip(ip):
        return {
            "organization": "Local / Private Network",
            "isp": "Local",
            "country": "Local",
            "city": "Internal",
            "region": "Internal",
            "asn": None,
            "reverse_dns": None,
        }

    if ip in _IP_CACHE:
        return _IP_CACHE[ip]

    inflight = _INFLIGHT_LOOKUPS.get(ip)
    if inflight is None or inflight.done():
        inflight = asyncio.create_task(_lookup_ip_once(ip))
        _INFLIGHT_LOOKUPS[ip] = inflight

    try:
        return await asyncio.shield(inflight)
    finally:
        if _INFLIGHT_LOOKUPS.get(ip) is inflight and inflight.done():
            _INFLIGHT_LOOKUPS.pop(ip, None)
