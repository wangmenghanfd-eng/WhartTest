# MSS Admin Dev — UI 自动化用例 (Playwright)

针对测试站点 `https://mss-admin-dev.marchbu.com/`(UCMDS Review Console,Spring Boot `safar-api` + React SPA)的 UI 自动化用例。

## 登录说明(重要)
站点登录受 reCAPTCHA 保护,且密码经前端 RSA 加密。**纯 curl/接口无法登录**;dev 前端会自动带 `recaptchaToken:"dev-token"` 旁路。本套件用 **真实浏览器(Playwright Chromium)** 走完整登录,因此能稳定通过。鉴权态保存在 httpOnly Cookie(`SAFAR_ACCESS_TOKEN`)。

## 运行
```bash
cd e2e/mss-admin-dev
npm i -D playwright @playwright/test
npx playwright install chromium
npx playwright test
```

## 用例清单(共 19,均通过)
- `auth.setup.js` — 登录(ncema_admin)并保存会话 `state.json` 供后续复用(1)
- `anon.spec.js` — 未登录访问门户跳转登录、错误密码不进入门户(2,负向/鉴权守卫)
- `roles.spec.js` — 多角色登录:ncema_admin / mod_admin / moi_admin / csc_admin / fp_admin(5)
- `ui.spec.js` — 8 个门户菜单页加载:Dashboard / Crises / NCEMA Reports / File Verification / Early Feedback / Users / Roles / Permission Grants(8,断言:不被踢回登录 + 无错误边界 + 主内容非空)
- `ui2.spec.js` — Crises 卡片数据(CRISIS-xxxx)、Users 数据表格、顶栏通知控件(3)

## 配套(供平台「接口自动化」的已认证用例刷新)
`refresh_authed.sh` / `login2.js`:真浏览器登录抓取 Cookie,并 PATCH 平台 env 41 的 `Cookie` 头,用于刷新平台中已认证 API 用例的登录态(令牌过期时执行)。

## 账号
所有部门账号密码均为 `Password123!`(`admin` 为 `123456`,带角色切换下拉)。
