# 验证记录

当前验证只使用 `demoa`、`demob`、`demotv` 虚构目录，不请求真实 115 或 TMDB，不下载视频，不转存或移动文件。

已覆盖：批量分享码解析、NFO/GuessIt 字段、XML 外部实体拒绝、演员与合集关系、电影多版本、ISO/BDMV、电视剧季集、分页检查点、任务租约、目录/文件级健康状态、明确缺失阈值、网络错误不隐藏、管理员来源隔离、匿名建议审核和前端桌面/移动布局。

Python 回归：`.venv\\Scripts\\python.exe -m pytest -q` 当前 34 passed、2 warnings。新增硬化测试覆盖 schema 升级、导入访问码冲突、CSRF 双提交、任务取消传播、暂停恢复收敛、审计脱敏和管理员停用。Ruff 使用 `--no-cache` 检查通过；此前缓存曾包含损坏文件，不能使用旧缓存结果。前端 `npm run build` 和生产依赖 `npm audit --omit=dev` 已通过；Playwright 浏览器二进制未安装，因此本轮不能把浏览器端到端运行标为通过。Docker Compose 配置已通过语法检查；本轮 `docker compose build` 因 Docker Desktop Linux daemon 未运行而未开始构建，不能据此宣称镜像构建成功。

合成性能基准（`.venv\\Scripts\\python.exe scripts/benchmark_index.py --nodes 2000`）在本机临时 SQLite 上创建 2,000 个节点和作品，中文目录搜索命中 1,000 条，查询耗时 56.59 ms，峰值 Python 分配 2.93 MiB。该数据只衡量本地合成查询，不代表真实 115 节点规模或公网性能。

待真实环境验证：115 当前接口字段、真实分页终止、账号认证/限流、源图是否公开、TMDB 鉴权与匹配、PostgreSQL 长时间租约和备份恢复。真实能力未经授权不会启用。
