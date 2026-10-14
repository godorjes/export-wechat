"""Metadata-only conversation discovery and UI-independent selection state."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import exporter_core as core


@contextmanager
def database_session(db_dir=None, progress=None, account=None, state=None):
    """Use the upstream reader only within its existing sensitive sandbox."""
    core.clear_current_sensitive_cache()
    workdir = core._create_sensitive_workdir()
    state = state if state is not None else {}
    try:
        with core._upstream_sensitive_sandbox(workdir):
            if db_dir and (Path(db_dir) / 'db_storage').is_dir():
                source = Path(db_dir)
                account = source.name
                db_dir = source.parent
            resolved = core.resolve_db_dir(db_dir) if db_dir else None
            kwargs = {'db_dir': resolved, 'workdir': str(workdir)}
            if account:
                kwargs['account'] = account
            state['db'] = core.WeChatDB(**kwargs)
            if account and getattr(state['db'], 'account', account) != account:
                raise RuntimeError('指定账号无法读取，请确认该账号已经登录。')
            yield state
    finally:
        ok, error = core._cleanup_sensitive_workdir(workdir, progress=progress)
        state['sensitive_cache_cleanup'] = ok
        state['sensitive_cache_cleanup_error'] = error


def list_chats(db_dir=None, progress=None):
    with database_session(db_dir, progress) as state:
        chats, unresolved = core._batch_chat_candidates(state['db'], progress)
        result = {'chats': chats, 'unresolved_message_tables': unresolved}
        account = getattr(state['db'], 'account_dir', None)
        result['account_dir'] = str(account) if account else None
    result.update({k: v for k, v in state.items() if k != 'db'})
    return result


class ChatSelection:
    def __init__(self):
        self.chats = {}
        self.selected = set()

    def replace(self, chats):
        self.chats = {c['username']: dict(c) for c in chats}
        self.selected.intersection_update(self.chats)

    def filter(self, category='全部', query=''):
        needle = query.strip().casefold()
        return [c for c in self.chats.values()
                if (category == '全部' or bool(c.get('is_group')) == (category == '群聊'))
                and (not needle or any(needle in str(c.get(k) or '').casefold()
                                      for k in ('name', 'remark', 'nick_name', 'username')))]

    def toggle(self, username):
        if username not in self.chats:
            return
        if username in self.selected:
            self.selected.remove(username)
        else:
            self.selected.add(username)

    def select_visible(self, chats):
        self.selected.update(c['username'] for c in chats if c['username'] in self.chats)

    def clear(self):
        self.selected.clear()
