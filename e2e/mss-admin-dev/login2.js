const { chromium } = require('playwright');
const SITE = 'https://mss-admin-dev.marchbu.com/';
const USER = process.argv[2] || 'ncema_admin';
const PASS = process.argv[3] || 'Password123!';

(async () => {
  const browser = await chromium.launch({ headless: true });
  const ctx = await browser.newContext({
    locale: 'en-US', viewport: { width: 1366, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
  });
  const page = await ctx.newPage();
  let loginReq = null, loginStatus = null;
  page.on('request', (r) => { if (/\/auth\/login(\b|\?|$)/.test(r.url()) && r.method()==='POST') { loginReq = r.postData(); } });
  page.on('response', (r) => { if (/\/auth\/login(\b|\?|$)/.test(r.url()) && r.request().method()==='POST') loginStatus = r.status(); });

  await page.goto(SITE, { waitUntil: 'networkidle', timeout: 60000 }).catch(()=>{});
  await page.waitForTimeout(2000);
  await page.fill('#username', USER).catch(()=>{});
  await page.fill('#password', PASS).catch(()=>{});
  await page.locator('button:has-text("Sign in")').first().click().catch(()=>{});
  await page.waitForTimeout(7000);
  console.log('loginStatus:', loginStatus);
  console.log('loginReq payload:', loginReq);
  console.log('URL after login:', page.url());

  const cookies = await ctx.cookies();
  console.log('COOKIES:', JSON.stringify(cookies.map(c => ({name:c.name, domain:c.domain, path:c.path, httpOnly:c.httpOnly, len:(c.value||'').length})), null, 1));

  // try an authenticated admin call using the browser session
  const probe = await page.evaluate(async () => {
    const tryUrl = async (u) => { try { const r = await fetch(u, {credentials:'include'}); const t = await r.text(); return {u, status:r.status, body:t.slice(0,160)}; } catch(e){ return {u, err:String(e)}; } };
    return {
      cases: await tryUrl('/api/v1/admin/cases'),
      stats: await tryUrl('/api/v1/admin/dashboard/stats'),
      me: await tryUrl('/api/v1/auth/me'),
    };
  });
  console.log('AUTHED_PROBE:', JSON.stringify(probe, null, 1));

  // save full cookie header string for reuse
  const cookieHeader = cookies.filter(c => /marchbu/.test(c.domain)).map(c => `${c.name}=${c.value}`).join('; ');
  require('fs').writeFileSync('/tmp/pw/cookie.txt', cookieHeader);
  console.log('cookieHeader length:', cookieHeader.length);
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
