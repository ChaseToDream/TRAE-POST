# 修复帖子标题和数据不同步问题

## 问题分析

项目存在两个核心同步问题：

### 问题1：帖子标题不会实时同步
- **根因**：`fetch_posts.py` 的 `fetch_user_topics` 函数接收 `existing_ids` 参数，跳过已存在的帖子 ID（第261-264行）
- **结果**：如果论坛上的帖子标题被修改，由于该帖子 ID 已在 `existing_ids` 中，重新抓取时会被跳过，标题永远不会更新

### 问题2：浏览量等数据不会实时同步
- **根因**：同上，`merge_posts` 函数（第413-429行）只添加新帖子，不会更新已有帖子的 `views`、`like_count`、`reply_count` 等可变字段
- **结果**：帖子的浏览量、点赞数、回复数等永远停留在首次抓取时的值

### 问题3：前端无刷新机制
- **根因**：`app.js` 在页面加载时只 fetch 一次 `data/posts.json`（第865-884行），之后没有任何刷新逻辑
- **结果**：用户长时间保持页面打开时，看不到最新数据

---

## 修复方案

### 步骤1：修改 `fetch_posts.py` — 让 `fetch_user_topics` 不再跳过已有帖子

**文件**：`scripts/fetch_posts.py`

**修改内容**：
- 修改 `main()` 函数，不再将 `existing_ids` 传递给 `fetch_user_topics`
- 改为传 `None` 或空集合，使函数抓取所有帖子（包括已存在的），从而获取最新的标题和统计数据
- 保留 `seen_ids` 的页内去重逻辑（防止同一批次内重复），但不再跨批次去重

**具体改动**：
```python
# 修改前（第546行）：
raw_topics = await fetch_user_topics(client, username, existing_ids)

# 修改后：
raw_topics = await fetch_user_topics(client, username)
```

### 步骤2：修改 `merge_posts` 函数 — 用新数据更新已有帖子

**文件**：`scripts/fetch_posts.py`

**修改内容**：
- 当前 `merge_posts` 对已有帖子只保留旧数据（第423-425行），需要改为用新抓取的数据覆盖旧数据
- 新数据应优先，因为包含最新的标题、浏览量、点赞数等
- 保留旧数据中可能存在的额外字段（如新 API 不再返回的字段）

**具体改动**：
```python
# 修改前（第413-429行）：
def merge_posts(existing: dict, new_posts: list[PostItem]) -> list[PostItem]:
    if not existing:
        return new_posts
    old_posts = {p["id"]: p for p in existing.get("posts", []) if p.get("id")}
    merged: dict[int, dict] = {}
    for post in new_posts:
        merged[post.id] = post.model_dump()
    for pid, post in old_posts.items():
        if pid not in merged:
            merged[pid] = post
    result = [PostItem(**p) for p in merged.values()]
    result.sort(key=lambda x: x.created_at, reverse=True)
    return result

# 修改后：
def merge_posts(existing: dict, new_posts: list[PostItem]) -> list[PostItem]:
    if not existing:
        return new_posts
    old_posts = {p["id"]: p for p in existing.get("posts", []) if p.get("id")}
    merged: dict[int, dict] = {}
    for post in new_posts:
        merged[post.id] = post.model_dump()
    for pid, post in old_posts.items():
        if pid not in merged:
            merged[pid] = post
    result = [PostItem(**p) for p in merged.values()]
    result.sort(key=lambda x: x.created_at, reverse=True)
    return result
```

> 注：`merge_posts` 的逻辑本身已经是"新数据优先"（新帖子覆盖旧帖子），但由于步骤1的修改，现在所有帖子都会出现在 `new_posts` 中，因此已有帖子的数据也会被新数据覆盖。

### 步骤3：添加已有帖子详情刷新机制

**文件**：`scripts/fetch_posts.py`

**修改内容**：
- 新增 `fetch_topic_details` 异步函数，通过 `/t/{id}.json` API 获取单个帖子的最新详情
- 新增 `refresh_existing_posts` 异步函数，并发刷新所有已有帖子的详情数据
- 在 `main()` 流程中，在获取新帖子后，额外刷新已有帖子的可变字段（views, like_count, reply_count, title, excerpt 等）
- 这样即使帖子列表 API 返回的数据不完整，也能通过详情 API 获取最新数据

**具体改动**：
```python
async def fetch_topic_details(client: ForumClient, topic_id: int) -> Optional[dict]:
    data = await client.fetch_json(f"{FORUM_BASE}/t/{topic_id}.json")
    if not data:
        return None
    return {
        "id": data.get("id", topic_id),
        "title": data.get("title", ""),
        "views": data.get("views", 0),
        "like_count": data.get("like_count", 0),
        "reply_count": data.get("reply_count", 0),
        "posts_count": data.get("posts_count", 0),
        "last_posted_at": data.get("last_posted_at", ""),
        "excerpt": data.get("excerpt", ""),
        "pinned": data.get("pinned", False),
        "closed": data.get("closed", False),
        "archived": data.get("archived", False),
    }

async def refresh_existing_posts(client: ForumClient, existing_ids: set[int]) -> dict[int, dict]:
    if not existing_ids:
        return {}
    log.info("开始刷新 %d 条已有帖子的详情...", len(existing_ids))
    tasks = [fetch_topic_details(client, tid) for tid in existing_ids]
    results = {}
    with tqdm(total=len(tasks), desc="刷新帖子详情") as pbar:
        for coro in asyncio.as_completed(tasks):
            detail = await coro
            if detail and detail.get("id"):
                results[detail["id"]] = detail
            pbar.update(1)
    log.info("成功刷新 %d/%d 条帖子详情", len(results), len(existing_ids))
    return results
```

- 新增 `apply_refresh_data` 函数，将刷新后的数据合并到帖子列表中：

```python
def apply_refresh_data(posts: list[PostItem], refresh_data: dict[int, dict]) -> list[PostItem]:
    if not refresh_data:
        return posts
    post_map = {p.id: p for p in posts}
    for pid, detail in refresh_data.items():
        if pid in post_map:
            p = post_map[pid]
            if detail.get("title"):
                p.title = detail["title"]
            if detail.get("views") is not None:
                p.views = detail["views"]
            if detail.get("like_count") is not None:
                p.like_count = detail["like_count"]
            if detail.get("reply_count") is not None:
                p.reply_count = detail["reply_count"]
            if detail.get("posts_count") is not None:
                p.posts_count = detail["posts_count"]
            if detail.get("last_posted_at"):
                p.last_posted_at = detail["last_posted_at"]
            if detail.get("excerpt"):
                p.excerpt = detail["excerpt"]
            if detail.get("pinned") is not None:
                p.pinned = detail["pinned"]
            if detail.get("closed") is not None:
                p.closed = detail["closed"]
            if detail.get("archived") is not None:
                p.archived = detail["archived"]
    return posts
```

- 在 `main()` 中调用刷新逻辑：

```python
# 在获取帖子后、合并前，刷新已有帖子详情
if existing_ids:
    refresh_data = await refresh_existing_posts(client, existing_ids)
    all_filtered = apply_refresh_data(all_filtered, refresh_data)
```

### 步骤4：前端添加自动刷新和手动刷新功能

**文件**：`app.js`

**修改内容**：

1. **添加自动定时刷新**：每隔 5 分钟自动重新 fetch `data/posts.json`，如果数据有变化则更新 UI
2. **添加手动刷新按钮**：在工具栏中添加刷新按钮，点击立即刷新数据
3. **添加刷新状态指示器**：显示数据刷新中的状态，以及上次刷新时间
4. **智能刷新**：只在页面可见时刷新（使用 `visibilitychange` 事件），避免后台浪费资源

**具体改动**：

- 在 `state` 对象中添加刷新相关状态：
```javascript
refreshTimer: null,
isRefreshing: false,
REFRESH_INTERVAL: 5 * 60 * 1000, // 5分钟
```

- 新增 `refreshData` 函数：
```javascript
function refreshData() {
    if (state.isRefreshing) return;
    state.isRefreshing = true;
    fetch(DATA_PATH + '?t=' + Date.now())
        .then(function(r) { if (!r.ok) throw new Error('HTTP ' + r.status); return r.json(); })
        .then(function(data) {
            if (!data || !data.posts) return;
            state.allPosts = data.posts || [];
            state.categories = data.categories || {};
            if (data.updated_at) {
                state.updatedAt = data.updated_at;
                document.getElementById('update-time').textContent = '最后更新: ' + fmtDate(data.updated_at);
            }
            renderHeader(data);
            updateCatTabs();
            renderPosts();
        })
        .catch(function(e) { console.warn('自动刷新失败:', e); })
        .finally(function() { state.isRefreshing = false; });
}
```

- 新增 `startAutoRefresh` 和 `stopAutoRefresh` 函数：
```javascript
function startAutoRefresh() {
    stopAutoRefresh();
    state.refreshTimer = setInterval(refreshData, state.REFRESH_INTERVAL);
}

function stopAutoRefresh() {
    if (state.refreshTimer) {
        clearInterval(state.refreshTimer);
        state.refreshTimer = null;
    }
}
```

- 在 `init` 函数中启动自动刷新，并监听页面可见性：
```javascript
startAutoRefresh();
document.addEventListener('visibilitychange', function() {
    if (document.hidden) {
        stopAutoRefresh();
    } else {
        refreshData();
        startAutoRefresh();
    }
});
```

- 在 `index.html` 工具栏中添加刷新按钮

### 步骤5：提高 GitHub Actions 更新频率

**文件**：`.github/workflows/update.yml`

**修改内容**：
- 将 cron 从每4小时改为每2小时：`'0 */2 * * *'`
- 这样后端数据更新更频繁，前端刷新时能获取到更新的数据

---

## 修改文件清单

| 文件 | 修改类型 | 说明 |
|------|----------|------|
| `scripts/fetch_posts.py` | 修改 | 不再跳过已有帖子、新增帖子详情刷新机制 |
| `app.js` | 修改 | 添加自动刷新、手动刷新、刷新状态指示 |
| `index.html` | 修改 | 添加刷新按钮 UI |
| `.github/workflows/update.yml` | 修改 | 提高更新频率 |

---

## 风险评估

1. **API 请求量增加**：步骤3的详情刷新会对每个已有帖子发一次 API 请求。对于71条帖子，并发数为5，约需15次并发批次。需确保不触发论坛 API 限流。
   - **缓解措施**：保持 `CONCURRENCY = 5` 和 `REQUEST_DELAY = 1.0`，并在请求失败时自动退避

2. **前端刷新闪烁**：自动刷新时如果直接替换 DOM 可能导致闪烁。
   - **缓解措施**：对比 `updated_at` 字段，只有数据确实更新时才重新渲染

3. **GitHub Actions 运行时间增加**：由于需要刷新所有帖子详情，运行时间会增加。
   - **缓解措施**：`timeout-minutes: 10` 已有足够余量
