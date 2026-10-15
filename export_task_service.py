"""Selective exports reuse the upstream engine and one sensitive DB context."""
from __future__ import annotations

from dataclasses import dataclass
from contextlib import contextmanager
from datetime import datetime
import errno
import hashlib
import os
import shutil
import tempfile
import threading
import time
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


class PublicationError(OSError):
    def __init__(self, cause, retained_paths):
        super().__init__('Incomplete output cleanup')
        self.cause = cause
        self.retained_paths = retained_paths


@contextmanager
def _output_lock(destination, token):
    # Stable across processes and unaffected by the sensitive tempfile sandbox.
    locks = core._persistent_app_data_dir() / 'output-locks'
    locks.mkdir(parents=True, exist_ok=True)
    identity = os.path.normcase(str(destination.resolve())).encode('utf8')
    lock_path = locks / (hashlib.sha256(identity).hexdigest() + '.lock')
    with lock_path.open('a+b') as handle:
        acquired = False
        if os.name == 'nt':
            import msvcrt
            acquire = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            release = lambda: msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            acquire = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            release = lambda: fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        try:
            while not acquired:
                token.check()
                handle.seek(0)
                try:
                    acquire()
                    acquired = True
                except OSError as exc:
                    if exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    time.sleep(.05)
            yield
        finally:
            if acquired:
                try:
                    handle.seek(0)
                    release()
                except OSError:
                    # Closing the descriptor also releases the OS lock.
                    pass


def _available_stem(name, reserved):
    base = core.safe_folder_name(name)[:80].rstrip(' .') or '未命名会话'
    device = base.split('.')[0].upper()
    if device in {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}:
        base = '_' + base
    number = 1
    while True:
        stem = base if number == 1 else f'{base} ({number})'
        names = {f'{stem}.{fmt}'.casefold() for fmt in ('txt', 'md', 'json')}
        names.add(f'{stem}_media'.casefold())
        if not names & reserved:
            reserved.update(names)
            return stem
        number += 1


def _publish_flat(source, destination, exported, token):
    """Publish complete files; Windows rename never replaces an existing target."""
    moved = []
    try:
        # Attachments must be available before a completed record is exposed.
        items = sorted(source.iterdir(), key=lambda p: (p.is_file(), p.name))
        for item in items:
            token.check()
            target = destination / item.name
            if target.exists() or target.is_symlink():
                raise FileExistsError()
            item.rename(target)
            moved.append((item, target))
        token.check()
    except BaseException as exc:
        retained = []
        for staged, published in reversed(moved):
            try:
                published.rename(staged)
            except OSError:
                retained.append(str(published))
        if retained:
            raise PublicationError(exc, retained) from exc
        raise
    result = dict(exported, output_dir=str(destination))
    for key in ('txt', 'md', 'json'):
        if result.get(key):
            result[key] = str(destination / Path(result[key]).name)
    return result


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
    dated_name = datetime.now().strftime('%Y-%m-%d') + 'WeChatExport'
    task = out if out.name == dated_name else out / dated_name
    task.mkdir(parents=True, exist_ok=True)
    partial = Path(tempfile.mkdtemp(prefix='.partial-', dir=task))
    result = dict(state='running', output_dir=str(task), discovered_total=0,
                  selected_total=0, unresolved_message_tables=0, exported=0,
                  failed=0, skipped_empty=0, cancelled=0, total_messages=0,
                  formats=list(options.formats), chats=[])
    current_name = ''
    session = {}
    selected = usernames or []

    def emit(stage, **fields):
        if progress:
            progress(dict(stage=stage, name=current_name,
                          completed=len(result['chats']), total=result['selected_total'],
                          messages=result['total_messages'], failed=result['failed'], **fields))

    def log(message):
        emit('日志', log=message)

    try:
        emit('连接数据库')
        token.check()
        with database_session(options.db_dir, log, options.account, session):
            db = session['db']
            token.check()
            chats, unresolved = core._batch_chat_candidates(db, log, cancel_token=token)
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
                        with _output_lock(task, token):
                            reserved = {p.name.casefold() for p in task.iterdir()}
                            stem = _available_stem(current_name, reserved)
                            exported = core._export_chat_impl(
                                out_root=partial, db=db, contact=contact, folder_name=folder,
                                index_cache=cache, formats=options.formats, cancel_token=token,
                                file_stem=stem, media_folder=stem + '_media',
                                progress=log, event=lambda e: emit(e['stage'], current=e['current'], current_total=e['total']),
                                export_images=options.export_images, export_files=options.export_files,
                                export_voices=options.export_voices, export_videos=options.export_videos,
                                transcribe_voices=options.transcribe_voices,
                            )
                            token.check()
                            exported = _publish_flat(partial / folder, task, exported, token)
                        entry.update(exported, status='exported')
                        result['exported'] += 1
                        result['total_messages'] += exported['message_count']
                    except PublicationError as exc:
                        entry['error'] = safe_error(exc.cause)
                        entry['partial_files'] = exc.retained_paths
                        result['partial_cleanup_error'] = '部分未完成文件无法回收，请关闭占用文件的程序后清理。'
                        if isinstance(exc.cause, ExportCancelled):
                            entry['status'] = 'cancelled'
                            result['cancelled'] += 1
                        else:
                            result['failed'] += 1
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
                emit('会话完成', status=entry['status'])
        result.update({k: v for k, v in session.items() if k != 'db'})
        result['state'] = 'cancelled' if token.cancelled else ('completed_with_errors' if result['failed'] else 'completed')
    except ExportCancelled:
        result['state'] = 'cancelled'
        result['selected_total'] = len(selected)
        processed = {c['username'] for c in result['chats']}
        for username in selected:
            if username not in processed:
                result['chats'].append(dict(username=username, name=username, status='cancelled',
                                           message_count=0, output_dir=None, txt=None, md=None, json=None))
                result['cancelled'] += 1
        result.update({k: v for k, v in session.items() if k != 'db'})
        result.setdefault('sensitive_cache_cleanup', True)
    except Exception as exc:
        result.update(state='failed', error=safe_error(exc))
        if 'session' in locals():
            result.update({k: v for k, v in session.items() if k != 'db'})
    finally:
        try:
            # Only remove this batch's own staging path, never prior exports.
            if partial.resolve().parent != task.resolve() or not partial.name.startswith('.partial-'):
                raise ValueError('Unexpected staging path')
            shutil.rmtree(partial)
        except OSError as exc:
            result['partial_cleanup_error'] = safe_error(exc)
    emit('任务结束', state=result['state'])
    return result
