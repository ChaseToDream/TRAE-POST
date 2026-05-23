# 全面修复帖子数据不同步问题

## 问题全景分析

经过全面检查，数据不同步的问题存在于**三个层面**，之前的修复只改了代码逻辑，但没有解决实际的数据和缓存问题：

### 层面1：数据文件过期（最关键）
- `data/posts.json` 的 `updated_at` 仍为 `2026-05-23T06:32:09Z`
- **虽然我们修改了 `fetch_posts.py` 的代码逻辑，但脚本从未被重新执行过**
- 前端展示的数据永远是这个旧文件的内容，无论代码怎么改都不会生效
- **必须删除旧数据文件并重新运行脚本**

### 层面2：前端缓存问题
- **初始加载无缓存破坏**：`app.js` 第925行 `fetch(DATA_PATH)` 没有 `?t=` 参数，浏览器会缓存 `posts.json`
- **`refreshData` 过早返回**：第853行 `if (data.updated_at && data.updated_at === state.updatedAt) return;` — 如果 `updated_at` 没变就跳过更新，但实际帖子数据可能已变
- **无 HTTP 缓存控制头**：`python -m http.server` 不设置 `Cache-Control` 头，浏览器可能缓存 JSON 文件

### 层面3：Python 脚本逻辑残留问题
- `fetch_user_topics` 函数仍保留 `existing_ids` 参数（虽然调用时不再传入，但函数内部仍用它初始化 `seen_ids`，造成混淆）
- `merge_posts` 的"增量合并"逻辑与"全量刷新"的设计理念矛盾 — 既然每次都通过详情 API 刷新所有帖子，就不需要复杂的合并逻辑
- 详情 API 返回的 `excerpt` 可能为空（Discourse 的 `/t/{id}.json` 不一定返回 excerpt），`apply_refresh_data` 中的 `if detail.get("excerpt")` 条件会导致空值时不更新，保留旧的 excerpt

---

## 修复步骤

### 步骤1：删除旧的 `posts.json` 数据文件
**文件**：`data/posts.json`

删除旧数据文件，确保下次运行脚本时从零开始全量抓取，不残留任何过时数据。

### 步骤2：重构 `fetch_posts.py` 主流程 — 简化为纯全量模式
**文件**：`scripts/fetch_posts.py`

**2a. 清理 `fetch_user_topics` 函数**：
- 移除 `existing_ids` 参数
- 函数内部 `seen_ids` 仅用于页内去重

**2b. 简化 `main()` 流程**：
- 移除 `load_existing_data()` 和 `merge_posts()` 调用
- 改为：列表API获取帖子ID → 详情API获取所有帖子最新数据 → 直接输出
- 不再加载旧数据，不再合并，完全以本次抓取的数据为准

**2c. 修复 `apply_refresh_data` 中的条件判断**：
- `excerpt` 字段：即使详情API返回空值，也应该更新（帖子可能被编辑删除了摘要）
- 改为无条件覆盖所有可变字段，不再用 `if detail.get("xxx")` 做守卫

**2d. 增强 `fetch_topic_details`**：
- 从详情API提取更多字段：`fancy_title`（带格式的标题，作为 title 的备选）、`description`（作为 excerpt 的备选）
- Discourse 的 `/t/{id}.json` 返回 `title` 和 `fancy_title`，以及 `posts_count`、`reply_count` 等

### 步骤3：修复前端缓存问题
**文件**：`app.js`

**3a. 初始加载添加缓存破坏参数**：
```javascript
// 修改前：
return fetch(DATA_PATH);
// 修改后：
return fetch(DATA_PATH + '?t=' + Date.now());
```

**3b. 移除 `refreshData` 中的 `updated_at` 过早返回**：
```javascript
// 删除这行：
if (data.updated_at && data.updated_at === state.updatedAt) return;
```
改为始终用新数据更新 UI，确保每次刷新都能拿到最新数据。

**3c. 强制刷新时重置 `state.updatedAt`**：
在 `refreshData` 开始时先清空 `state.updatedAt`，确保不会因为时间戳相同而跳过更新。

### 步骤4：添加 HTML meta 标签防止缓存
**文件**：`index.html`

在 `<head>` 中添加：
```html
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
```

### 步骤5：本地运行脚本生成最新数据
- 设置 `FORUM_USERNAME` 环境变量
- 运行 `python scripts/fetch_posts.py` 生成全新的 `posts.json`
- 验证数据是否为最新

### 步骤6：重启预览并验证
- 重启 HTTP 服务器
- 在浏览器中验证数据是否为最新

---

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `data/posts.json` | 删除 | 清除旧数据 |
| `scripts/fetch_posts.py` | 重构 | 简化为全量模式、修复条件判断、清理冗余参数 |
| `app.js` | 修改 | 修复缓存破坏、移除过早返回 |
| `index.html` | 修改 | 添加防缓存 meta 标签 |
