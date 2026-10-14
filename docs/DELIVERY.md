# V1.0 开发与交付报告

日期：2026-10-14（Asia/Shanghai）。目标仓库：https://github.com/godorjes/export-wechat 。

## 结果

已基于上游 v1.4.0、提交 2c49469a91e2f3b0c73a581e15a8ad2db25b7923 增量开发。底层 wechatauto-replica 精确锁定 1.2.4.4，保留上游 Git 历史、LICENSE 和第三方声明。未新增数据库解密、注入、密钥提取或聊天上传功能。

完成自动发现/手选数据源、实际账号固定、可靠 username 列表、好友/群分类、备注/昵称搜索、多选和跨筛选保留选择、刷新去重、选择性和全部批量导出、格式/媒体选项、后台进度、协作取消、失败汇总及原生预览。每个任务有独立输出目录，每个会话按 username 稳定命名，取消/失败清理暂存且保留已成功结果。

## 文件清单

修改：app.py、cli.py、exporter_core.py、preview.py、.github/workflows/build-windows.yml、.gitignore、README.md、THIRD_PARTY_NOTICES.md。
新增：chat_list_service.py、export_task_service.py、ui/__init__.py、ui/chat_list.py、ui/main_window.py、requirements-core.txt、requirements-build.txt、scripts/build_windows.py、tests/test_chat_list.py、tests/test_selected_export.py、tests/test_gui.py、tests/test_cli.py、docs/V1_TASK.md、docs/CODE_AUDIT.md、docs/ACCEPTANCE.md、本报告和 docs/superpowers/plans/2026-10-14-v1.md。

## 复用与关键决定

1. 列表复用 _batch_chat_candidates 和 sqlite_master 元数据，不解析消息正文。未知身份统计并跳过。扩展昵称/备注用于搜索。
2. 批量复用 _export_chat_impl、分片 Name2Id、图片/文件处理及账号缓存，一次任务一个 DB 上下文。格式接口默认仍写三种，旧入口兼容。
3. 每次任务使用独立根目录；先写 .partial，完成才提交会话目录。INCOMPLETE.txt 只有在汇总和清理完成后删除。磁盘写失败仍返回成功路径和脱敏错误。
4. 目录加载后固定实际 account_dir，拒绝显式账号被依赖切换，防止多账号漂移。
5. 原 GUI 保留 --legacy，源代码和旧 CLI 媒体能力保留；V1 默认 GUI 只提供图片和普通文件。
6. JSON 固定每页最多 100 条，释放旧页控件/图像；仅 TXT/MD 使用流式分页文本预览，避免隐式写 JSON。JSON 文件数据仍一次解析到内存，极大 JSON 的首次读取成本仍存在。

## 测试和审查

- 未修改原版：52 项 unittest 通过。
- 最终源码：79 项 unittest 通过；命令 python -m unittest discover -s tests -p test_*.py。
- 合成 SQLite 验证：有记录会话识别、重名、未知表、不读正文的列表查询、单/多格式、跨分片发送者、原全部导出、失败继续、取消、源文件字节保持不变和敏感沙箱恢复。
- 合成图片/普通文件经过实际缓存索引和复制路径，复制内容与源一致；加密图片使用原回归夹具，真实 V2 图片待用户验收。
- 实际 Tk 控件验证：选择跨筛选/刷新保留、线程回调在主线程、重复任务保护、完整选会话到 SQLite 导出流程、最小 980×640 窗口按钮无重叠、固定分页及文件句柄关闭。
- GitHub Actions 首次运行暴露英文 Windows 重定向编码差异；新增模拟 ASCII 输出回归，CLI 明确使用 UTF-8。本地 79 项已通过，远端重跑中。此修复只涉及独立 CLI，GUI EXE 未包含该入口，二进制不变。
- 独立源码审查发现三项 Important，均以失败测试复现并修复：锁定依赖 get_self_info 的连接泄漏、汇总失败丢失结果/未完成标记、初次连接后的取消遗漏。无延后 Minor。
- 连接修复仅在调用原身份方法时跟踪并明确关闭其打开的连接，保留原身份语义；不靠 GC 清理敏感 SQLite。

## Windows 构建结果

本地 Windows 10 10.0.19044、Python 3.12.14、PyInstaller 6.22.3。三种最终构建均成功。

| 版本 | 未压缩 EXE/目录体积 | 本地记录耗时 |
| --- | ---: | ---: |
| 原版 v1.4.0 onefile | 134.63 MiB | 52.16 s |
| V1 核心 onefile | 123.62 MiB | 49.58 s |
| V1 完整 onefile | 134.66 MiB | 53.48 s |
| V1 核心 onedir | 333.05 MiB | 34.02 s |

核心单文件相对原版减少 8.18%，没有移除数据库/图片/附件的依赖。FFmpeg 是 WXGF 图片转换路径所需，因此保留；只排除可选 ASR 的 sherpa-onnx/soundfile。rust-silk 固定官方归档并校验 SHA256。
原版耗时只计 PyInstaller，新版含 ZIP 打包，以上只作构建记录，不据此声称构建加速。

核心 EXE SHA256：d720ed2135f7410a16c0cc9531d9530954df5bdc17679dc2cd3a692b494de31d
完整 EXE SHA256：cb85d0394d3969e205e00c9d45c7501e1d558731a892254f49820e34b4907f95

最终核心 EXE 已启动并发现标题为“微信聊天记录导出 V1.0”的原生窗口，辅助功能树读取成功；正常关闭通过 Alt+F4 发起。桌面截图失败（FrameArrived/window capture timeout），实际控件几何由 Tk 测试验证。
未得到可靠冷启动对照：工具首次启动耗时异常，原版启动对照遇到 app approval timeout；核心第二次窗口出现约 2.91 s，含工具开销且系统缓存未重置，不能当作严格性能结果。空闲内存和真实账号联系人扫描速度未测量。

正式产物：Export-WeChat-V1.exe / Export-WeChat-V1-onefile-Windows.zip。
可选完整包：Export-WeChat-V1-Full-onefile-Windows.zip。
可选目录包：Export-WeChat-V1-onedir-Windows.zip，需完整解压。
源码：export-wechat-v1-source.zip。
以上产物位于本次聊天的 outputs 目录，二进制和真实用户数据不提交到 Git。GitHub Actions 会在 main 推送后构建 core/full artifact；其在线状态独立于本地构建结果。

## 未完成/待真实环境验收

- Windows 10 + 微信 4.1.15.13 的真实联系人完整性、跨分片发送者/群归属及图片文件兼容性，尚未作准确性验收。
- Windows 11 和完全未安装 Python 的独立机器尚未实测；产物包含 Python/Tcl 运行时。
- 真正冷启动、空闲内存、真实大账号列表性能未得可靠测量。
- 底层首次连接/解密和单个大文件复制不强行中断；取消等待其返回检查点。
- 仅 TXT/MD 的预览是原生分页文本，附件可从导出目录查看；大 JSON 首次解析内存仍与记录规模相关。
- 强制杀进程、断电、文件占用可留敏感残余；继承原所有权检查和下次清理机制。
- V2 交易/红包/统计/Excel/PDF/AI/云同步均未新增。

请按 docs/ACCEPTANCE.md 的真实账号清单验收。待 V1 稳定后，再将交易解析、视频增强和统计作为独立可选模块评估。
