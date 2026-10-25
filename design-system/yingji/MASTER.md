# 映集设计系统

先使用 ui-ux-pro-max 做 design-system 检索，再查询 nuxt-ui 栈。检索的营销 Hero/CTA 不适合影视目录，采用其通用可访问性和少动效规则，手工调整为内容优先。

- 前台：墨蓝 #090e18，面板 #111b2b，主文字 #eef3fa，次文字 #a8b5c8，强调薄荷 #65dfbd。后台复用 token，信息密度更高。
- 中文系统字体 PingFang SC / Microsoft YaHei / sans-serif；无需在线字体。正文 16px，辅助 13px，标题 clamp(28px,4vw,52px)。
- 4/8px 间距，12px 圆角，海报 2:3 固定比例；移动 2 列，平板 3-4 列，桌面 5-6 列。网格无需大面积背景素材。
- 顶部品牌/发现/演员/合集/后台；手机折行不隐藏关键入口。后台导航横向可滚动，数据表独立滚动。
- Nuxt UI UButton/UInput/USelect/UTextarea/UBadge/UAlert/UTabs 等可用部件，Lucide 图标统一。不引入第二套 UI。
- 文字对比至少4.5:1，键盘焦点可见，触控目标44px；有 label、错误文本、状态 live region，不仅颜色。
- 微动效150–200ms，仅颜色/透明度，支持 prefers-reduced-motion；无滚动劫持或自动轮播。
- 完整 loading/empty/error/paused/pending/recheck/default-poster 状态。复制有反馈，管理员凭据不预填显示。
- 模拟海报为本项目 CSS/SVG 抽象图形，不冒充真实作品海报；不下载第三方图片。
