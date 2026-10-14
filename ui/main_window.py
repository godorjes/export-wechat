from __future__ import annotations

import base64
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
from preview import open_export_preview
from wechat_data_dirs import _account_dirs, discover_wechat_data_dirs
from ui.chat_list import ChatList


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


class App(tk.Tk):
    def __init__(self, auto_load=True, app_directory=None, icon=None):
        super().__init__()
        self.title('微信聊天记录导出 V1.0')
        self.geometry('1160x760')
        self.minsize(980, 640)
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
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
        default = app_directory or (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1])
        self.out = tk.StringVar(value=str(default / 'exports'))
        self.source = tk.StringVar()
        self.source_status = tk.StringVar(value='数据源尚未加载')
        self.state = tk.StringVar(value='就绪')
        self.progress_text = tk.StringVar(value='选择会话后开始导出')
        self.format_vars = {f: tk.BooleanVar(value=True) for f in ('txt', 'md', 'json')}
        self.images = tk.BooleanVar(value=False)
        self.files = tk.BooleanVar(value=False)
        self.open_after = tk.BooleanVar(value=False)
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)
        header = ttk.Frame(self, padding=(18, 14, 18, 0))
        header.grid(row=0, column=0, sticky='ew')
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text='微信聊天记录导出', font=('Microsoft YaHei UI', 16, 'bold')).grid(row=0, column=0, sticky='w')
        ttk.Label(header, text='本地读取 · 本地导出', foreground='#666666').grid(row=0, column=1, sticky='e')
        ttk.Label(header, text='微信数据目录 / 账号').grid(row=1, column=0, sticky='w', pady=(12, 0))
        self.source_combo = ttk.Combobox(header, textvariable=self.source)
        self.source_combo.grid(row=1, column=1, sticky='ew', padx=10, pady=(12, 0))
        self.source_combo.bind('<<ComboboxSelected>>', lambda _: self.refresh())
        self.source_combo.bind('<Return>', lambda _: self.refresh())
        self.browse_btn = ttk.Button(header, text='浏览目录', command=self.browse_source)
        self.browse_btn.grid(row=1, column=2, pady=(12, 0))
        self.discover_btn = ttk.Button(header, text='重新检测', command=self.discover)
        self.discover_btn.grid(row=1, column=3, padx=(8, 0), pady=(12, 0))
        ttk.Label(header, textvariable=self.source_status, foreground='#666666', wraplength=1050).grid(row=2, column=0, columnspan=4, sticky='w', pady=(8, 8))
        split = ttk.Panedwindow(self, orient='horizontal')
        split.grid(row=1, column=0, sticky='nsew', padx=18, pady=(8, 14))
        self.chat_list = ChatList(split, self.update_buttons, self.refresh)
        split.add(self.chat_list, weight=3)
        right = ttk.Frame(split, padding=(14, 0, 0, 0))
        split.add(right, weight=2)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(5, weight=1)
        opts = ttk.LabelFrame(right, text='导出选项', padding=12)
        opts.grid(row=0, column=0, sticky='ew')
        opts.columnconfigure(0, weight=1)
        formats = ttk.Frame(opts)
        formats.grid(row=0, column=0, sticky='ew')
        for f, label in [('txt', 'TXT'), ('md', 'Markdown'), ('json', 'JSON')]:
            ttk.Checkbutton(formats, text=label, variable=self.format_vars[f]).pack(side='left', padx=(0, 14))
        media = ttk.Frame(opts)
        media.grid(row=1, column=0, sticky='ew', pady=10)
        ttk.Checkbutton(media, text='图片', variable=self.images).pack(side='left', padx=(0, 14))
        ttk.Checkbutton(media, text='普通文件附件', variable=self.files).pack(side='left')
        ttk.Label(opts, text='输出目录').grid(row=2, column=0, sticky='w')
        dest = ttk.Frame(opts)
        dest.grid(row=3, column=0, sticky='ew', pady=(4, 8))
        dest.columnconfigure(0, weight=1)
        ttk.Entry(dest, textvariable=self.out).grid(row=0, column=0, sticky='ew')
        ttk.Button(dest, text='选择', command=self.browse_output).grid(row=0, column=1, padx=(8, 0))
        ttk.Checkbutton(opts, text='完成后打开文件夹', variable=self.open_after).grid(row=4, column=0, sticky='w')
        actions = ttk.Frame(right)
        actions.grid(row=1, column=0, sticky='ew', pady=12)
        self.export_btn = ttk.Button(actions, text='导出所选会话', command=self.start_selected)
        self.export_btn.pack(side='left')
        self.all_btn = ttk.Button(actions, text='导出全部聊天', command=self.start_all)
        self.all_btn.pack(side='left', padx=8)
        self.cancel_btn = ttk.Button(actions, text='取消任务', command=self.cancel, state='disabled')
        self.cancel_btn.pack(side='right')
        ttk.Label(right, textvariable=self.state, font=('Microsoft YaHei UI', 11, 'bold')).grid(row=2, column=0, sticky='w')
        self.bar = ttk.Progressbar(right, mode='determinate')
        self.bar.grid(row=3, column=0, sticky='ew', pady=(6, 6))
        ttk.Label(right, textvariable=self.progress_text, wraplength=440).grid(row=4, column=0, sticky='w')
        logs = ttk.LabelFrame(right, text='进度与结果', padding=6)
        logs.grid(row=5, column=0, sticky='nsew', pady=(10, 10))
        logs.rowconfigure(0, weight=1)
        logs.columnconfigure(0, weight=1)
        self.log_text = tk.Text(logs, height=10, wrap='word', state='disabled', font=('Microsoft YaHei UI', 9))
        self.log_text.grid(row=0, column=0, sticky='nsew')
        scroll = ttk.Scrollbar(logs, command=self.log_text.yview)
        scroll.grid(row=0, column=1, sticky='ns')
        self.log_text.configure(yscrollcommand=scroll.set)
        result_buttons = ttk.Frame(right)
        result_buttons.grid(row=6, column=0, sticky='ew')
        self.open_btn = ttk.Button(result_buttons, text='打开结果文件夹', command=self.open_output, state='disabled')
        self.open_btn.pack(side='left')
        self.preview_btn = ttk.Button(result_buttons, text='预览导出结果', command=self.preview_results, state='disabled')
        self.preview_btn.pack(side='left', padx=8)
        ttk.Button(right, text='打开已有聊天记录', command=self.preview_existing).grid(row=7, column=0, sticky='w', pady=(8, 0))
        self.protocol('WM_DELETE_WINDOW', self.on_close)
        self.update_buttons()
        self._poll_id = self.after(60, self.poll)
        self._discover_id = None
        if auto_load:
            self._discover_id = self.after(0, self.discover)

    def destroy(self):
        for token in (self._poll_id, self._discover_id):
            if token:
                self.after_cancel(token)
        super().destroy()

    def log(self, text):
        self.log_text.configure(state='normal')
        self.log_text.insert('end', str(text) + '\n')
        # Keep live log bounded, even for very large batches.
        if int(self.log_text.index('end-1c').split('.')[0]) > 1200:
            self.log_text.delete('1.0', '201.0')
        self.log_text.see('end')
        self.log_text.configure(state='disabled')

    def update_buttons(self):
        ready = not self.busy and self.source_ready and bool(self.chat_list.model.chats)
        if hasattr(self, 'export_btn'):
            self.export_btn.configure(state='normal' if ready and self.chat_list.model.selected else 'disabled')
            self.all_btn.configure(state='normal' if ready else 'disabled')
        for w in (self.source_combo, self.browse_btn, self.discover_btn, self.chat_list.refresh_btn):
            w.configure(state='disabled' if self.busy else 'normal')
        if hasattr(self, 'cancel_btn'):
            self.cancel_btn.configure(state='normal' if self.busy and self.cancel_token and not self.cancel_token.cancelled else 'disabled')

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
                self.q.put(('error', (kind, safe_error(exc))))
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
                            self.state.set('任务失败，可重试')
                            self.log(result)
                            if task_kind == 'list':
                                self.source_ready = False
                                self.update_buttons()
                                self.source_status.set(process_status() + ' · 数据源读取失败，请检查所选目录/账号')
        except queue.Empty:
            pass
        if self.closing and not self.busy:
            self.destroy()
        else:
            self._poll_id = self.after(60, self.poll)

    def discover(self):
        if self.busy:
            return
        self.state.set('正在检测微信数据目录…')
        self.launch('sources', lambda: discover_sources(lambda m: self.q.put(('log', m))), self.sources_loaded)

    def sources_loaded(self, sources):
        self.sources = sources
        self.source_combo.configure(values=sources)
        if sources:
            self.source.set(sources[0])
            if process_status() == '微信正在运行':
                self.refresh()
            else:
                self.state.set('请登录微信后刷新列表')
                self.source_status.set(process_status() + ' · 已发现数据目录，登录后点击刷新')
        else:
            self.state.set('请选择微信数据目录')
            self.source_status.set(process_status() + ' · 未发现支持的数据库，可浏览选择账号或数据根目录')

    def browse_source(self):
        folder = filedialog.askdirectory(parent=self, title='选择微信数据根目录或账号目录')
        if folder:
            self.source.set(folder)
            self.refresh()

    def refresh(self):
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
        self.source_ready = False
        self.launch('list', lambda: list_chats(source, lambda m: self.q.put(('log', m))), self.list_loaded)

    def list_loaded(self, result):
        self.source_ready = True
        self.loaded_source = result.get('account_dir') or self.loaded_source
        if self.loaded_source:
            self.source.set(self.loaded_source)
        self.chat_list.replace(result['chats'])
        count = result.get('unresolved_message_tables', 0)
        source = result.get('account_dir') or self.loaded_source
        self.source_status.set(process_status() + f' · 已加载 {len(result["chats"])} 个会话 · 当前账号：{source}')
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

    def start_all(self):
        self.start_export(None)

    def start_export(self, usernames):
        if self.busy:
            return
        try:
            if usernames is not None and not usernames:
                raise ValueError('请先勾选至少一个会话。')
            options = ExportOptions(out_root=self.out.get().strip(),
                                    formats=tuple(f for f, v in self.format_vars.items() if v.get()),
                                    export_images=self.images.get(), export_files=self.files.get(),
                                    db_dir=self.loaded_source)
        except ValueError as exc:
            messagebox.showwarning('导出设置', str(exc), parent=self)
            return
        token = self.cancel_token = CancelToken()
        self.state.set('导出中…')
        self.bar.configure(value=0)
        self.last_result = None
        self.open_btn.configure(state='disabled')
        self.preview_btn.configure(state='disabled')
        self._open_after_task = self.open_after.get()
        self.launch('export', lambda: export_selected_chats(usernames, options,
                    lambda e: self.q.put(('progress', e)), token), self.export_done)

    def show_progress(self, event):
        if event.get('log'):
            self.log(event['log'])
        total = event.get('total', 0)
        done = event.get('completed', 0)
        self.bar.configure(maximum=max(1, total), value=done)
        stage = event['stage']
        if stage != '日志':
            self.state.set('正在取消，等待清理…' if self.cancel_token and self.cancel_token.cancelled else stage)
        self.progress_text.set(f"{event.get('name', '')}\n已完成 {done}/{total} 个会话 · 已写出 {event.get('messages', 0)} 条消息 · 失败 {event.get('failed', 0)}")

    def export_done(self, result):
        self.last_result = result
        labels = {'completed': '导出完成', 'completed_with_errors': '导出完成，部分会话失败', 'cancelled': '任务已取消', 'failed': '任务失败'}
        self.state.set(labels.get(result['state'], result['state']))
        self.log(f"成功 {result['exported']} · 无消息 {result['skipped_empty']} · 失败 {result['failed']} · 取消 {result['cancelled']} · {result['total_messages']} 条消息")
        for c in result['chats']:
            if c.get('error'):
                self.log(f"{c['name']}：{c['error']}")
        if result.get('error'):
            self.log(result['error'])
        if not result.get('sensitive_cache_cleanup') or result.get('partial_cleanup_error'):
            self.log('部分临时文件未完全清理，请查看任务汇总并关闭程序后重试清理。')
        self.log('结果目录：' + result['output_dir'])
        self.open_btn.configure(state='normal')
        self.preview_btn.configure(state='normal' if result['exported'] else 'disabled')
        if self._open_after_task and result['state'].startswith('completed'):
            self.open_output()

    def cancel(self):
        if self.cancel_token:
            self.cancel_token.cancel()
            self.state.set('正在取消，等待当前安全检查点和清理…')
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

    def preview_existing(self):
        folder = filedialog.askdirectory(parent=self, title='选择具体的聊天导出文件夹')
        if folder:
            open_export_preview(self, Path(folder))

    def preview_results(self):
        if not self.last_result:
            return
        chats = [c for c in self.last_result['chats'] if c['status'] == 'exported']
        dialog = tk.Toplevel(self)
        dialog.title('选择导出会话预览')
        dialog.geometry('640x380')
        dialog.rowconfigure(0, weight=1)
        dialog.columnconfigure(0, weight=1)
        tree = ttk.Treeview(dialog, columns=('name', 'username'), show='headings', selectmode='browse')
        tree.heading('name', text='会话名称')
        tree.heading('username', text='username')
        tree.grid(row=0, column=0, sticky='nsew', padx=12, pady=12)
        for c in chats:
            tree.insert('', 'end', iid=c['username'], values=(c['name'], c['username']))
        def preview():
            selection = tree.selection()
            if selection:
                chat = next(c for c in chats if c['username'] == selection[0])
                open_export_preview(self, Path(chat['output_dir']))
        ttk.Button(dialog, text='打开预览', command=preview).grid(row=1, column=0, pady=(0, 12))
        tree.bind('<Double-1>', lambda _: preview())
