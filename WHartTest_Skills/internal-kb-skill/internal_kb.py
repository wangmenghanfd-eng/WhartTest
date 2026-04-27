# -*- coding: utf-8 -*-
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

import argparse
import json
import os
from pathlib import Path

import requests

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
except ImportError:
    pass


BASE_URL = (os.getenv("WHARTTEST_BACKEND_URL") or "http://127.0.0.1:8000").rstrip("/")
API_KEY = os.getenv("WHARTTEST_API_KEY") or "wharttest-default-mcp-key-2025"
HEADERS = {
    "accept": "application/json, text/plain, */*",
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}


def _handle_response(resp):
    resp.raise_for_status()
    try:
        return resp.json()
    except Exception:
        return {"raw": resp.text}


def list_knowledge_bases():
    return _handle_response(
        requests.get(f"{BASE_URL}/api/knowledge/knowledge-bases/", headers=HEADERS, timeout=30)
    )


def get_global_config():
    return _handle_response(
        requests.get(f"{BASE_URL}/api/knowledge/global-config/", headers=HEADERS, timeout=30)
    )


def get_system_status():
    return _handle_response(
        requests.get(f"{BASE_URL}/api/knowledge/knowledge-bases/system_status/", headers=HEADERS, timeout=30)
    )


def list_documents(knowledge_base_id: str):
    return _handle_response(
        requests.get(
            f"{BASE_URL}/api/knowledge/documents/",
            headers=HEADERS,
            params={"knowledge_base": knowledge_base_id},
            timeout=30,
        )
    )


def query_knowledge_base(knowledge_base_id: str, query: str, top_k: int = 5, similarity_threshold: float = 0.1):
    payload = {
        "query": query,
        "knowledge_base_id": knowledge_base_id,
        "top_k": top_k,
        "similarity_threshold": similarity_threshold,
        "include_metadata": True,
    }
    return _handle_response(
        requests.post(
            f"{BASE_URL}/api/knowledge/knowledge-bases/{knowledge_base_id}/query/",
            headers=HEADERS,
            data=json.dumps(payload, ensure_ascii=False),
            timeout=60,
        )
    )


def test_embedding_connection(embedding_service: str, api_base_url: str, model_name: str, api_key: str = ""):
    payload = {
        "embedding_service": embedding_service,
        "api_base_url": api_base_url,
        "model_name": model_name,
        "api_key": api_key,
    }
    return _handle_response(
        requests.post(
            f"{BASE_URL}/api/knowledge/test-embedding-connection/",
            headers=HEADERS,
            data=json.dumps(payload, ensure_ascii=False),
            timeout=60,
        )
    )


def test_reranker_connection(reranker_service: str, reranker_api_url: str, reranker_model_name: str, reranker_api_key: str = ""):
    payload = {
        "reranker_service": reranker_service,
        "reranker_api_url": reranker_api_url,
        "reranker_model_name": reranker_model_name,
        "reranker_api_key": reranker_api_key,
    }
    return _handle_response(
        requests.post(
            f"{BASE_URL}/api/knowledge/test-reranker-connection/",
            headers=HEADERS,
            data=json.dumps(payload, ensure_ascii=False),
            timeout=60,
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--action", required=True)
    parser.add_argument("--knowledge_base_id")
    parser.add_argument("--query")
    parser.add_argument("--top_k", type=int, default=5)
    parser.add_argument("--similarity_threshold", type=float, default=0.1)
    parser.add_argument("--embedding_service")
    parser.add_argument("--api_base_url")
    parser.add_argument("--model_name")
    parser.add_argument("--api_key", default="")
    parser.add_argument("--reranker_service")
    parser.add_argument("--reranker_api_url")
    parser.add_argument("--reranker_model_name")
    parser.add_argument("--reranker_api_key", default="")
    args = parser.parse_args()

    actions = {
        "list_knowledge_bases": lambda: list_knowledge_bases(),
        "get_global_config": lambda: get_global_config(),
        "get_system_status": lambda: get_system_status(),
        "list_documents": lambda: list_documents(args.knowledge_base_id),
        "query_knowledge_base": lambda: query_knowledge_base(args.knowledge_base_id, args.query, args.top_k, args.similarity_threshold),
        "test_embedding_connection": lambda: test_embedding_connection(args.embedding_service, args.api_base_url, args.model_name, args.api_key),
        "test_reranker_connection": lambda: test_reranker_connection(args.reranker_service, args.reranker_api_url, args.reranker_model_name, args.reranker_api_key),
    }

    if args.action not in actions:
        print(json.dumps({"error": f"未知 action: {args.action}"}, ensure_ascii=False, indent=2))
        sys.exit(1)

    try:
        result = actions[args.action]()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
