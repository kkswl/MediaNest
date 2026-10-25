# 开源方案复用评估

本项目是只读索引站，不把任何开源项目整仓复制进来。下表记录可复用依赖和仅供参考的项目。

| 项目 | 适合借鉴的部分 | 本项目处理方式 | 许可证/注意事项 |
| --- | --- | --- | --- |
| [p115client](https://github.com/ChenyangGao/p115client) | 115 分享码/访问码解析、分享目录分页、只读节点字段 | 作为 Python 依赖；适配器只暴露分享读取与受限 NFO 读取 | MIT；禁止调用转存、移动、下载、播放接口 |
| [OpenList](https://github.com/OpenListTeam/OpenList) | 115 share 的参数、根目录/子目录 ID、失效错误分类 | 只读文档和协议行为参考，不复制驱动代码 | AGPL-3.0；不能静默嵌入本项目 |
| [Media Marshal](https://github.com/media-marshal/media-marshal) | GuessIt/TMDB 识别、低置信度人工确认、媒体版本整理 | 仅参考工作流和字段设计 | 先审查仓库许可证；不复制实现 |
| [kodi-metadata-tmdb-cli](https://github.com/fengqi/kodi-metadata-tmdb-cli) | NFO、TMDB、电影/剧集/BDMV 目录识别 | 仅参考 NFO 字段和匹配流程 | 按其仓库许可证使用；本项目不下载源包海报 |
| [MoviePilot-Wiki](https://github.com/jxxghp/MoviePilot-Wiki) | 电影/电视剧/动漫分类、TMDB 字段、字幕和原盘命名经验 | 仅参考公开文档，不复制 MoviePilot 代码 | 代码和文档许可需分别核对 |
| [Vue Vben Admin](https://github.com/vbenjs/vue-vben-admin) | 后台布局和权限信息架构 | 评估后继续使用现有 Vue + Nuxt UI，不复制 monorepo | MIT，保留其版权声明 |
| [PanSou](https://github.com/fish2018/pansou) | 分享链接状态的 pending/missing 分类思路 | 仅参考状态机；不复制 Go 代码 | MIT，需保留版权和许可证 |

## 明确不纳入

- 未明确授权的 115ShareHub 解析/数据库代码。
- OpenList 的 AGPL 驱动源码。
- 任何包含转存、下载、播放、绕过访问控制或抓取私有凭据的代码。

## 许可证执行

直接依赖的许可证与版本记录在 `THIRD_PARTY_NOTICES.md`；新增依赖必须同步更新该文件，并运行 `scripts/collect_licenses.py`。TMDB 数据和图片不属于开源依赖，必须遵守 TMDB 使用条款和署名要求。
