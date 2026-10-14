# -*- coding: utf-8 -*-
import argparse
import json
import signal
import sys

from exporter_core import (
    clear_sensitive_cache,
    export_all_chats,
    export_chat,
    install_local_asr_model,
    install_rust_silk,
)


if __name__ == "__main__":
    # Redirected streams on English Windows may default to a legacy code page.
    # JSON and Chinese diagnostics use the same explicit UTF-8 contract.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8', errors='replace')
    p = argparse.ArgumentParser(description="微信聊天信息导出给大模型")
    p.add_argument("name", nargs="?", help="好友备注/昵称或群名")
    p.add_argument("--out", default="exports")
    p.add_argument(
        "--images",
        action="store_true",
        help="同时导出本机仍有缓存的聊天图片",
    )
    p.add_argument(
        "--files",
        action="store_true",
        help="同时导出本机仍有缓存的聊天文件",
    )
    p.add_argument("--voices", action="store_true", help="同时导出语音；有解码器时生成 WAV")
    p.add_argument("--videos", action="store_true", help="同时导出本机仍有缓存的视频")
    p.add_argument(
        "--transcribe-voices",
        action="store_true",
        help="用本地 SenseVoice 将导出的语音转成文字；会自动开启语音导出",
    )
    p.add_argument(
        "--media",
        action="store_true",
        help="同时开启图片、文件、语音和视频导出",
    )
    p.add_argument(
        "--all",
        dest="export_all",
        action="store_true",
        help=(
            "导出本机所有能够从本地消息表可靠识别的私聊和群聊，"
            "并生成 all_chats_index.json / all_chats_index.md 总索引"
        ),
    )
    p.add_argument(
        "--limit",
        type=int,
        default=None,
        help="配合 --all 使用：只导出最近的 N 个会话，便于先小范围试跑",
    )
    p.add_argument(
        "--install-asr",
        action="store_true",
        help="下载安装本地 SenseVoice 语音识别模型后退出",
    )
    p.add_argument(
        "--install-rust-silk",
        action="store_true",
        help="下载安装 rust-silk 语音解码器后退出",
    )
    p.add_argument(
        "--clear-sensitive-cache",
        action="store_true",
        help=(
            "清除当前版本临时敏感缓存，以及 v1.3.3 及更早版本 / "
            "wechatauto-replica 默认留下的密钥和解密数据库缓存后退出"
        ),
    )
    p.add_argument(
        "--db-dir",
        default=None,
        help=(
            "微信数据目录（微信「设置 → 文件管理」里显示的那个）。"
            "默认自动探测；数据目录被自行迁移过、或自动探测读到错误副本时指定。"
        ),
    )
    p.add_argument('--list-chats', action='store_true', help='列出有本地消息的可靠会话 username、备注及昵称（JSON）')
    p.add_argument('--username', action='append', default=None, help='按稳定 username 导出，可重复提供以选择多个会话')
    p.add_argument('--format', dest='formats', action='append', choices=('txt', 'md', 'json'), default=None, help='只写指定聊天格式，可重复提供')
    a = p.parse_args()

    if a.username and a.export_all:
        p.error('--username 与 --all 不能同时使用。')
    if a.list_chats:
        if a.username or a.export_all or a.name:
            p.error('--list-chats 不能同时进行导出。')
        from chat_list_service import list_chats
        print(json.dumps(list_chats(a.db_dir), ensure_ascii=False, indent=2))
        raise SystemExit(0)
    if a.username or (a.export_all and a.formats):
        if a.limit is not None:
            p.error('按格式选择的新批量入口不支持 --limit，请先列出会话再按 username 选择。')
        if a.name:
            p.error('--username 不接受昵称位置参数。')
        from export_task_service import CancelToken, ExportOptions, export_selected_chats
        token = CancelToken()
        previous = signal.signal(signal.SIGINT, lambda *_: token.cancel())
        try:
            result = export_selected_chats(a.username, ExportOptions(
                out_root=a.out, formats=tuple(a.formats or ('txt', 'md', 'json')),
                db_dir=a.db_dir, export_images=a.images or a.media,
                export_files=a.files or a.media, export_voices=a.voices or a.media,
                export_videos=a.videos or a.media, transcribe_voices=a.transcribe_voices),
                progress=lambda e: print(e.get('log') or f"{e['stage']} {e.get('completed', 0)}/{e.get('total', 0)}"),
                cancel_token=token)
        finally:
            signal.signal(signal.SIGINT, previous)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        raise SystemExit(130 if result['state'] == 'cancelled' else
                         1 if result['failed'] or result['state'] == 'failed' or result.get('summary_error')
                         or result.get('partial_cleanup_error') or not result.get('sensitive_cache_cleanup') else 0)
    if a.formats:
        p.error('--format 请配合 --username 或 --all 使用；原昵称入口保留三格式行为。')

    if a.limit is not None and a.limit <= 0:
        p.error("--limit 必须是正整数。")
    if a.limit is not None and not a.export_all:
        p.error("--limit 只能配合 --all 使用。")

    if a.install_asr:
        install_local_asr_model(progress=print)
        raise SystemExit(0)
    if a.install_rust_silk:
        install_rust_silk(progress=print)
        raise SystemExit(0)
    if a.clear_sensitive_cache:
        report = clear_sensitive_cache()
        for path in report.get("removed") or []:
            print("已清除：" + path)
        if not report.get("removed"):
            print("没有发现需要清理的敏感缓存。")
        failed = report.get("failed") or []
        if failed:
            for item in failed:
                print(
                    "清理失败："
                    + str(item.get("path"))
                    + "："
                    + str(item.get("error"))
                )
            raise SystemExit(1)
        raise SystemExit(0)
    if a.export_all:
        if a.name:
            print(f"注意：已指定 --all，忽略会话关键词“{a.name}”。")
        result = export_all_chats(
            a.out,
            progress=print,
            export_images=(a.images or a.media),
            export_files=(a.files or a.media),
            export_voices=(a.voices or a.media or a.transcribe_voices),
            export_videos=(a.videos or a.media),
            transcribe_voices=a.transcribe_voices,
            db_dir=a.db_dir,
            limit=a.limit,
        )
        print(
            f"可可靠识别会话 {result['discovered_total']}，"
            f"本次处理 {result['selected_total']}；"
            f"成功 {result['exported']}，无消息 {result['skipped_empty']}，"
            f"失败 {result['failed']}，消息总数 {result['total_messages']}。"
        )
        if result.get("unresolved_message_tables"):
            print(
                f"另有 {result['unresolved_message_tables']} 个消息表无法可靠反查身份，"
                "已跳过而不是猜测。"
            )
        print("输出目录：" + result["output_dir"])
        print("总索引：" + result["index_md"])
        if not result["sensitive_cache_cleanup"]:
            print(
                "敏感临时缓存自动清理失败："
                + str(result.get("sensitive_cache_cleanup_error"))
            )
            raise SystemExit(1)
        raise SystemExit(1 if result["failed"] else 0)

    if not a.name:
        p.error(
            "请提供好友备注/昵称或群名；或用 --all 导出全部聊天；"
            "或使用 --install-asr / --install-rust-silk / "
            "--clear-sensitive-cache"
        )

    result = export_chat(
        a.name,
        a.out,
        progress=print,
        export_images=(a.images or a.media),
        export_files=(a.files or a.media),
        export_voices=(a.voices or a.media or a.transcribe_voices),
        export_videos=(a.videos or a.media),
        transcribe_voices=a.transcribe_voices,
        db_dir=a.db_dir,
    )
    print(result)
