# Windows 微信聊天记录导出工具 V1.0

把电脑上的微信聊天记录保存成文件，方便自己备份、查找，或交给其他工具整理。

选中要保存的好友或群聊，选好格式和文件夹，就能开始导出。聊天内容保存在自己的电脑上，本工具不会上传聊天记录。

## 能做什么

- 一次选择一个或多个好友、群聊，也可以全选当前列表。
- 按聊天名称、备注或昵称搜索，切换筛选后保留已勾选的聊天。
- 保存为 TXT、Markdown 或 JSON，可以同时选择多种格式。
- 除了文字，还可以一起保存本机仍有缓存的图片和普通文件。
- 导出完成后直接打开文件夹；同名文件自动加序号，避免覆盖已有记录。

目前主要适配 **Windows 10 / 11 64 位、Windows 微信 4.1.15.13**。使用前先登录电脑微信，并保持微信运行。

## 下载和打开

**[点击下载 Windows 核心版 ZIP（推荐）](https://github.com/godorjes/export-wechat/actions/runs/38901670058/artifacts/12046586793)**

下载后解压，双击 **Export-WeChat-V1.exe** 打开程序。不需要安装 Python，也不用输入命令。

下载需要登录 GitHub。其他版本和后续构建可在 [GitHub Actions 下载页面](https://github.com/godorjes/export-wechat/actions/workflows/build-windows.yml) 查看；完整包与核心包的区别见下方开发说明。

## 怎么导出

1. **检测账号**：打开程序后会自动检测，也可以点击右上角的「检测微信账号」或「重新检测」。显示「已识别微信账号」后，就能看到聊天列表。检测中请等待按钮恢复。
2. **选择聊天**：在左侧勾选好友或群聊。可以搜索，也可以切换「全部 / 好友 / 群聊」后全选当前列表。
3. **选择保存格式**：点击右侧「保存格式」下拉框，勾选需要的格式。可以多选，默认只保存 TXT。
4. **选择导出内容**：默认只保存文字，需要时再选择图片或普通文件。
5. **选择保存位置**：点击「选择」挑选文件夹，也可以直接修改输入框里的路径。
6. **开始导出**：点击底部导出按钮。导出时显示「导出中…」，需要停止时点击「取消导出」。完成后点击「打开文件夹」查看结果。

三种格式怎么选：

| 格式 | 适合什么情况 |
| --- | --- |
| TXT（推荐） | 想直接打开看文字、搜索内容，或交给其他工具整理。 |
| Markdown | 想保留排版，用支持 Markdown 的软件阅读。 |
| JSON | 准备用脚本或程序继续处理聊天数据。 |

## 导出的文件在哪里

程序会在你选择的位置下，按当天日期建立一个文件夹，例如 `2026-10-16WeChatExport`。聊天文件直接放在里面，不会再给每个聊天套一层文件夹。

以保存 TXT 为例：

```text
你选择的文件夹/
└─ 2026-10-16WeChatExport/
   ├─ 小林.txt
   ├─ 家人群.txt
   └─ 小林 (2).txt
```

选择多种格式时，会同时生成对应的 `.md`、`.json` 文件；附件保存在对应聊天的 `聊天名_media` 文件夹中。已有同名记录时会加上 `(2)`、`(3)` 等序号，之前导出的文件会保留。

如果直接选择了当天的 `yyyy-MM-ddWeChatExport` 文件夹，记录就保存到这个文件夹中，不再重复建立同名目录。

## 常见问题

**没有识别到账号怎么办？**

先确认电脑微信已经登录，再点「重新检测」。看到本地数据文件夹不代表一定能读取账号；微信版本变化、数据目录变动或文件权限问题都可能导致检测失败。多次检测仍失败时，可以把界面上的提示反馈到 [Issues](https://github.com/godorjes/export-wechat/issues)。

**为什么有些图片或文件没有导出来？**

本工具只能保存这台电脑上仍有缓存的附件。已经清理、删除或从未下载到本机的内容，无法通过本工具找回。

**导出很久没有显示百分比，正常吗？**

目前会显示「导出中…」，不会显示估算百分比。聊天很多、记录很长或勾选了附件时，处理时间会更长。取消后已经完成的聊天文件会保留。

**导出的内容能直接发给别人吗？**

文件中包含真实聊天内容，请先检查再分享。反馈问题时也不要上传聊天数据库、密钥或完整的私人聊天记录。

---

## 开发说明

下面是源码运行、命令行和打包说明。只使用 EXE 的用户可以跳过。

### 环境与源码运行

推荐 Python 3.12。主界面使用 Tkinter / ttk，不需要额外的浏览器或前端运行环境。

```powershell
python -m pip install -r requirements-core.txt
python app.py
```

当前主界面提供聊天选择、格式多选、文字及图片/普通文件导出。历史界面与旧命令行保留原有的语音、视频、本地语音转文字等入口；需要这些功能时安装完整依赖：

```powershell
python -m pip install -r requirements.txt
python app.py --legacy
```

主界面及窗口图标共用 `assets/app.png`；EXE 的 Windows 图标使用 `assets/app.ico`。构建时会将 assets 一并打包。

### 命令行

先列出可读取聊天的稳定 `username`，再选择需要导出的账号 ID：

```powershell
python cli.py --list-chats --db-dir "D:\微信数据\xwechat_files\wxid_xxx"
python cli.py --username wxid_a --username wxid_b --format txt --format json --images --files --out "D:\聊天导出"
python cli.py --all --format md --out "D:\聊天导出"
```

`--username` 和 `--format` 可以重复传入。按 username 选择及 `--all --format` 使用与新界面相同的平铺日期目录；可按 Ctrl+C 请求协作取消。

原昵称入口及不带 `--format` 的 `--all / --limit` 入口保留历史行为，包括原来的会话子目录和批量索引。`--limit` 不适用于新的按格式选择入口：

```powershell
python cli.py "好友备注名或群名" --db-dir "D:\微信数据"
python cli.py --all --limit 20
```

### 数据读取与临时缓存

- 聊天选择使用稳定 `username`，不依赖显示名区分同名联系人；仅导出能可靠对应到本地消息表的会话。
- 底层依赖精确锁定为 `wechatauto-replica==1.2.4.4`。发送者按消息来源分片解析，不用昵称或数字 ID 猜测「我」；无法确认的发送者保留不确定状态。
- 每次数据库会话使用隔离的 `%TEMP%\wechat-chat-export-sensitive\run-*` 工作目录；数据库密钥副本、图片密钥和解密数据库缓存重定向到该目录，结束后尝试清理。
- 启动和新导出前会检查本项目自己的失效缓存：活动进程的目录跳过，无标记旧目录超过 24 小时后才自动清理。
- 强制结束进程、断电或文件占用仍可能留下敏感临时文件。显式清理命令如下；它也会尝试清理可能被其他工具共用的旧 `%TEMP%\wechatauto_db`，执行前请关闭这些工具：

```powershell
python cli.py --clear-sensitive-cache
```

正常导出只读取原始微信数据库，结果写入用户选择的目录；缓存清理不删除原始数据库或已完成的导出文件。

### 语音与媒体

核心包和完整包都包含 FFmpeg 与固定版本的 rust-silk 解码器。核心包不包含可选的 ASR 运行时；完整包保留 sherpa-onnx / soundfile 等语音识别依赖，供旧界面或命令行使用。

完整环境下可按需安装解码器和本地语音模型：

```powershell
python cli.py --install-rust-silk
python cli.py --install-asr
python cli.py "好友备注名或群名" --transcribe-voices
```

SenseVoice 模型不会打进 EXE，首次安装会下载并校验。识别在本机完成，默认模型目录为 `%LOCALAPPDATA%\WeChat-Chat-Export-for-LLM\models\sensevoice`，转写缓存位于同一应用目录的 `cache\voice_asr_cache.json`。

媒体只使用能可靠匹配的本地缓存；视频号等特殊消息的限制、JSON 扩展字段和历史行为见 [原版技术说明](docs/UPSTREAM_V1_4_0.md)。

### 测试与 Windows 构建

```powershell
python -m unittest discover -s tests -p "test_*.py"
python -m pip install -r requirements.txt -r requirements-build.txt
python scripts/build_windows.py --profile core --layout onefile
python scripts/build_windows.py --profile full --layout onefile
python scripts/build_windows.py --profile core --layout onedir --distdir dist/onedir
```

GitHub Actions 会运行依赖契约检查、语法检查和完整单元测试，通过后构建核心/完整 Windows 单文件包并上传产物。构建脚本校验固定 rust-silk v0.1.3 的 SHA-256，打包许可证及说明文档，并记录实际体积、构建耗时和 EXE 摘要。

Dependabot 负责检查依赖更新；升级仍需经过 Windows CI 和人工审核，不自动合并或发布。

合成 SQLite 和界面测试不等于真实微信验收。相关开发记录：

- [运行与验收](docs/ACCEPTANCE.md)
- [界面与导出结构说明](docs/UI_ACCOUNT_FOLDED.md)
- [代码审查](docs/CODE_AUDIT.md)
- [交付报告](docs/DELIVERY.md)

## 项目来源与致谢

本项目基于 [zhuzhangxue/wechat-chat-export v1.4.0](https://github.com/zhuzhangxue/wechat-chat-export) 进行增量二次开发，沿用原数据库读取、分片发送者解析和媒体导出引擎，并针对当前桌面界面、聊天选择及导出方式进行调整。

感谢原项目及其贡献者，也感谢 [fanyuantaier/wechatauto-replica](https://github.com/fanyuantaier/wechatauto-replica) 提供底层读取和媒体处理能力。原版说明及贡献记录保留在 [原版 v1.4.0 文档](docs/UPSTREAM_V1_4_0.md)，第三方组件和许可证见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 许可证与声明

采用 [Apache License 2.0](LICENSE)，保留原项目及第三方声明。

本项目与腾讯、微信及其关联公司没有隶属、授权或合作关系。请只处理自己有权访问的数据；微信版本、系统环境或依赖变化可能导致部分功能失效或导出不完整。不需要为运行本工具关闭系统安全保护。
