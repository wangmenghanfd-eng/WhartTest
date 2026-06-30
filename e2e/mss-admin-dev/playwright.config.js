const { defineConfig } = require('@playwright/test');
module.exports = defineConfig({
  testDir: './tests',
  timeout: 90000,
  expect: { timeout: 20000 },
  retries: 1,
  workers: 1,
  reporter: [['list']],
  use: {
    baseURL: 'https://mss-admin-dev.marchbu.com',
    headless: true,
    viewport: { width: 1366, height: 900 },
    userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    locale: 'en-US',
    actionTimeout: 20000,
    navigationTimeout: 60000,
  },
  projects: [
    { name: 'setup', testMatch: /auth\.setup\.js/ },
    { name: 'anon', testMatch: /(anon|roles)\.spec\.js/, use: { storageState: { cookies: [], origins: [] } } },
    { name: 'ui', testMatch: /ui.*\.spec\.js/, dependencies: ['setup'], use: { storageState: 'state.json' } },
  ],
});
