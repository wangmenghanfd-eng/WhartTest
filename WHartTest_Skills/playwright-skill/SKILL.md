---
name: playwright-skill
description: 浏览器自动化执行工具。用于执行 Web 页面测试、表单填写、登录验证、截图等浏览器操作。
---

# Playwright 浏览器自动化

执行浏览器自动化任务，支持页面测试、表单操作、登录验证等。

## ⚠️ 强制规则：先获取页面结构，再操作元素

**禁止猜测选择器！禁止通过截图识别元素！**

打开任何页面后，必须**立即**调用 `helpers.describePageForAI(page)` 获取页面元素列表，然后根据返回的选择器进行操作。

```javascript
// 打开页面后第一件事：获取页面结构
await page.goto('http://example.com');
const desc = await helpers.describePageForAI(page);
console.log(desc);  // 输出所有可交互元素及其选择器
```

输出示例：
```
## Page: WHartTest
URL: http://192.168.150.114:8913/login

### Input Fields (2)
- text: selector="#username" placeholder="请输入用户名"
- password: selector="#password" placeholder="请输入密码"

### Buttons (1)
- "登录": selector="button[type="submit"]"
```

然后根据输出的选择器进行操作：
```javascript
await page.fill('#username', 'admin');
await page.fill('#password', '123456');
await page.click('button[type="submit"]');
```

## 使用方法

通过 `execute_skill_script` 工具调用，传入 inline 代码：

```
node run.js "your playwright code here"
```

**重要**：代码必须写在一行，语句用分号分隔。run.js 会自动包装 async IIFE 和 require 语句。**禁止添加 --session、--inline、--eval 等参数，run.js 不支持这些参数。**

### ⚠️ 避免转义错误（最常见的失败原因）

inline 命令外层用双引号 `"..."` 包裹，所以**命令内部禁止再出现未转义的裸双引号**，否则会被 shell 截断成 `xxx: not found` 之类错误。硬性约定：

1. **字符串一律用单引号** `'...'`，不要用双引号。选择器里的属性值也用单引号：`page.fill('input[name=\"x\"]', 'v')` 这种需要转义的写法尽量避免，改用 `page.fill('#x', 'v')` 等无引号选择器。
2. **禁止使用反引号模板字符串**（`` `...` ``）。路径/消息拼接一律用 `+`，例如 `dir + '/a.png'`，不要写 `` `${dir}/a.png` ``。
3. **console.log 不要带冒号等特殊字符开头的裸文本**，先把值存进变量再打印：`const t = await page.title(); console.log('title', t);`
4. 命令越短越稳：一次只做一件事（先打开+截图，再单独取标题），不要把十几步塞进一行。

## WHartTest 功能测试执行链路

当你是在执行 WHartTest 的“功能测试用例”时，职责分工必须固定：

1. 先用 `whart-test` 读取测试用例详情，例如 `get_testcase_detail`。
2. 再用 `playwright-skill` 执行浏览器动作，命令只能是 `node run.js "..."`。
3. 对同一个用例，始终复用同一个 `session_id`，推荐格式：`case_{case_id}`。
4. 截图保存到 `process.env.SCREENSHOT_DIR`。
5. 最后回到 `whart-test` 调用 `upload_screenshot` 或 `upload_screenshots` 上传截图。

不要把下面这些旧链路/其他工具层名字当成当前技能的可执行命令：

- `python playwright_script.py --action execute_test_case`
- `browser_navigate`
- `browser_snapshot`
- `browser_take_screenshot`
- `save_operation_screenshots_to_the_application_case`
- `/path/to/screenshot1.png`

对当前技能来说，真正可执行的浏览器命令只有：

```bash
node run.js "your playwright code here"
```

## 截图路径约定

**必须使用环境变量 `process.env.SCREENSHOT_DIR`** 作为截图保存目录。系统会自动设置该变量指向 playwright-skill 目录下的 `media/screenshots/` 子目录。

截图命名建议：`case_{case_id}_step{step_number}.png`

**示例**：
```javascript
const screenshotDir = process.env.SCREENSHOT_DIR || './media/screenshots';
await page.screenshot({ path: `${screenshotDir}/case_11_step1.png` });
```

## 基础示例

### 打开页面并截图

```bash
node run.js "const dir = process.env.SCREENSHOT_DIR; const browser = await chromium.launch({ headless: true }); const page = await browser.newPage(); await page.goto('http://example.com'); await page.screenshot({ path: dir + '/example.png' }); console.log('截图已保存:', dir + '/example.png'); await browser.close();"
```

### 登录测试（带截图）

```bash
node run.js "const dir = process.env.SCREENSHOT_DIR; const browser = await chromium.launch({ headless: true, slowMo: 100 }); const page = await browser.newPage(); await page.goto('http://192.168.150.114:8913/'); await page.screenshot({ path: dir + '/step1_open.png' }); await page.fill('input[type=\"text\"]', 'admin'); await page.fill('input[type=\"password\"]', 'admin123456'); await page.screenshot({ path: dir + '/step2_filled.png' }); await page.click('button[type=\"submit\"]'); await page.waitForTimeout(2000); await page.screenshot({ path: dir + '/step3_result.png' }); console.log('截图已保存到', dir); await browser.close();"
```

### 表单填写

```bash
node run.js "const browser = await chromium.launch({ headless: true }); const page = await browser.newPage(); await page.goto('http://example.com/form'); await page.fill('input[name=\"username\"]', 'testuser'); await page.fill('input[name=\"email\"]', 'test@example.com'); await page.click('button[type=\"submit\"]'); console.log('表单提交完成'); await browser.close();"
```

## 其他 helpers 函数

### helpers.getPageStructure(page) - 获取结构化 JSON

返回 JSON 对象，适合程序化处理。

```javascript
const structure = await helpers.getPageStructure(page);
console.log(JSON.stringify(structure, null, 2));
```

### helpers.getPageText(page) - 获取纯文本内容

返回页面所有可见文本。

```javascript
const text = await helpers.getPageText(page);
console.log(text);
```

## 常用 API

### 浏览器启动

> ⚠️ **本技能运行在无显示器(no XServer)的容器内，浏览器必须 `headless: true`。**
> 禁止使用 `headless: false`——会报 `launched a headed browser without having a XServer running` 直接失败。
> （即使写了 `false`，run.js 也会强制改回 `true`，请直接写 `true` 避免误导。）

```javascript
// 无头模式（容器内唯一可用模式）
const browser = await chromium.launch({ headless: true });

// 需要放慢动作便于排查时，可加 slowMo（仍是无头）
const browser = await chromium.launch({ headless: true, slowMo: 100 });
```

### 页面导航

```javascript
await page.goto('http://example.com');
await page.goto('http://example.com', { waitUntil: 'networkidle' });
```

### ⚠️ 导航等待策略

默认不要把 `waitUntil: 'networkidle'` 当成通用等待策略。很多真实站点会持续发请求，容易导致：
- `Page.goto: Timeout ... waiting until "networkidle"`

优先策略：

```javascript
// 推荐：先正常打开
await page.goto('https://example.com/login');

// 再按目标显式等待
await page.waitForSelector('#username');
// 或
await page.waitForURL('**/secure');
```

只有在你确认页面确实需要等待网络完全安静时，才使用 `networkidle`。

### 元素定位与操作

```javascript
// 输入文本
await page.fill('input[name="username"]', 'admin');
await page.fill('input[type="password"]', '123456');

// 点击
await page.click('button[type="submit"]');
await page.click('text=登录');
await page.click('.login-btn');

// 等待元素
await page.waitForSelector('.success-message');
await page.waitForURL('**/dashboard');
```

### 常用选择器

| 选择器类型 | 示例 |
|-----------|------|
| CSS | `input[name="username"]`, `.login-btn`, `#submit` |
| 文本 | `text=登录`, `button:has-text("提交")` |
| 类型 | `input[type="text"]`, `input[type="password"]` |
| 占位符 | `input[placeholder*="账号"]`, `input[placeholder*="密码"]` |

### ⚠️ 验证页面跳转/登录成功

**优先用 URL 检查，而不是 `text=` 选择器**：

```javascript
// ✅ 推荐：等待 URL 变化（不依赖页面文字大小写）
await page.waitForURL('**/secure');

// ✅ 推荐：打印 URL 供 AI 判断
console.log(page.url());

// ❌ 禁止：text= 正则默认区分大小写
// 页面显示 "Secure Area"（大写 S），但选择器写 /secure/（小写），永远超时
await page.waitForSelector('text=/secure/');

// ✅ 若必须用文本正则，加 /i 标志忽略大小写
await page.waitForSelector('text=/secure area/i');
```

### ⚠️ 负向场景断言

对于“密码错误 / 用户名错误 / 权限不足”这类负向场景，不要先猜固定报错文案再死等 30 秒。

推荐顺序：

```javascript
// 先看 URL 是否仍停留在登录页
console.log(page.url());

// 再看页面实际文本
const text = await helpers.getPageText(page);
console.log(text);
```

然后再根据真实文本使用大小写不敏感匹配：

```javascript
await page.waitForSelector('text=/password is invalid/i');
```

如果第一次文本断言超时，优先重新读取页面文本或结构，而不是立刻刷新页面。

### 截图（使用环境变量）

```javascript
const dir = process.env.SCREENSHOT_DIR;
await page.screenshot({ path: `${dir}/screenshot.png` });
await page.screenshot({ path: `${dir}/full.png`, fullPage: true });
```

### 等待

```javascript
await page.waitForTimeout(2000);  // 等待2秒
await page.waitForLoadState('networkidle');  // 等待网络空闲
```

## 完整测试流程示例

执行一个完整的登录测试：

```bash
node run.js "const dir = process.env.SCREENSHOT_DIR; const browser = await chromium.launch({ headless: true, slowMo: 100 }); const page = await browser.newPage(); console.log('步骤1: 打开登录页'); await page.goto('http://192.168.150.114:8913/'); await page.screenshot({ path: dir + '/step1_open.png' }); console.log('步骤2: 输入账号'); await page.fill('input[type=\"text\"]', 'admin'); console.log('步骤3: 输入密码'); await page.fill('input[type=\"password\"]', 'admin123456'); await page.screenshot({ path: dir + '/step2_input.png' }); console.log('步骤4: 点击登录'); await page.click('button[type=\"submit\"]'); await page.waitForTimeout(2000); await page.screenshot({ path: dir + '/step3_result.png' }); console.log('登录结果 - 当前URL:', page.url()); await browser.close(); console.log('测试完成，截图保存在:', dir);"
```

## 注意事项

1. **截图路径**：必须使用 `process.env.SCREENSHOT_DIR` 环境变量
2. **代码格式**：inline 代码用分号分隔语句，写在一行内
3. **引号转义**：字符串内的双引号需要转义 `\"`
4. **browser.close()**：非持久化模式下执行完毕后务必关闭浏览器
5. **console.log()**：用于输出执行进度和结果
6. **headless: true**：容器内无显示器，必须无头模式，禁止 `headless: false`

## 持久化会话模式

对于需要**跨多个步骤保持浏览器打开**的场景（如自动化测试用例），使用 `session_id` 参数：

### ⚠️ 核心规则（必须严格遵守）

1. **session_id 必须完全一致**：整个测试流程中所有步骤**必须使用完全相同的 session_id 字符串**，否则会创建新浏览器导致状态丢失！
   - ✅ 正确：所有步骤都用 `session_id="case_11"`
   - ❌ 错误：第一步用 `case_11`，第二步用 `case-11`，第三步用 `test-case-11`（这会创建3个不同的浏览器！）
2. **直接使用 `page` 变量**：无需 `chromium.launch()`，系统自动管理
3. **不要调用 `browser.close()`**：浏览器由系统管理，空闲 15 分钟自动关闭

### 持久化模式示例

**步骤 1：打开页面**
```python
execute_skill_script(
    skill_name="playwright-skill",
    command='node run.js "await page.goto(\'http://example.com\'); console.log(page.url());"',
    session_id="test-case-001"
)
```

**步骤 2：填写表单（复用同一浏览器）**
```python
execute_skill_script(
    skill_name="playwright-skill",
    command='node run.js "await page.fill(\'input[name=username]\', \'admin\'); await page.fill(\'input[name=password]\', \'123456\');"',
    session_id="test-case-001"
)
```

**步骤 3：点击登录（继续复用）**
```python
execute_skill_script(
    skill_name="playwright-skill",
    command='node run.js "await page.click(\'button[type=submit]\'); await page.waitForTimeout(2000); console.log(\'登录后URL:\', page.url());"',
    session_id="test-case-001"
)
```

### 适合 WHartTest 的执行片段

```python
execute_skill_script(
    skill_name="playwright-skill",
    command='node run.js "const dir = process.env.SCREENSHOT_DIR; await page.goto(\'https://practice.expandtesting.com/login\'); const desc = await helpers.describePageForAI(page); console.log(desc); await page.fill(\'#username\', \'practice\'); await page.fill(\'#password\', \'SuperSecretPassword!\'); await page.screenshot({ path: `${dir}/case_11_step1.png` }); await page.click(\'button[type=submit]\'); await page.waitForURL(\'**/secure\'); await page.screenshot({ path: `${dir}/case_11_step2.png` }); console.log(page.url());"',
    session_id="case_11"
)
```

### 持久化 vs 非持久化对比

| 特性 | 非持久化（无 session_id） | 持久化（有 session_id） |
|------|--------------------------|------------------------|
| 浏览器生命周期 | 代码手动管理 | 系统自动管理 |
| 启动方式 | `chromium.launch()` | 直接使用 `page` |
| 关闭方式 | `browser.close()` | 自动关闭（15分钟空闲） |
| 跨步骤状态 | 不保持 | 保持（登录态、cookie等） |
| 适用场景 | 单步操作 | 多步骤测试用例 |
