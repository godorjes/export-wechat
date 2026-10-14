"""Selective exports reuse the upstream engine and one sensitive DB context."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import shutil
import tempfile
import threading
from pathlib import Path

import exporter_core as core
from chat_list_service import database_session


class ExportCancelled(Exception):
    pass


class CancelToken:
    def __init__(self):
        self._event = threading.Event()

    def cancel(self):
        self._event.set()

    @property
    def cancelled(self):
        return self._event.is_set()

    def check(self):
        if self.cancelled:
            raise ExportCancelled()


@dataclass(frozen=True)
class ExportOptions:
    out_root: str | Path = 'exports'
    formats: tuple[str, ...] = ('txt', 'md', 'json')
    export_images: bool = False
    export_files: bool = False
    db_dir: str | None = None
    account: str | None = None
    # Existing optional engine functionality remains available through services/CLI.
    export_voices: bool = False
    export_videos: bool = False
    transcribe_voices: bool = False

    def __post_init__(self):
        object.__setattr__(self, 'formats', tuple(sorted(core._normalize_formats(self.formats))))
        if not str(self.out_root).strip():
            raise ValueError('请选择输出目录。')


def safe_error(exc):
    """Do not propagate arbitrary exception strings that may contain chat/key data."""
    if isinstance(exc, PermissionError):
        return '权限不足，请检查数据或输出目录的访问权限。'
    if isinstance(exc, FileNotFoundError):
        return '文件或目录不存在，请刷新数据源后重试。'
    if isinstance(exc, OSError):
        return f'文件或数据库读写失败（{type(exc).__name__}），请检查路径和磁盘空间。'
    return f'数据读取或处理失败（{type(exc).__name__}），请确认微信已登录、所选账号和版本兼容。'


def validate_output_directory(path):
    root = Path(path).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    # Probe in the actual destination without touching existing user files.
    with tempfile.TemporaryFile(dir=root):
        pass
    return root


def _write_summary(root, result):
    data = {k: v for k, v in result.items() if not k.startswith('index_')}
    target = root / 'task_index.json'
    tmp = root / 'task_index.json.tmp'
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8-sig')
    tmp.replace(target)
    lines = ['# 微信聊天导出任务', '',
             f"状态：{result['state']}；成功 {result['exported']}；失败 {result['failed']}；"
             f"无消息 {result['skipped_empty']}；取消 {result['cancelled']}；消息 {result['total_messages']}", '',
             '敏感缓存清理：' + ('成功' if result.get('sensitive_cache_cleanup') else '等待结束或清理未成功'), '']
    for item in result['chats']:
        # Escape display metadata before writing a Markdown index.
        name = str(item['name']).replace('\n', ' ').replace('[', '\\[').replace(']', '\\]')
        lines.append(f"- {name} ({item['username']})：{item['status']}，{item['message_count']} 条")
        for fmt in ('txt', 'md', 'json'):
            if item.get(fmt):
                rel = Path(item[fmt]).relative_to(root).as_posix()
                lines.append(f'  - [{fmt.upper()}]({core._markdown_href(rel)})')
        if item.get('error'):
            lines.append('  - ' + item['error'])
    (root / 'task_index.md').write_text('\n'.join(lines) + '\n', encoding='utf-8-sig')
    result['index_json'] = str(target)
    result['index_md'] = str(root / 'task_index.md')


def export_selected_chats(usernames, options, progress=None, cancel_token=None):
    """None selects all reliable chats; an explicit collection selects exact IDs."""
    if usernames is not None:
        if isinstance(usernames, str):
            raise ValueError('usernames 必须是 username 集合。')
        usernames = list(dict.fromkeys(usernames))
        if not usernames or any(not isinstance(x, str) or not x.strip() for x in usernames):
            raise ValueError('请至少选择一个有效会话。')
    token = cancel_token or CancelToken()
    out = validate_output_directory(options.out_root)
    task = Path(tempfile.mkdtemp(prefix=datetime.now().strftime('task-%Y%m%d-%H%M%S-'), dir=out))
    partial = task / '.partial'
    partial.mkdir()
    marker = task / 'INCOMPLETE.txt'
    marker.write_text('任务尚未完成。仅 task_index 中 exported 的会话为完整结果。', encoding='utf8')
    result = dict(state='running', output_dir=str(task), discovered_total=0,
                  selected_total=0, unresolved_message_tables=0, exported=0,
                  failed=0, skipped_empty=0, cancelled=0, total_messages=0,
                  formats=list(options.formats), chats=[])
    current_name = ''
    session = {}

    def emit(stage, **fields):
        if progress:
            progress(dict(stage=stage, name=current_name,
                          completed=len(result['chats']), total=result['selected_total'],
                          messages=result['total_messages'], failed=result['failed'], **fields))

    def log(message):
        emit('日志', log=message)

    try:
        emit('连接数据库')
        with database_session(options.db_dir, log, options.account, session):
            db = session['db']
            chats, unresolved = core._batch_chat_candidates(db, log)
            available = {c['username']: c for c in chats}
            selected = list(available) if usernames is None else usernames
            result.update(discovered_total=len(chats), selected_total=len(selected),
                          unresolved_message_tables=unresolved,
                          account_dir=getattr(db, 'account_dir', None))
            cache = {}
            for username in selected:
                contact = available.get(username)
                current_name = contact['name'] if contact else username
                entry = dict(username=username, name=current_name, status='failed',
                             message_count=0, output_dir=None, txt=None, md=None, json=None,
                             is_group=username.endswith('@chatroom'), error=None)
                if token.cancelled:
                    entry['status'] = 'cancelled'
                    result['cancelled'] += 1
                elif contact is None:
                    entry['error'] = '该 username 已不存在或无法可靠关联本地消息，请刷新列表。'
                    result['failed'] += 1
                else:
                    folder = core._stable_batch_folder(username)
                    emit('读取消息')
                    try:
                        exported = core._export_chat_impl(
                            out_root=partial, db=db, contact=contact, folder_name=folder,
                            index_cache=cache, formats=options.formats, cancel_token=token,
                            progress=log, event=lambda e: emit(e['stage'], current=e['current'], current_total=e['total']),
                            export_images=options.export_images, export_files=options.export_files,
                            export_voices=options.export_voices, export_videos=options.export_videos,
                            transcribe_voices=options.transcribe_voices,
                        )
                        token.check()
                        source = partial / folder
                        final = task / folder
                        source.rename(final)
                        for key in ('txt', 'md', 'json'):
                            if exported.get(key):
                                exported[key] = str(final / Path(exported[key]).name)
                        exported['output_dir'] = str(final)
                        entry.update(exported, status='exported')
                        result['exported'] += 1
                        result['total_messages'] += exported['message_count']
                    except ExportCancelled:
                        entry['status'] = 'cancelled'
                        result['cancelled'] += 1
                    except core.EmptyConversationError:
                        entry.update(status='skipped_empty', error='没有可读取的本地消息。')
                        result['skipped_empty'] += 1
                    except Exception as exc:
                        entry['error'] = safe_error(exc)
                        result['failed'] += 1
                result['chats'].append(entry)
                _write_summary(task, result)
                emit('会话完成', status=entry['status'])
        result.update({k: v for k, v in session.items() if k != 'db'})
        result['state'] = 'cancelled' if token.cancelled else ('completed_with_errors' if result['failed'] else 'completed')
    except Exception as exc:
        result.update(state='failed', error=safe_error(exc))
        if 'session' in locals():
            result.update({k: v for k, v in session.items() if k != 'db'})
    finally:
        try:
            # Only remove this batch's own staging path, never prior exports.
            if partial.resolve().parent != task.resolve():
                raise ValueError('Unexpected staging path')
            shutil.rmtree(partial)
        except OSError as exc:
            result['partial_cleanup_error'] = safe_error(exc)
        if not result.get('partial_cleanup_error'):
            marker.unlink(missing_ok=True)
        _write_summary(task, result)
    emit('任务结束', state=result['state'])
    return result
