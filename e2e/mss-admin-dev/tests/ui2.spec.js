const { test, expect } = require('@playwright/test');

// 已认证的列表页交互/数据渲染用例(项目 ui 提供登录态)

async function gotoMenu(page, name) {
  await page.goto('/ncema/reports', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(1500);
  await expect(page).not.toHaveURL(/\/login/);
  const byRole = page.getByRole('menuitem', { name, exact: true });
  if (await byRole.count()) await byRole.first().click();
  else await page.getByText(name, { exact: true }).first().click();
  await page.waitForLoadState('networkidle').catch(() => {});
  await page.waitForTimeout(2500);
}

test('Crises 页面渲染危机数据(卡片)', async ({ page }) => {
  await gotoMenu(page, 'Crises');
  // Crises 为卡片布局(非表格):断言出现真实危机编号 CRISIS-xxxx
  await expect(page.getByText(/CRISIS-\d/).first()).toBeVisible();
});

test('Users 页面渲染数据表格', async ({ page }) => {
  await gotoMenu(page, 'Users');
  await expect(page.locator('.ant-table, table').first()).toBeVisible();
});

test('门户顶栏通知控件可见(已登录外壳渲染)', async ({ page }) => {
  await page.goto('/ncema/reports', { waitUntil: 'domcontentloaded' });
  await page.waitForTimeout(2000);
  await expect(page).not.toHaveURL(/\/login/);
  // 已登录的外壳:存在通知按钮(aria 含 Notifications)
  await expect(page.locator('[aria-label*="Notifications" i]').first()).toBeVisible();
});
