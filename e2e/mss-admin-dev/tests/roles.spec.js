const { test, expect } = require('@playwright/test');

// 多角色登录用例(无登录态项目 anon):验证不同部门账号都能登录进入各自门户
const ACCOUNTS = [
  'ncema_admin',
  'mod_admin',
  'moi_admin',
  'csc_admin',
  'fp_admin',
];

for (const username of ACCOUNTS) {
  test(`多角色登录: ${username} 可进入门户`, async ({ page }) => {
    await page.goto('/', { waitUntil: 'networkidle' });
    await page.fill('#username', username);
    await page.fill('#password', 'Password123!');
    await page.locator('button:has-text("Sign in")').first().click();
    // 登录成功后离开 /login(各部门门户前缀可能不同, 故只断言不再停留登录页)
    await page.waitForURL((u) => !/\/login/.test(u.pathname), { timeout: 40000 });
    await expect(page).not.toHaveURL(/\/login/);
    // 已登录外壳: 顶栏通知控件存在
    await expect(page.locator('[aria-label*="Notifications" i]').first()).toBeVisible({ timeout: 20000 });
  });
}
