#!/usr/bin/env python3
import argparse
import json
import os
import re
import sys
from html import unescape
from urllib.parse import quote, urljoin, urlparse
import ipaddress
import socket

import requests
from bs4 import BeautifulSoup

FIRECRAWL_API_BASE = os.environ.get("FIRECRAWL_API_BASE_URL", "https://api.firecrawl.dev")
FIRECRAWL_API_KEY = os.environ.get("FIRECRAWL_API_KEY", "").strip()


def firecrawl_headers() -> dict:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "WHartTest-firecrawl-skill/1.0",
    }
    if FIRECRAWL_API_KEY:
        headers["Authorization"] = f"Bearer {FIRECRAWL_API_KEY}"
    return headers


def cleanup_text(text: str) -> str:
    text = unescape(text or "")
    text = re.sub(r"\s+", " ", text).strip()
    return text


def local_search(query: str, limit: int) -> dict:
    url = f"https://html.duckduckgo.com/html/?q={quote(query)}"
    resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    results = []
    for node in soup.select(".result")[:limit]:
        link = node.select_one(".result__title a")
        snippet = node.select_one(".result__snippet")
        href = link.get("href") if link else ""
        title = cleanup_text(link.get_text(" ", strip=True) if link else "")
        summary = cleanup_text(snippet.get_text(" ", strip=True) if snippet else "")
        if title and href:
            results.append({"title": title, "url": href, "snippet": summary})
    return {"mode": "local-fallback", "results": results}


def _ip_is_blocked(ip_str: str) -> bool:
    """判断某个具体 IP 是否落在禁止访问的网段。"""
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True  # 解析不出合法 IP，一律拒绝
    # 解包 IPv4-mapped IPv6（如 ::ffff:127.0.0.1），防止用映射地址绕过
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return (
        ip.is_private        # 10/8、172.16/12、192.168/16、fc00::/7
        or ip.is_loopback    # 127/8、::1
        or ip.is_link_local  # 169.254/16（含云元数据 169.254.169.254）、fe80::/10
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified  # 0.0.0.0、::
    )


def _assert_public_http_url(url: str) -> None:
    """校验 URL：必须是 http/https，且主机名解析出的所有 IP 都不在内网/保留段。"""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"仅允许 http/https，已拒绝协议: {parsed.scheme or '(空)'}")
    host = parsed.hostname
    if not host:
        raise ValueError("URL 缺少主机名")
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    # 关键：解析主机名 → 校验解析出的每个 A/AAAA 记录；
    # 只要有一个指向内网/保留段就拒绝（挡住“域名指向内网”的绕过）。
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise ValueError(f"无法解析主机名 {host}: {exc}")
    for info in infos:
        ip_str = info[4][0]
        if _ip_is_blocked(ip_str):
            raise ValueError(f"目标 {host} 解析到受限地址 {ip_str}，已拒绝（SSRF 防护）")


def _safe_get(url: str, *, timeout: int, max_redirects: int = 5) -> requests.Response:
    """逐跳手动跟随重定向，每跳都重新校验目标地址；禁用 requests 自动跳转。"""
    current = url
    for _ in range(max_redirects + 1):
        _assert_public_http_url(current)
        resp = requests.get(
            current,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=timeout,
            allow_redirects=False,  # 不让 requests 自动跳转，避免公网域名 302→内网
        )
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("Location")
            if not location:
                return resp
            current = urljoin(current, location)  # 相对跳转归一化后再校验
            continue
        return resp
    raise ValueError(f"重定向次数超过 {max_redirects}，已中止（疑似跳转规避）")


def local_scrape(url: str) -> dict:
    resp = _safe_get(url, timeout=45)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    title = cleanup_text(soup.title.get_text(" ", strip=True) if soup.title else "")
    body = soup.body or soup
    lines = []
    for element in body.find_all(["h1", "h2", "h3", "p", "li"], limit=300):
        text = cleanup_text(element.get_text(" ", strip=True))
        if text:
            lines.append(text)
    content = "\n".join(lines[:150])
    return {"mode": "local-fallback", "url": url, "title": title, "content": content}


def api_search(query: str, limit: int) -> dict:
    resp = requests.post(
        f"{FIRECRAWL_API_BASE}/v2/search",
        headers=firecrawl_headers(),
        json={"query": query, "limit": limit},
        timeout=45,
    )
    resp.raise_for_status()
    return resp.json()


def api_scrape(url: str) -> dict:
    resp = requests.post(
        f"{FIRECRAWL_API_BASE}/v2/scrape",
        headers=firecrawl_headers(),
        json={"url": url, "formats": ["markdown"]},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_status(_: argparse.Namespace) -> int:
    if FIRECRAWL_API_KEY:
        print("mode: firecrawl-api")
        print("api_key: configured")
        return 0
    print("mode: local-fallback")
    print("api_key: missing")
    print("说明: search/scrape 可执行；高级 interact/crawl/monitor 需配置 FIRECRAWL_API_KEY 或改用浏览器技能。")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query or " ".join(args.query_parts or [])
    if not query:
        print("缺少查询词，请使用 --query 或直接在 search 后写查询文本。", file=sys.stderr)
        return 2
    payload = api_search(query, args.limit) if FIRECRAWL_API_KEY else local_search(query, args.limit)
    if args.json:
        print_json(payload)
        return 0

    results = payload.get("results") or payload.get("data", {}).get("web") or []
    print(f"mode: {payload.get('mode', 'firecrawl-api')}")
    print(f"query: {query}")
    print()
    for idx, item in enumerate(results[: args.limit], start=1):
        title = item.get("title") or item.get("metadata", {}).get("title") or f"result-{idx}"
        url = item.get("url") or item.get("link") or ""
        snippet = item.get("snippet") or item.get("description") or item.get("markdown") or ""
        print(f"[{idx}] {title}")
        print(url)
        if snippet:
            print(cleanup_text(str(snippet))[:500])
        print()
    return 0


def cmd_scrape(args: argparse.Namespace) -> int:
    url = args.url or (args.url_parts[0] if args.url_parts else "")
    if not url:
        print("缺少 URL，请使用 --url 或直接在 scrape 后写 URL。", file=sys.stderr)
        return 2
    payload = api_scrape(url) if FIRECRAWL_API_KEY else local_scrape(url)
    if args.json:
        print_json(payload)
        return 0

    print(f"mode: {payload.get('mode', 'firecrawl-api')}")
    print(f"url: {url}")
    title = payload.get("title") or payload.get("metadata", {}).get("title") or payload.get("data", {}).get("metadata", {}).get("title")
    if title:
        print(f"title: {title}")
    print()
    if "content" in payload:
        print(payload["content"][:4000])
    else:
        data = payload.get("data") or {}
        markdown = data.get("markdown") or payload.get("markdown") or ""
        if markdown:
            print(markdown[:4000])
        else:
            print_json(payload)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Firecrawl-compatible skill runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_status = subparsers.add_parser("status")
    p_status.set_defaults(func=cmd_status)

    p_search = subparsers.add_parser("search")
    p_search.add_argument("--query")
    p_search.add_argument("query_parts", nargs="*")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--summary", action="store_true")
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_scrape = subparsers.add_parser("scrape")
    p_scrape.add_argument("--url")
    p_scrape.add_argument("url_parts", nargs="*")
    p_scrape.add_argument("--json", action="store_true")
    p_scrape.set_defaults(func=cmd_scrape)

    args = parser.parse_args()
    try:
        return args.func(args)
    except requests.HTTPError as exc:
        response = exc.response
        body = ""
        try:
            body = response.text[:1000]
        except Exception:
            body = str(exc)
        print(f"Firecrawl 请求失败: HTTP {response.status_code}\n{body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Firecrawl 执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
