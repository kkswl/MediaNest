# 开源复用与第三方声明

本文件区分依赖调用和设计参考。MIT 不等于可删除版权；LGPL 依赖不得被无许可证地复制重写；未明确授权的代码不纳入本项目。

## 实际依赖

| 项目 | 用途／代码路径 | 许可证 | 集成方式 |
| --- | --- | --- | --- |
| [p115client](https://github.com/ChenyangGao/p115client) `0.0.9.7.2` | `p115client/client.py` 的分享只读列表与小 NFO 地址；参考 `p115client/fs/fs_share.py` | [MIT](https://github.com/ChenyangGao/p115client/blob/main/LICENSE) | Python 发布包依赖；项目只读适配器不调用转存／移动等写 API |
| [GuessIt](https://github.com/guessit-io/guessit) 3.x | 文件名识别 | [LGPLv3](https://github.com/guessit-io/guessit/blob/develop/LICENSE) | 独立未修改 Python 依赖，保留发布包许可与源码获取链接 |
| [Nuxt UI](https://github.com/nuxt/ui) 4.12.0 | Vue 组件、Vite 插件 | MIT，已核对 `node_modules/@nuxt/ui/LICENSE` | npm 依赖，不复制源码 |
| [Vue](https://github.com/vuejs/core) 3.x | 响应式界面 | MIT | npm 依赖 |
| [FastAPI](https://github.com/fastapi/fastapi) | HTTP API | MIT | Python 依赖 |
| [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy) | ORM 与数据库 | MIT | Python 依赖 |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI 服务器 | BSD-3-Clause | Python 依赖 |
| [HTTPX](https://github.com/encode/httpx) | 受限服务端 HTTP | BSD-3-Clause | Python 依赖 |
| [cryptography](https://github.com/pyca/cryptography) | 私有凭据加密 | Apache-2.0 OR BSD-3-Clause | Python 依赖 |
| [defusedxml](https://github.com/tiran/defusedxml) | 安全 NFO XML 解析 | PSF-2.0 | Python 依赖 |
| [Psycopg](https://github.com/psycopg/psycopg) | 可选 PostgreSQL 驱动 | LGPL-3.0 | Python 依赖 |

准确解析版本以 `frontend/package-lock.json` 和 Python 锁定文件为准，不以本表的主版本替代锁文件。传递依赖也必须保留其包内声明。

## 已评估但未复制源码

- [Vue Vben Admin](https://github.com/vbenjs/vue-vben-admin)：MIT；评估后台能力后，因完整 monorepo 与 Nuxt UI 技术体系重叠，本项目未直接引入。版权 2024-present Vben。
- [PanSou](https://github.com/fish2018/pansou)：MIT；`service/check_service.go` 的 `check115`、缓存和状态分类作为设计参考，未复制 Go 代码。其根分享检测不证明文件仍存在。
- [115ShareHub](https://github.com/a55ure/115ShareHub)：未确认明确复用许可，仅参考需求与行为，不复制 `parser.rs` 或数据库代码。
- [OpenList](https://github.com/OpenListTeam/OpenList)：AGPL-3.0；没有复制其 115 分享驱动，也没有将其打包进应用。
- [FastAPI 全栈模板](https://github.com/fastapi/full-stack-fastapi-template)：MIT；曾评估 React 技术路线，当前采用 Vue/Nuxt UI，不声称套用其模板代码。

## 分发注意

本文件不是各许可证全文的替代品。随安装包保留的 LICENSE/COPYING/NOTICE 均应随发行物保留。`scripts/collect_licenses.py` 从实际 Python 环境和 npm 安装树收集声明及全文，输出 `licenses/installed-manifest.json`、`licenses/THIRD_PARTY_LICENSES.txt` 和缺失清单。范围包括开发工具，不宣称每个包都被打入浏览器。对平台原生包，只有与主包版本一致时复用主包许可；部分发布包缺少许可文件时，补充上游官方许可并记录原网址，未提供精确版本 tag 的网址不得视为精确源码对应证明。

默认收集命令不联网；只有显式 `--fetch-supplemental` 才访问脚本内固定的官方许可证地址，不访问应用资源。发布前应在最终依赖环境重新生成，审核 `MISSING_NOTICE_TEXTS.txt`，检查实际锁文件与清单一致，不可将许可证字段或自动收集视为完整法律审查。Docker 保留本声明和已收集全文，Python 发布包自带许可保留在安装位置。

TMDB 内容不是开源软件许可的一部分；使用其 API／图像需遵守 [TMDB 使用条款与署名要求](https://developer.themoviedb.org/docs/faq)。本站不宣称获得 TMDB 或 115 的认可。

## 已核对的前端 MIT 许可

以下版权行分别对应各自依赖，许可正文同下。构建产物也应包含依赖声明，不能只在源码树保留。

- Nuxt UI: Copyright (c) 2023 Nuxt
- Vue: Copyright (c) 2018-present, Yuxi (Evan) You

```text
MIT License

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.
```
