const { test, expect } = require('@playwright/test');

const PAGES = [
  'Dashboard',
  'Crises',
  'NCEMA Reports',
  'File Verification',
  'Early Feedback',
  'Users',
  'Roles',
  'Permission Grants',
];

test.describe('门户页面加载(已认证)', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/ncema/reports', { waitUntil: 'domcontentloaded' });
    await page.waitForTimeout(2000);
    await expect(page, '会话应有效, 不应跳回登录页').not.toHaveURL(/\/login/);
  });

  for (const name of PAGES) {
    test(`页面加载: ${name}`, async ({ page }) => {
      // 优先点 antd menuitem, 退化到文本
      const byRole = page.getByRole('menuitem', { name, exact: true });
      if (await byRole.count()) {
        await byRole.first().click();
      } else {
        await page.getByText(name, { exact: true }).first().click();
      }
      await page.waitForLoadState('networkidle').catch(() => {});
      await page.waitForTimeout(2000);

      // 1) 未被踢回登录
      await expect(page).not.toHaveURL(/\/login/);
      // 2) 没有错误边界
      await expect(page.locator('text=/something went wrong/i')).toHaveCount(0);
      await expect(page.locator('text=/页面出错|发生错误/')).toHaveCount(0);
      // 3) 主内容已渲染(非空)
      const main = page.locator('.ant-layout-content, main, #root').first();
      const txt = (await main.innerText().catch(() => '')).trim();
      expect(txt.length, `${name} 主内容应非空`).toBeGreaterThan(20);
    });
  }
});
