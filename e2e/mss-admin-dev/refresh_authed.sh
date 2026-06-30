#!/bin/bash
# 刷新 MSS Admin Dev 已认证环境(env 41)的登录 Cookie:
#   1) 用 Playwright 真浏览器登录(处理密码加密 + dev-token recaptcha)
#   2) 抓取 SAFAR_ACCESS_TOKEN 等 Cookie
#   3) PATCH 平台 env 41 的 headers.Cookie
# 用法: bash refresh_authed.sh [username] [password]
set -e
U="${1:-ncema_admin}"; P="${2:-Password123!}"
cd /tmp/pw
node login2.js "$U" "$P" >/tmp/pw/refresh.log 2>&1
CK=$(cat /tmp/pw/cookie.txt)
if [ -z "$CK" ]; then echo "登录失败,未取到 Cookie,见 /tmp/pw/refresh.log"; exit 1; fi
TOK=$(curl -s -X POST http://127.0.0.1:8912/api/token/ -H 'Content-Type: application/json' \
  -d '{"username":"admin","password":"admin123456"}' \
  | python3 -c "import sys,json;d=json.load(sys.stdin);dd=d.get('data',d);print(dd.get('access') or d.get('access',''))")
python3 - "$TOK" "$CK" <<'PY'
import sys, json, urllib.request
tok, ck = sys.argv[1], sys.argv[2]
req = urllib.request.Request(
    "http://127.0.0.1:8912/api/api-automation/env-configs/41/",
    data=json.dumps({"headers": {"Cookie": ck}}).encode(),
    headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"},
    method="PATCH")
with urllib.request.urlopen(req, timeout=30) as r:
    print("env 41 cookie 已刷新, HTTP", r.status)
PY
echo "完成。可重跑已认证用例批次确认通过。"
