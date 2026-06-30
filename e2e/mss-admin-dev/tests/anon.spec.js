const { test, expect } = require('@playwright/test');

// 这些用例不带登录态(项目 anon 用空 storageState)

test('未登录访问受保护门户页应跳转登录', async ({ page }) => {
  await page.goto('/ncema/reports', { waitUntil: 'networkidle' });
  await page.waitForTimeout(2500);
  await expect(page, '未登录应被重定向到 /login').toHaveURL(/\/login/);
});

test('登录失败: 错误密码不应进入门户', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#username', 'ncema_admin');
  await page.fill('#password', 'WrongPassword!!!');
  await page.locator('button:has-text("Sign in")').first().click();
  await page.waitForTimeout(6000);
  // 不应跳进门户;应仍停留在登录页且用户名输入仍在
  await expect(page).not.toHaveURL(/\/ncema\//);
  await expect(page).toHaveURL(/\/login/);
  await expect(page.locator('#username')).toBeVisible();
});
