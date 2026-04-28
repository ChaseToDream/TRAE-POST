# TRAE Forum Posts

展示个人在 [TRAE 官方中文社区](https://forum.trae.cn/) 的帖子，自动排除「Bug反馈」和「产品建议」模块，按分类整理展示。

## 功能

- 从 TRAE 论坛爬取指定用户全部帖子
- 自动排除 Bug反馈、产品建议分类
- 分类导航筛选 + 关键词搜索
- 响应式设计，支持移动端
- GitHub Actions 每日自动更新数据
- 支持 Cloudflare Pages / GitHub Pages 部署

## 项目结构

```
├── index.html                  # 静态网站页面
├── data/posts.json             # 爬取的帖子数据（自动生成）
├── scripts/fetch_posts.py      # 数据爬取脚本
├── requirements.txt            # Python 依赖
└── .github/workflows/update.yml # GitHub Actions 工作流
```

## 部署步骤

### 1. Fork 或创建仓库

将本项目推送到你的 GitHub 仓库。

### 2. 配置 Secret

在仓库 **Settings → Secrets and variables → Actions** 中添加：

| 名称 | 值 | 说明 |
|------|------|------|
| `FORUM_USERNAME` | 你的论坛用户名 | TRAE 论坛的用户名（如 `JasonShane`） |

### 3. 首次运行爬取

本地运行生成初始数据：

```bash
pip install -r requirements.txt
FORUM_USERNAME=你的用户名 python scripts/fetch_posts.py
```

Windows PowerShell：

```powershell
pip install -r requirements.txt
$env:FORUM_USERNAME="你的用户名"
python scripts/fetch_posts.py
```

提交生成的 `data/posts.json` 到仓库。

### 4. 部署到 Cloudflare Pages

1. 登录 [Cloudflare Dashboard](https://dash.cloudflare.com/)
2. 进入 **Workers & Pages → Create application → Pages**
3. 连接 GitHub 仓库
4. 构建设置：
   - 构建命令：留空
   - 输出目录：`/`
   - 根目录：`/`
5. 部署

### 5. 部署到 GitHub Pages

1. 仓库 **Settings → Pages**
2. Source 选择 `Deploy from a branch`
3. Branch 选择 `main`，目录选 `/ (root)`
4. 保存

## 自动更新

GitHub Actions 工作流配置为每日 UTC 02:00（北京时间 10:00）自动运行，也可在 Actions 页面手动触发。

工作流会：
1. 运行 `scripts/fetch_posts.py` 爬取最新数据
2. 如有变化，自动提交到仓库
3. Cloudflare Pages / GitHub Pages 会自动重新部署

## 自定义

- 修改 `scripts/fetch_posts.py` 中的 `EXCLUDED_CATEGORIES` 和 `EXCLUDED_SUBCATEGORIES` 可调整排除的分类
- 修改 `index.html` 中的 CSS 变量可调整主题配色
- 修改 `.github/workflows/update.yml` 中的 cron 表达式可调整更新频率

## 技术说明

- 论坛基于 Discourse 平台，通过 JSON API（URL 后加 `.json`）获取结构化数据
- 用户帖子 API：`/topics/created-by/{username}.json`（支持分页）
- 用户信息 API：`/u/{username}.json`
- 分类信息 API：`/categories.json`
- 爬取间隔 2 秒，避免触发限流

## License

MIT
