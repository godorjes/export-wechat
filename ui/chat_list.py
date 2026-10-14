from datetime import datetime
import tkinter as tk
from tkinter import ttk

from chat_list_service import ChatSelection


class ChatList(ttk.Frame):
    def __init__(self, parent, on_change=None, on_refresh=None):
        super().__init__(parent, padding=(0, 0, 12, 0))
        self.model = ChatSelection()
        self.on_change = on_change
        self.category = tk.StringVar(value='全部')
        self.query = tk.StringVar()
        self.count = tk.StringVar(value='已选 0 个会话')
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky='ew')
        ttk.Label(top, text='好友与群聊', font=('Microsoft YaHei UI', 12, 'bold')).pack(side='left')
        self.refresh_btn = ttk.Button(top, text='刷新列表', command=on_refresh)
        self.refresh_btn.pack(side='right')
        categories = ttk.Frame(self)
        categories.grid(row=1, column=0, sticky='ew', pady=(12, 8))
        for c in ('全部', '好友', '群聊'):
            ttk.Radiobutton(categories, text=c, variable=self.category, value=c).pack(side='left', padx=(0, 12))
        search = ttk.Frame(self)
        search.grid(row=2, column=0, sticky='ew', pady=(0, 8))
        search.columnconfigure(1, weight=1)
        ttk.Label(search, text='搜索').grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(search, textvariable=self.query).grid(row=0, column=1, sticky='ew')
        body = ttk.Frame(self)
        body.grid(row=3, column=0, sticky='nsew')
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.tree = ttk.Treeview(body, columns=('check', 'name', 'kind', 'last'), show='headings', selectmode='browse')
        for key, title, width in [('check', '选择', 46), ('name', '名称', 205), ('kind', '类型', 58), ('last', '最近消息', 140)]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=width if key != 'name' else 120, stretch=key == 'name')
        self.tree.grid(row=0, column=0, sticky='nsew')
        y = ttk.Scrollbar(body, orient='vertical', command=self.tree.yview)
        y.grid(row=0, column=1, sticky='ns')
        x = ttk.Scrollbar(body, orient='horizontal', command=self.tree.xview)
        x.grid(row=1, column=0, sticky='ew')
        self.tree.configure(yscrollcommand=y.set, xscrollcommand=x.set)
        self.tree.bind('<Button-1>', self._click)
        self.tree.bind('<space>', self._space)
        self.tree.bind('<Double-1>', self._space)
        footer = ttk.Frame(self)
        footer.grid(row=4, column=0, sticky='ew', pady=(10, 0))
        ttk.Button(footer, text='全选当前结果', command=self.select_visible).pack(side='left')
        ttk.Button(footer, text='取消全部选择', command=self.clear).pack(side='left', padx=6)
        ttk.Label(self, textvariable=self.count).grid(row=5, column=0, sticky='w', pady=(8, 0))
        self.empty = tk.StringVar(value='正在准备列表…')
        ttk.Label(self, textvariable=self.empty, foreground='#666666').grid(row=6, column=0, sticky='w', pady=(4, 0))
        self.category.trace_add('write', lambda *_: self.render())
        self.query.trace_add('write', lambda *_: self.render())

    def replace(self, chats):
        self.model.replace(chats)
        self.render()

    def render(self):
        focus = self.tree.focus()
        self.tree.delete(*self.tree.get_children())
        visible = self.model.filter(self.category.get(), self.query.get())
        for c in visible:
            last = c.get('last_time')
            try:
                date = datetime.fromtimestamp(int(last)).strftime('%Y-%m-%d %H:%M') if last else '未知'
            except (ValueError, OSError, OverflowError):
                date = '未知'
            username = c['username']
            self.tree.insert('', 'end', iid=username, values=(
                '☑' if username in self.model.selected else '☐', c['name'],
                '群聊' if c.get('is_group') else '好友', date))
        if focus in self.tree.get_children():
            self.tree.focus(focus)
            self.tree.selection_set(focus)
        self.count.set(f'已选 {len(self.model.selected)} 个会话 · 当前显示 {len(visible)} / {len(self.model.chats)}')
        self.empty.set('没有匹配的会话。' if not visible and self.model.chats else
                       '没有可可靠识别的本地会话。' if not visible else '点击选择列勾选；空格键也可切换选择。')
        if self.on_change:
            self.on_change()

    def _click(self, event):
        if self.tree.identify_column(event.x) == '#1':
            username = self.tree.identify_row(event.y)
            self.model.toggle(username)
            self.render()
            return 'break'

    def _space(self, _event=None):
        self.model.toggle(self.tree.focus())
        self.render()
        return 'break'

    def select_visible(self):
        self.model.select_visible(self.model.filter(self.category.get(), self.query.get()))
        self.render()

    def clear(self):
        self.model.clear()
        self.render()
