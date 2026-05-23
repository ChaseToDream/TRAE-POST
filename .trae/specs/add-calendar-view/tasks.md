# Tasks

- [ ] Task 1: 在 index.html 工具栏中添加日历视图按钮
  - [ ] SubTask 1.1: 在 view-toggle 区域添加第三个视图按钮（日历图标），id 为 `view-calendar`
  - [ ] SubTask 1.2: 在快捷键提示区域添加 `<kbd>3</kbd>` 日历视图提示
- [ ] Task 2: 在 app.js 中添加日历视图核心逻辑
  - [ ] SubTask 2.1: 在 ICONS 常量中添加日历图标 SVG
  - [ ] SubTask 2.2: 在 state 对象中添加 `calendarMonth` 和 `calendarYear` 状态字段
  - [ ] SubTask 2.3: 实现 `renderCalendarView(filtered)` 函数，渲染月历网格和帖子分布指示
  - [ ] SubTask 2.4: 实现月份导航（前/后月切换）功能
  - [ ] SubTask 2.5: 实现点击日期格子展开/收起当日帖子列表
  - [ ] SubTask 2.6: 在 `renderPosts()` 中添加日历视图分支
  - [ ] SubTask 2.7: 更新视图切换事件绑定，支持日历视图按钮
  - [ ] SubTask 2.8: 更新键盘快捷键，`3` 键切换日历视图
  - [ ] SubTask 2.9: 更新 URL 状态同步（`view=calendar`）
  - [ ] SubTask 2.10: 更新 localStorage 偏好保存，支持日历视图状态
- [ ] Task 3: 在 styles.css 中添加日历视图样式
  - [ ] SubTask 3.1: 添加日历容器、月份导航、星期标题行样式
  - [ ] SubTask 3.2: 添加日历格子样式（含帖子指示圆点、hover 效果、今日高亮）
  - [ ] SubTask 3.3: 添加日期展开帖子列表样式
  - [ ] SubTask 3.4: 添加深色主题适配样式
  - [ ] SubTask 3.5: 添加响应式布局样式（移动端适配）
  - [ ] SubTask 3.6: 添加日历视图入场动画

# Task Dependencies
- Task 2 depends on Task 1（需要 HTML 中的按钮元素）
- Task 3 depends on Task 2（需要 JS 渲染的 DOM 结构来确定样式类名）
- Task 1 和 Task 3 可并行准备（HTML 结构和 CSS 类名预先约定）
