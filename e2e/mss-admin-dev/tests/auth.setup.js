const { test, expect } = require('@playwright/test');
const STATE = 'state.json';

// 登录用例:真浏览器登录(平台前端会带 dev-token recaptcha + 加密密码),并保存会话供后续页面用例复用
test('登录: 凭证有效并进入门户', async ({ page }) => {
  await page.goto('/', { waitUntil: 'networkidle' });
  await page.fill('#username', 'ncema_admin');
  await page.fill('#password', 'Password123!');
  await page.locator('button:has-text("Sign in")').first().click();
  await page.waitForURL(/\/ncema\//, { timeout: 40000 });
  await expect(page).not.toHaveURL(/\/login/);
  await page.context().storageState({ path: STATE });
});
