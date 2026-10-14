# V1.0 代码审查与实施范围

上游：zhuzhangxue/wechat-chat-export，基线提交 `2c49469a91e2f3b0c73a581e15a8ad2db25b7923`（v1.4.0）。本仓库是增量二次开发，保留上游 Git 历史与 Apache-2.0 许可证。

## 直接复用

- `_batch_chat_candidates()` 从 contact/session 元数据和 sqlite_master 的消息表名反查 username，不读取消息正文，不猜测未知表归属。
- `_export_chat_impl()`、`load_rows()` 和分片 Name2Id 发送者解析；保留图片、普通文件、语音、视频解析代码。
- `_stable_batch_folder()` 的 username + SHA256 稳定目录；账号级索引缓存。
- `_upstream_sensitive_sandbox()`、一次性 workdir、异常清理与残留所有权检查。
- `wechat_data_dirs.py` 的配置、注册表、浅层目录发现和原生 ttk 预览。
- 原 `export_chat()`、`export_all_chats()` 和 CLI；原 GUI 保留为 `--legacy`。

## 新增和修改

- `chat_list_service.py`：列表加载、搜索/分类、username 选择集合与元数据缓存。
- `export_task_service.py`：明确选项、协作取消、共享上下文、独立任务目录、结构化进度、隔离失败和任务汇总。
- `ui/chat_list.py`、`ui/main_window.py`：双栏列表界面，后台线程/queue/after，数据源候选选择，任务锁和关闭清理。
- `exporter_core.py`：枚举结果增加昵称/备注；单会话接口支持格式集合和取消点，默认行为保持三种格式。
- `preview.py`：固定大小分页、释放旧页控件和图像；兼容仅 TXT/Markdown 的预览，不强制生成 JSON。
- `cli.py`：增加 `--list-chats`、可重复 `--username` 和 `--format`。
- `scripts/build_windows.py` 和 Windows CI：原版基线、核心与完整构建、测试和许可证打包。

## 主要回归风险与验证

1. 分片发送者/群归属：原测试 + 合成 SQLite 端到端导出。
2. 取消时残留半成品：每个会话先写临时目录，完成后提交；取消/失败清理，已成功会话保留。
3. 重名与重复导出：username 稳定目录置于独立任务根，避免覆盖此前任务。
4. 单格式与预览：只生成所选格式；TXT/Markdown 使用分页文本预览，JSON 使用原聊天视图。
5. 轻量化：数据库/图片依赖保留，ASR 与视频转码仅作为显式完整包；先测原构建再比较。真实微信数据不进入测试、日志或 Git。

目标 Windows 10/11、微信 4.1.15.13。自动化测试不等同于真实账号验收；没有读取用户真实聊天的授权或夹具，本次使用合成数据验证。
