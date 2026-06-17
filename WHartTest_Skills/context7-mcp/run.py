#!/usr/bin/env python3
import argparse
import json
import os
import sys

import requests

BASE_URL = os.environ.get("CONTEXT7_API_BASE_URL", "https://context7.com/api/v2")
API_KEY = os.environ.get("CONTEXT7_API_KEY", "").strip()


def build_headers() -> dict:
    headers = {
        "Accept": "application/json",
        "User-Agent": "WHartTest-context7-skill/1.0",
    }
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"
    return headers


def do_get(path: str, params: dict) -> dict:
    resp = requests.get(
        f"{BASE_URL}{path}",
        headers=build_headers(),
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def print_json(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_library(args: argparse.Namespace) -> int:
    data = do_get(
        "/libs/search",
        {
            "libraryName": args.library_name,
            "query": args.query,
        },
    )
    if args.json:
        print_json(data)
        return 0

    results = data.get("results") or []
    if not results:
        print("未找到匹配的库。")
        return 0

    for idx, item in enumerate(results[: args.limit], start=1):
        print(f"[{idx}] {item.get('title')}")
        print(f"  id: {item.get('id')}")
        print(f"  benchmarkScore: {item.get('benchmarkScore')}")
        print(f"  trustScore: {item.get('trustScore')}")
        print(f"  snippets: {item.get('totalSnippets')}")
        if item.get("description"):
            print(f"  desc: {item.get('description')}")
        print()
    return 0


def cmd_docs(args: argparse.Namespace) -> int:
    library_id = args.library_id
    if not library_id and args.library:
        search = do_get(
            "/libs/search",
            {
                "libraryName": args.library,
                "query": args.query,
            },
        )
        results = search.get("results") or []
        if results:
            library_id = results[0].get("id")
    if not library_id:
        print("未提供 library_id，且无法从 --library 自动解析。", file=sys.stderr)
        return 2

    data = do_get(
        "/context",
        {
            "libraryId": library_id,
            "query": args.query,
            "type": "json",
        },
    )
    if args.json:
        print_json(data)
        return 0

    info_snippets = data.get("infoSnippets") or []
    code_snippets = data.get("codeSnippets") or []

    print(f"libraryId: {library_id}")
    print(f"query: {args.query}")
    print()

    if info_snippets:
        print("== Info Snippets ==")
        for idx, item in enumerate(info_snippets[:5], start=1):
            title = item.get("title") or item.get("breadcrumb") or f"info-{idx}"
            content = (item.get("content") or "").strip()
            print(f"[{idx}] {title}")
            print(content[:1200])
            print()

    if code_snippets:
        print("== Code Snippets ==")
        for idx, item in enumerate(code_snippets[:3], start=1):
            title = item.get("codeTitle") or f"code-{idx}"
            print(f"[{idx}] {title}")
            for block in (item.get("codeList") or [])[:2]:
                language = block.get("language") or "text"
                code = (block.get("code") or "").strip()
                print(f"```{language}")
                print(code[:1600])
                print("```")
            print()
    return 0


def cmd_ask(args: argparse.Namespace) -> int:
    search = do_get(
        "/libs/search",
        {
            "libraryName": args.library,
            "query": args.query,
        },
    )
    results = search.get("results") or []
    if not results:
        print("未找到匹配的库。")
        return 0

    best = results[0]
    docs = do_get(
        "/context",
        {
            "libraryId": best.get("id"),
            "query": args.query,
            "type": "json",
        },
    )
    payload = {
        "best_match": {
            "title": best.get("title"),
            "id": best.get("id"),
            "description": best.get("description"),
            "benchmarkScore": best.get("benchmarkScore"),
            "trustScore": best.get("trustScore"),
        },
        "docs": docs,
    }
    if args.json:
        print_json(payload)
        return 0

    print(f"best_match: {best.get('title')} ({best.get('id')})")
    print()
    info_snippets = docs.get("infoSnippets") or []
    code_snippets = docs.get("codeSnippets") or []
    for idx, item in enumerate(info_snippets[:3], start=1):
        title = item.get("title") or item.get("breadcrumb") or f"info-{idx}"
        print(f"[info {idx}] {title}")
        print((item.get("content") or "").strip()[:1200])
        print()
    for idx, item in enumerate(code_snippets[:2], start=1):
        print(f"[code {idx}] {item.get('codeTitle') or f'code-{idx}'}")
        for block in (item.get("codeList") or [])[:1]:
            print(f"```{block.get('language') or 'text'}")
            print((block.get("code") or "").strip()[:1600])
            print("```")
        print()
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    query = args.query or " ".join(args.query_parts or [])
    if not query:
        print("缺少查询词，请使用 --query 或直接在命令后写查询文本。", file=sys.stderr)
        return 2
    library = args.library or args.library_name or args.framework
    if library:
        ask_args = argparse.Namespace(library=library, query=query, json=args.json)
        return cmd_ask(ask_args)
    return cmd_library(
        argparse.Namespace(
            library_name=query.split()[0] if query.strip() else "",
            query=query,
            limit=args.limit,
            json=args.json,
        )
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Context7 skill runner")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_library = subparsers.add_parser("library", help="搜索库 ID")
    p_library.add_argument("library_name")
    p_library.add_argument("--query", required=True)
    p_library.add_argument("--limit", type=int, default=5)
    p_library.add_argument("--json", action="store_true")
    p_library.set_defaults(func=cmd_library)

    p_docs = subparsers.add_parser("docs", help="按库 ID 获取文档")
    p_docs.add_argument("library_id", nargs="?")
    p_docs.add_argument("--library")
    p_docs.add_argument("--query", required=True)
    p_docs.add_argument("--json", action="store_true")
    p_docs.set_defaults(func=cmd_docs)

    p_ask = subparsers.add_parser("ask", help="先检索库，再获取文档")
    p_ask.add_argument("--library", required=True)
    p_ask.add_argument("--query", required=True)
    p_ask.add_argument("--json", action="store_true")
    p_ask.set_defaults(func=cmd_ask)

    p_search = subparsers.add_parser("search", help="兼容旧调用方式，自动检索并返回文档")
    p_search.add_argument("--library")
    p_search.add_argument("--library-name")
    p_search.add_argument("--framework")
    p_search.add_argument("--action")
    p_search.add_argument("--query")
    p_search.add_argument("query_parts", nargs="*")
    p_search.add_argument("--limit", type=int, default=5)
    p_search.add_argument("--json", action="store_true")
    p_search.set_defaults(func=cmd_search)

    p_get_doc = subparsers.add_parser("get_doc", help="兼容旧调用方式，等价于 search/ask")
    p_get_doc.add_argument("--library")
    p_get_doc.add_argument("--library-name")
    p_get_doc.add_argument("--framework")
    p_get_doc.add_argument("--action")
    p_get_doc.add_argument("--query")
    p_get_doc.add_argument("query_parts", nargs="*")
    p_get_doc.add_argument("--limit", type=int, default=5)
    p_get_doc.add_argument("--json", action="store_true")
    p_get_doc.set_defaults(func=cmd_search)

    p_get_latest = subparsers.add_parser("get_latest_docs", help="兼容更旧的调用方式")
    p_get_latest.add_argument("--library")
    p_get_latest.add_argument("--library-name")
    p_get_latest.add_argument("--framework")
    p_get_latest.add_argument("--action")
    p_get_latest.add_argument("--query")
    p_get_latest.add_argument("query_parts", nargs="*")
    p_get_latest.add_argument("--limit", type=int, default=5)
    p_get_latest.add_argument("--json", action="store_true")
    p_get_latest.set_defaults(func=cmd_search)

    args, _unknown = parser.parse_known_args()
    try:
        return args.func(args)
    except requests.HTTPError as exc:
        response = exc.response
        body = ""
        try:
            body = response.text[:1000]
        except Exception:
            body = str(exc)
        print(f"Context7 请求失败: HTTP {response.status_code}\n{body}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Context7 执行失败: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
