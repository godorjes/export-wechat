from __future__ import annotations

import base64
from collections import deque
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import psutil
import exporter_core as core

from chat_list_service import list_chats
from export_task_service import CancelToken, ExportOptions, export_selected_chats, safe_error
from wechat_data_dirs import _account_dirs, discover_wechat_data_dirs
from ui.chat_list import ChatList
from ui.theme import (BG, WHITE, INK, MUTED, LINE, GREEN, RoundedCard, RoundedButton,
                      ScrollFrame, combo_field, configure_theme, destination_folders,
                      label, link_button, rounded_rect)


def discover_sources(progress=None):
    cleanup = core.clear_current_sensitive_cache()
    if progress and cleanup.get('failed'):
        progress('部分异常退出的敏感缓存尚未清理，请关闭占用文件的程序后重试。')
    sources = []
    for root in discover_wechat_data_dirs():
        for account in _account_dirs(Path(root['path'])):
            storage = account / 'db_storage'
            try:
                files = list(storage.rglob('*.db'))
                if any(p.name in {'contact.db', 'session.db'} for p in files) and any(p.name.startswith('message_') for p in files):
                    sources.append(str(account))
            except OSError:
                continue
    return list(dict.fromkeys(sources))


def process_status():
    try:
        running = any((p.info.get('name') or '').lower() in {'weixin.exe', 'wechat.exe'}
                      for p in psutil.process_iter(['name']))
        return '微信正在运行' if running else '未检测到微信进程，请先登录微信'
    except (psutil.Error, OSError):
        return '微信进程状态未知'


def read_detected_sources(sources, progress=None, stopped=None):
    last_error = None
    for source in sources:
        if stopped and stopped():
            raise RuntimeError('检测已停止。')
        try:
            result = list_chats(source, progress)
            result['account_dir'] = result.get('account_dir') or source
            return result
        except Exception as exc:
            last_error = exc
            if progress:
                progress('该本地账号暂不可读取，继续检测其他账号。')
    if last_error:
        raise last_error
    raise RuntimeError('未找到可读取账号。')


class App(tk.Tk):
    def __init__(self, auto_load=True, app_directory=None, icon=None):
        super().__init__()
        self.title('微信聊天记录导出 V1.0')
        self.geometry('1160x780')
        self.minsize(980, 640)
        configure_theme(self)
        if icon:
            try:
                self._icon = tk.PhotoImage(data=base64.b64decode(icon))
                self.iconphoto(True, self._icon)
            except tk.TclError:
                pass
        self.q = queue.Queue()
        self.busy = False
        self.worker_thread = None
        self.cancel_token = None
        self.closing = False
        self.last_result = None
        self.loaded_source = None
        self.source_ready = False
        self.callbacks = {}
        self.sources = []
        self.detecting = False
        self._poll_id = self._discover_id = None
        self._settings_guard = False
        self.settings_controls = []
        self.task_log = deque(maxlen=1200)
        self.destinations = destination_folders()
        self.out = tk.StringVar(value=str(Path(app_directory) / 'exports') if app_directory else next(iter(self.destinations.values())))
        self.source = tk.StringVar()
        self.source_status = tk.StringVar(value='点击右上角“检测微信账号”读取可用的本地账号数据。')
        self.account_status = tk.StringVar(value='未识别微信账号')
        self.state = tk.StringVar(value='本地读取 · 本地保存')
        self.progress_text = tk.StringVar(value='导出中…')
        self.format_vars = {f: tk.BooleanVar(value=f == 'txt') for f in ('txt', 'md', 'json')}
        self.images = tk.BooleanVar(value=False)
        self.files = tk.BooleanVar(value=False)
        self.content_choice = tk.StringVar(value='仅聊天文字（推荐）')
        self.format_help = tk.StringVar(value='适合直接打开、阅读和保存。')
        self.content_help = tk.StringVar(value='导出更快，文件体积更小。')
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        header = tk.Frame(self, background=BG)
        header.grid(row=0, column=0, sticky='ew', padx=34, pady=(24, 22))
        header.columnconfigure(1, weight=1)
        mark = tk.Canvas(header, width=46, height=46, background=BG, highlightthickness=0)
        mark.grid(row=0, column=0, rowspan=2, padx=(0, 12))
        rounded_rect(mark, 1, 1, 45, 45, 14, fill=GREEN, outline='')
        mark.create_oval(10, 10, 36, 34, outline=WHITE, width=2)
        mark.create_line(13, 29, 10, 36, 20, 32, fill=WHITE, width=2)
        for x in (16, 23, 30):
            mark.create_oval(x-1, 21, x+1, 23, fill=WHITE, outline='')
        tk.Label(header, text='微信聊天记录导出', background=BG, foreground=INK,
                 font=('Microsoft YaHei UI', 17, 'bold'), anchor='w').grid(row=0, column=1, sticky='w')
        label(header, '选好聊天，轻松保存到电脑', small=True, color=MUTED, background=BG).grid(row=1, column=1, sticky='w', pady=(3, 0))
        tools = tk.Frame(header, background=BG)
        tools.grid(row=0, column=2, rowspan=2, sticky='e')
        self.account_btn = RoundedButton(tools, '检测微信账号', self.discover, height=36, small=True)
        self.account_btn.pack(side='left')
        self.account_dot = label(tools, '●', small=True, color='#db5252', background=BG)
        self.account_dot.pack(side='left', padx=(8, 6))
        self.account_status_label = label(tools, variable=self.account_status, small=True, color=MUTED, background=BG)
        self.account_status_label.pack(side='left', padx=(0, 16))
        link_button(tools, '使用帮助', self.show_help, color=MUTED).pack(side='left')

        layout = tk.Frame(self, background=BG)
        layout.grid(row=1, column=0, sticky='nsew', padx=34, pady=(0, 14))
        layout.rowconfigure(0, weight=1)
        layout.columnconfigure(0, weight=135, uniform='panels')
        layout.columnconfigure(1, weight=91, uniform='panels')
        left = RoundedCard(layout)
        left.grid(row=0, column=0, sticky='nsew', padx=(0, 8))
        left.body.rowconfigure(0, weight=1)
        left.body.columnconfigure(0, weight=1)
        self.chat_list = ChatList(left.body, self.update_buttons, self.refresh)
        self.chat_list.grid(row=0, column=0, sticky='nsew')
        right = RoundedCard(layout)
        right.grid(row=0, column=1, sticky='nsew', padx=(9, 0))
        right.body.columnconfigure(0, weight=1)
        right.body.rowconfigure(1, weight=1)
        heading = tk.Frame(right.body, background=WHITE)
        heading.grid(row=0, column=0, sticky='ew', padx=22, pady=(8, 18))
        label(heading, '导出设置', bold=True).pack(side='left')
        label(heading, '简单设置就能开始', small=True, color=MUTED).pack(side='right')
        scroller = ScrollFrame(right.body)
        scroller.grid(row=1, column=0, sticky='nsew', padx=(22, 15))
        self.settings_canvas = scroller.canvas
        self.settings_body = opts = scroller.body
        opts.columnconfigure(0, weight=1)
        format_section = tk.Frame(opts, background=WHITE)
        format_section.grid(row=0, column=0, sticky='ew', pady=(0, 19))
        format_section.columnconfigure(0, weight=1)
        label(format_section, '保存格式', small=True, bold=True, color='#41505c').grid(row=0, column=0, sticky='w', pady=(0, 8))
        _, self.format_combo = combo_field(format_section, None, ('txt', 'md', 'json'), width=1,
                                          variables=self.format_vars,
                                          labels={'txt': 'TXT', 'md': 'Markdown', 'json': 'JSON'})
        self.format_combo.grid(row=1, column=0, sticky='ew')
        self.settings_controls.append((self.format_combo, 'readonly'))
        label(format_section, variable=self.format_help, small=True, color='#99a4ac').grid(row=2, column=0, sticky='w', pady=(7, 0))
        self.content_combo = self._setting_field(opts, 1, '包含哪些内容', self.content_choice,
                            ('仅聊天文字（推荐）', '文字和图片', '文字、图片和普通文件', '文字和普通文件'), self.content_help)
        self.content_combo.bind('<<ComboboxSelected>>', self.content_changed)
        save = tk.Frame(opts, background=WHITE)
        save.grid(row=2, column=0, sticky='ew', pady=(0, 19))
        save.columnconfigure(0, weight=1)
        label(save, '保存到哪里', small=True, bold=True, color='#41505c').grid(row=0, column=0, sticky='w', pady=(0, 8))
        self.custom_folder = tk.Frame(save, background=WHITE)
        self.custom_folder.grid(row=1, column=0, sticky='ew')
        self.custom_folder.columnconfigure(0, weight=1)
        path_shell = RoundedCard(self.custom_folder, height=42, width=1, radius=9, inset=(8, 5), shadow=False, background=WHITE)
        path_shell.grid(row=0, column=0, sticky='ew')
        self.path_entry = ttk.Entry(path_shell.body, textvariable=self.out, width=1)
        self.path_entry.pack(fill='both', expand=True)
        self.browse_output_btn = RoundedButton(self.custom_folder, '选择', self.browse_output, height=42, small=True)
        self.browse_output_btn.grid(row=0, column=1, padx=(8, 0))
        self.settings_controls.extend(((self.path_entry, 'normal'), (self.browse_output_btn, 'normal')))
        scroller.bind_wheel()

        footer = tk.Frame(right.body, background='#fbfdfc')
        footer.grid(row=2, column=0, sticky='ew', pady=(14, 0))
        footer.columnconfigure(0, weight=1)
        tk.Frame(footer, background=LINE, height=1).grid(row=0, column=0, sticky='ew')
        action = tk.Frame(footer, background='#fbfdfc')
        action.grid(row=1, column=0, sticky='ew', padx=22, pady=(16, 0))
        action.columnconfigure(0, weight=1)
        self.export_btn = RoundedButton(action, '选择聊天后开始导出', self.start_selected, primary=True, height=46, width=1)
        self.export_btn.grid(row=0, column=0, sticky='ew')
        self.task_frame = tk.Frame(action, background='#fbfdfc')
        self.task_frame.grid(row=1, column=0, sticky='ew', pady=(4, 0))
        self.task_frame.columnconfigure(0, weight=1)
        task_label = label(self.task_frame, variable=self.progress_text, small=True, color=MUTED,
                           background='#fbfdfc', wraplength=260, justify='left')
        task_label.grid(row=0, column=0, sticky='ew')
        self.cancel_btn = RoundedButton(self.task_frame, '取消导出', self.cancel, height=39, state='disabled')
        self.cancel_btn.grid(row=1, column=0, sticky='ew', pady=(12, 0))
        self.task_frame.grid_remove()
        self.result_buttons = tk.Frame(action, background='#fbfdfc')
        self.result_buttons.grid(row=2, column=0, sticky='ew', pady=(10, 0))
        self.result_buttons.columnconfigure(0, weight=1)
        self.open_btn = RoundedButton(self.result_buttons, '打开文件夹', self.open_output, height=34, small=True, state='disabled', width=1)
        self.open_btn.grid(row=0, column=0, sticky='ew')
        self.result_buttons.grid_remove()
        state_label = label(footer, variable=self.state, small=True, color=MUTED,
                            background='#fbfdfc', wraplength=300, justify='center')
        self.state_label = state_label
        state_label.configure(anchor='center')
        state_label.grid(row=2, column=0, sticky='ew', padx=22, pady=(11, 3))
        action.bind('<Configure>', lambda event: task_label.configure(wraplength=max(120, event.width-5)))
        footer.bind('<Configure>', lambda event: state_label.configure(wraplength=max(160, event.width-44)))
        self.footer_status = label(self, variable=self.source_status, small=True, color='#96a2a9',
                                  background=BG, wraplength=1050, justify='center')
        self.footer_status.configure(anchor='center')
        self.footer_status.grid(row=2, column=0, sticky='ew', padx=34, pady=(0, 16))
        self.bind('<Configure>', self._window_resized, add='+')
        for var in self.format_vars.values():
            var.trace_add('write', self.sync_formats)
        self.images.trace_add('write', self.sync_content)
        self.files.trace_add('write', self.sync_content)
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.update_buttons()
        self._poll_id = self.after(60, self.poll)
        if auto_load:
            self._discover_id = self.after(0, self.discover)

    def _window_resized(self, event):
        if event.widget == self:
            self.footer_status.configure(wraplength=max(500, event.width-68))

    def _setting_field(self, parent, row, title, variable, values, hint):
        section = tk.Frame(parent, background=WHITE)
        section.grid(row=row, column=0, sticky='ew', pady=(0, 19 if hint else 0))
        section.columnconfigure(0, weight=1)
        label(section, title, small=True, bold=True, color='#41505c').grid(row=0, column=0, sticky='w', pady=(0, 8))
        shell, control = combo_field(section, variable, values, width=1)
        shell.grid(row=1, column=0, sticky='ew')
        if hint:
            hint_label = label(section, variable=hint, small=True, color='#99a4ac', wraplength=300, justify='left')
            hint_label.grid(row=2, column=0, sticky='ew', pady=(7, 0))
            section.bind('<Configure>', lambda event: hint_label.configure(wraplength=max(180, event.width-5)))
        self.settings_controls.append((control, 'readonly'))
        return control

    def sync_formats(self, *_args):
        if self._settings_guard:
            return
        formats = [f for f, v in self.format_vars.items() if v.get()]
        mapping = {'txt': '适合直接打开、阅读和保存。',
                   'md': '适合整理笔记，保留清晰的文字结构。',
                   'json': '适合进一步处理聊天数据。'}
        if len(formats) == 1:
            hint = mapping[formats[0]]
        else:
            hint = '同时保存：' + '、'.join(f.upper() for f in formats) if formats else '请至少选择一种保存格式。'
        self.format_help.set(hint)
        self.update_buttons()

    def content_changed(self, _event=None):
        flags = {'仅聊天文字（推荐）': (False, False), '文字和图片': (True, False),
                 '文字、图片和普通文件': (True, True), '文字和普通文件': (False, True)}
        images, files = flags[self.content_choice.get()]
        self._settings_guard = True
        try:
            self.images.set(images)
            self.files.set(files)
        finally:
            self._settings_guard = False
        self.sync_content()

    def sync_content(self, *_args):
        if self._settings_guard:
            return
        name, hint = {
            (False, False): ('仅聊天文字（推荐）', '导出更快，文件体积更小。'),
            (True, False): ('文字和图片', '一并保存聊天中的图片，文件会更大。'),
            (True, True): ('文字、图片和普通文件', '包含图片和普通文件附件，导出时间可能更长。'),
            (False, True): ('文字和普通文件', '保存普通文件附件，不导出图片。'),
        }[(self.images.get(), self.files.get())]
        self.content_choice.set(name)
        self.content_help.set(hint)

    def get_export_options(self):
        return ExportOptions(out_root=self.out.get().strip(),
                             formats=tuple(f for f, v in self.format_vars.items() if v.get()),
                             export_images=self.images.get(), export_files=self.files.get(),
                             db_dir=self.loaded_source)

    def show_help(self):
        messagebox.showinfo('使用帮助', '1. 先在电脑上登录微信，点击“检测微信账号”读取可用数据。\n\n'
                            '2. 勾选需要的聊天，勾选一种或多种保存格式，选择内容和位置。\n\n'
                            '3. 点击导出，完成后打开文件夹查看结果。\n\n'
                            '导出过程可取消；失败原因会在任务状态处显示。', parent=self)

    def destroy(self):
        for token in (self._poll_id, self._discover_id):
            if token:
                self.after_cancel(token)
        super().destroy()

    def log(self, text):
        self.task_log.append(str(text))

    def update_buttons(self):
        if not hasattr(self, 'chat_list'):
            return
        ready = not self.busy and self.source_ready and bool(self.chat_list.model.chats)
        has_formats = any(var.get() for var in self.format_vars.values())
        if hasattr(self, 'export_btn'):
            self.export_btn.configure(state='normal' if ready and self.chat_list.model.selected and has_formats else 'disabled')
            selected = len(self.chat_list.model.selected)
            self.export_btn.configure(text='请选择保存格式' if not has_formats else
                                      f'导出 {selected} 个聊天' if selected else '选择聊天后开始导出')
        self.account_btn.configure(state='disabled' if self.busy or self.detecting else 'normal',
                                   text='检测中…' if self.detecting else '重新检测' if self.source_ready else '检测微信账号')
        self.account_status.set('检测中…' if self.detecting else '已识别微信账号' if self.source_ready else '未识别微信账号')
        self.account_status_label.configure(foreground=GREEN if self.source_ready else MUTED)
        self.account_dot.configure(foreground=GREEN if self.source_ready else '#db5252')
        self.chat_list.set_enabled(not self.busy)
        for widget, enabled_state in self.settings_controls:
            widget.configure(state='disabled' if self.busy else enabled_state)
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn.configure(state='normal' if self.busy and self.cancel_token and not self.cancel_token.cancelled else 'disabled')
            if self.busy and self.cancel_token:
                self.export_btn.grid_remove()
                self.task_frame.grid()
                self.state_label.grid_remove()
                self.result_buttons.grid_remove()
            else:
                self.export_btn.grid()
                self.task_frame.grid_remove()
                self.state_label.grid()

    def launch(self, kind, work, done):
        if self.busy or self.closing:
            return False
        self.busy = True
        self.callbacks[kind] = done
        self.update_buttons()
        def worker():
            try:
                result = work()
                self.q.put(('done', (kind, result)))
            except Exception as exc:
                reason = safe_error(exc)
                if kind in {'sources', 'list'}:
                    if isinstance(exc, PermissionError):
                        reason = '没有权限读取微信数据，请检查文件权限后重试。'
                    elif isinstance(exc, FileNotFoundError):
                        reason = '微信数据目录已变化，请重新检测。'
                    elif isinstance(exc, OSError):
                        reason = '暂时无法读取微信数据，请检查数据目录后重试。'
                    else:
                        reason = '未读到可用账号，请确认微信已登录且版本受支持。'
                self.q.put(('error', (kind, reason)))
        self.worker_thread = threading.Thread(target=worker, name=f'wechat-{kind}', daemon=False)
        self.worker_thread.start()
        return True

    def poll(self):
        try:
            for _ in range(120):
                kind, value = self.q.get_nowait()
                if kind == 'progress':
                    self.show_progress(value)
                elif kind == 'log':
                    self.log(value)
                elif kind in {'done', 'error'}:
                    task_kind, result = value
                    self.busy = False
                    self.cancel_token = None
                    self.update_buttons()
                    callback = self.callbacks.pop(task_kind, None)
                    if not self.closing:
                        if kind == 'done' and callback:
                            callback(result)
                        elif kind == 'error':
                            self.state.set('任务失败：'+result)
                            self.log(result)
                            if task_kind in {'sources', 'list'}:
                                self.detecting = False
                                self.source_ready = False
                                self.source_status.set('微信账号检测失败：' + result)
                                self.state.set('检测失败，可重新检测')
                                self.update_buttons()
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.destroy()
        else:
            self._poll_id = self.after(60, self.poll)

    def discover(self):
        if self.busy:
            return
        self.detecting = True
        self.source_ready = False
        self.state.set('正在检测微信账号…')
        self.source_status.set('正在查找可用的本地微信数据…')
        self.launch('sources', lambda: discover_sources(lambda m: self.q.put(('log', m))), self.sources_loaded)

    def sources_loaded(self, sources):
        self.sources = sources
        if sources:
            self.source.set(self.loaded_source if self.loaded_source in sources else sources[0])
            status = process_status()
            if status == '微信正在运行':
                ordered = [self.source.get()] + [s for s in sources if s != self.source.get()]
                self.refresh(candidates=ordered)
                return
            self.state.set('请登录微信后重新检测')
            self.source_status.set(status + ' · 仅发现本地数据目录')
        else:
            self.source.set('')
            self.loaded_source = None
            self.chat_list.replace([])
            self.state.set('未检测到可用账号')
            self.source_status.set('未找到可用微信数据，请登录微信后重新检测。')
        self.detecting = False
        self.source_ready = False
        self.update_buttons()

    def refresh(self, candidates=None):
        if self.busy:
            return
        source = self.source.get().strip()
        if not source:
            self.discover()
            return
        if source != self.loaded_source:
            self.chat_list.model.clear()
            self.chat_list.replace([])
            self.loaded_source = source
        self.state.set('正在加载会话元数据…')
        self.detecting = True
        self.source_ready = False
        progress = lambda m: self.q.put(('log', m))
        work = (lambda: read_detected_sources(candidates, progress, lambda: self.closing)) if candidates else (
               lambda: list_chats(source, progress))
        self.launch('list', work, self.list_loaded)

    def list_loaded(self, result):
        self.detecting = False
        self.source_ready = True
        account = result.get('account_dir') or self.loaded_source
        if account != self.loaded_source:
            self.chat_list.model.clear()
        self.loaded_source = account
        if self.loaded_source:
            self.source.set(self.loaded_source)
        self.chat_list.replace(result['chats'])
        count = result.get('unresolved_message_tables', 0)
        source = result.get('account_dir') or self.loaded_source
        self.source_status.set(f'已读取 {len(result["chats"])} 个聊天 · 账号数据可读取')
        self.state.set('就绪')
        if count:
            self.log(f'{count} 个消息表无法可靠确定身份，已跳过。')
        if not result.get('sensitive_cache_cleanup'):
            self.log('敏感临时缓存未完全清理。请关闭后重试或使用 CLI 清理。')

    def browse_output(self):
        folder = filedialog.askdirectory(parent=self, title='选择导出目录')
        if folder:
            self.out.set(folder)

    def start_selected(self):
        self.start_export(sorted(self.chat_list.model.selected))

    def start_export(self, usernames):
        if self.busy:
            return
        if not self.out.get().strip():
            self.state.set('请选择保存目录。')
            self.path_entry.focus_set()
            return
        try:
            if usernames is not None and not usernames:
                raise ValueError('请先勾选至少一个会话。')
            options = self.get_export_options()
        except ValueError as exc:
            messagebox.showwarning('导出设置', str(exc), parent=self)
            return
        token = self.cancel_token = CancelToken()
        self.state.set('导出中…')
        self.progress_text.set('导出中…')
        self.last_result = None
        self.result_buttons.grid_remove()
        self.open_btn.configure(state='disabled')
        self.launch('export', lambda: self.export_with_path_feedback(usernames, options,
                    lambda e: self.q.put(('progress', e)), token), self.export_done)

    @staticmethod
    def export_with_path_feedback(usernames, options, progress, token):
        try:
            # The service probes the destination before opening a WeChat DB.
            return export_selected_chats(usernames, options, progress, token)
        except (OSError, ValueError) as exc:
            return {'state': 'invalid_output', 'error': safe_error(exc)}

    def show_progress(self, event):
        if event.get('log'):
            self.log(event['log'])
        message = '正在取消…' if self.cancel_token and self.cancel_token.cancelled else '导出中…'
        self.progress_text.set(message)
        self.state.set(message)

    def export_done(self, result):
        if result['state'] == 'invalid_output':
            self.state.set('保存路径无效或不可写，请选择其他目录。')
            self.log(result['error'])
            self.path_entry.focus_set()
            return
        self.last_result = result
        self.result_buttons.grid()
        labels = {'completed': '导出完成', 'completed_with_errors': '导出完成，部分会话失败', 'cancelled': '任务已取消', 'failed': '任务失败'}
        self.state.set(labels.get(result['state'], result['state']))
        self.log(f"成功 {result['exported']} · 无消息 {result['skipped_empty']} · 失败 {result['failed']} · 取消 {result['cancelled']} · {result['total_messages']} 条消息")
        for c in result['chats']:
            if c.get('error'):
                self.log(f"{c['name']}：{c['error']}")
            for path in c.get('partial_files', []):
                self.log('未完成文件需清理：' + path)
        if result.get('error'):
            self.log(result['error'])
        if not result.get('sensitive_cache_cleanup') or result.get('partial_cleanup_error'):
            self.log('部分临时文件未完全清理，请关闭占用程序后重试清理。')
            self.state.set(self.state.get()+'；部分临时文件未清理，请关闭占用程序后重试。')
        error = result.get('error') or next((c.get('error') for c in result['chats'] if c.get('error')), None)
        if error and result['state'] in {'failed', 'completed_with_errors'}:
            self.state.set(self.state.get()+'：'+error)
        self.log('结果目录：' + result['output_dir'])
        self.open_btn.configure(state='normal')

    def cancel(self):
        if self.cancel_token:
            self.cancel_token.cancel()
            self.state.set('正在取消，等待当前安全检查点和清理…')
            self.progress_text.set('正在取消…')
            self.update_buttons()

    def on_close(self):
        if self.busy:
            self.closing = True
            self.cancel()
            self.state.set('正在安全退出，等待后台资源清理…')
        else:
            self.destroy()

    def open_output(self):
        if self.last_result:
            try:
                os.startfile(self.last_result['output_dir'])
            except OSError as exc:
                messagebox.showerror('打开目录', safe_error(exc), parent=self)
