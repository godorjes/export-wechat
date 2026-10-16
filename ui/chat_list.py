from datetime import datetime
import math
import tkinter as tk
from tkinter import font as tkfont, ttk

from chat_list_service import ChatSelection
from ui.theme import (WHITE, INK, MUTED, LINE, GREEN, GREEN_DARK, PALE, FIELD, BODY_FONT,
                      RoundedCard, combo_field, label, link_button, rounded_rect, pill, heading_dot, draw_icon)


class ChatList(tk.Frame):
    """Metadata rows drawn only for the viewport, with stable username selection."""
    def __init__(self, parent, on_change=None, on_refresh=None):
        super().__init__(parent, background=WHITE)
        self.model = ChatSelection()
        self.on_change = on_change
        self.enabled = True
        self.visible = []
        self.focused = None
        self.hovered = None
        self.category = tk.StringVar(value='全部')
        self.query = tk.StringVar()
        self.count = tk.StringVar(value='已选择 0 个聊天')
        self.selection_note = tk.StringVar(value='已选择 0 个')
        self.list_count = tk.StringVar(value='当前显示 0 个聊天')
        self.source_note = tk.StringVar(value='本地聊天')
        self.name_font = tkfont.Font(font=(BODY_FONT[0], 11, 'bold'))
        self.small_font = tkfont.Font(font=(BODY_FONT[0], 10))
        self.tiny_font = tkfont.Font(font=(BODY_FONT[0], 9))
        self.row_height = max(76, self.name_font.metrics('linespace') + self.small_font.metrics('linespace') + 25)
        self._draw_id = None
        self.columnconfigure(0, weight=1)
        self.rowconfigure(3, weight=1)
        top = tk.Frame(self, background=WHITE)
        top.grid(row=0, column=0, sticky='ew', padx=18, pady=(4, 12))
        heading_dot(top).pack(side='left', padx=(0, 7))
        tk.Label(top, text='选择要导出的聊天', font=(BODY_FONT[0], 12, 'bold'),
                 background=WHITE, foreground=INK, borderwidth=0).pack(side='left')
        pill(top, variable=self.selection_note, width=100, height=30).pack(side='right')
        filters = tk.Frame(self, background=WHITE)
        filters.grid(row=1, column=0, sticky='ew', padx=18, pady=(0, 12))
        filters.columnconfigure(1, weight=1)
        category_field, self.category_combo = combo_field(filters, self.category, ('全部', '好友', '群聊'), width=10)
        category_field.grid(row=0, column=0, sticky='ew', padx=(0, 10))
        search = RoundedCard(filters, height=42, width=100, radius=9, inset=(32, 6), shadow=False, background=WHITE)
        search.grid(row=0, column=1, sticky='ew')
        search.create_oval(12, 12, 24, 24, outline='#8d98a2', width=1.5)
        search.create_line(22, 23, 28, 29, fill='#8d98a2', width=1.5)
        self.search_entry = tk.Entry(search.body, textvariable=self.query, relief='flat', borderwidth=0,
                                     background=WHITE, foreground=INK, insertbackground=GREEN,
                                     font=BODY_FONT, disabledbackground=WHITE)
        self.search_entry.pack(fill='both', expand=True)
        self.placeholder = label(search.body, '搜索微信好友、群聊或备注…', color=MUTED)
        self.placeholder.place(x=2, rely=.5, anchor='w')
        self.placeholder.bind('<Button-1>', lambda _: self.search_entry.focus_set())
        self.search_entry.bind('<FocusIn>', lambda _: self.placeholder.place_forget())
        self.search_entry.bind('<FocusOut>', lambda _: self._placeholder())
        strip = RoundedCard(self, height=42, width=1, radius=9, inset=(12, 4),
                              shadow=False, background=WHITE, fill=FIELD)
        strip.grid(row=2, column=0, sticky='ew', padx=18, pady=(0, 8))
        list_icon = tk.Canvas(strip.body, width=17, height=18, background=FIELD, highlightthickness=0, takefocus=False)
        list_icon.pack(side='left', padx=(0, 7))
        draw_icon(list_icon, 'list', 0, 1, 17, MUTED)
        label(strip.body, variable=self.list_count, small=True, bold=True, color='#74869f', background=FIELD).pack(side='left')
        self.select_all_btn = link_button(strip.body, '全选当前列表', self.select_visible)
        self.select_all_btn.pack(side='right')
        body = tk.Frame(self, background=WHITE)
        body.grid(row=3, column=0, sticky='nsew', padx=(4, 4))
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(body, background=WHITE, highlightthickness=0, borderwidth=0,
                                height=300, width=1, takefocus=True, yscrollincrement=20)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scrollbar = ttk.Scrollbar(body, command=self.canvas.yview)
        self.scrollbar.grid(row=0, column=1, sticky='ns')
        self.canvas.configure(yscrollcommand=self._scrolled)
        self.canvas.bind('<Configure>', lambda _: self._queue_draw())
        self.canvas.bind('<Button-1>', self._click)
        self.canvas.bind('<Motion>', self._motion)
        self.canvas.bind('<Leave>', lambda _: self._hover(None))
        self.canvas.bind('<MouseWheel>', self._wheel)
        self.canvas.bind('<space>', self._space)
        for key in ('Up', 'Down', 'Home', 'End', 'Prior', 'Next'):
            self.canvas.bind('<' + key + '>', lambda event, key=key: self._navigate(key))
        self.canvas.bind('<Control-a>', lambda _: self.select_visible() or 'break')
        self.canvas.bind('<FocusIn>', lambda _: self._queue_draw())
        self.canvas.bind('<FocusOut>', lambda _: self._queue_draw())
        footer = tk.Frame(self, background=WHITE)
        footer.grid(row=4, column=0, sticky='ew', padx=18, pady=(0, 2))
        tk.Frame(footer, background=LINE, height=1).pack(fill='x', pady=(0, 10))
        row = tk.Frame(footer, background=WHITE)
        row.pack(fill='x')
        label(row, '●', small=True, color=GREEN).pack(side='left', padx=(0, 7))
        label(row, variable=self.count, small=True, color=INK).pack(side='left')
        self.refresh_btn = link_button(row, '刷新列表', on_refresh, color=INK)
        self.refresh_btn.pack(side='right')
        label(row, '│', small=True, color='#c4cfdd').pack(side='right', padx=10)
        self.clear_btn = link_button(row, '清空选择', self.clear, color=INK)
        self.clear_btn.pack(side='right')
        self.category.trace_add('write', lambda *_: self.render())
        self.query.trace_add('write', lambda *_: self.render())
        self.render()

    def destroy(self):
        if self._draw_id:
            self.after_cancel(self._draw_id)
            self._draw_id = None
        super().destroy()

    def _placeholder(self):
        if not self.query.get() and self.search_entry.focus_get() != self.search_entry:
            self.placeholder.place(x=2, rely=.5, anchor='w')
        else:
            self.placeholder.place_forget()

    def replace(self, chats):
        self.model.replace(chats)
        self.render()

    def set_enabled(self, enabled):
        self.enabled = enabled
        state = 'normal' if enabled else 'disabled'
        self.category_combo.configure(state='readonly' if enabled else 'disabled')
        self.search_entry.configure(state=state)
        self.refresh_btn.configure(state=state)
        self.clear_btn.configure(state=state)
        self.select_all_btn.configure(state=state if self.visible else 'disabled')

    def render(self):
        previous = [c['username'] for c in self.visible]
        self.visible = self.model.filter(self.category.get(), self.query.get())
        current = [c['username'] for c in self.visible]
        if self.focused not in current:
            self.focused = current[0] if current else None
        self.canvas.configure(scrollregion=(0, 0, max(1, self.canvas.winfo_width()), max(1, len(current)*self.row_height)))
        if current != previous:
            self.canvas.yview_moveto(0)
        selected = len(self.model.selected)
        self.selection_note.set(f'已选择 {selected} 个')
        self.count.set(f'已选择 {selected} 个聊天')
        self.list_count.set(f'当前显示 {len(current)} 个聊天')
        all_on = bool(current) and all(x in self.model.selected for x in current)
        self.select_all_btn.configure(text='取消全选' if all_on else '全选当前列表',
                                      state='normal' if self.enabled and current else 'disabled')
        self._placeholder()
        self._queue_draw()
        if self.on_change:
            self.on_change()

    def _queue_draw(self):
        if self._draw_id is None:
            self._draw_id = self.after_idle(self._draw)

    def _scrolled(self, first, last):
        self.scrollbar.set(first, last)
        self._queue_draw()

    def _fit(self, text, width, font):
        text = str(text).replace('\n', ' ').replace('\r', ' ')
        if width <= 0:
            return ''
        if font.measure(text) <= width:
            return text
        lo, hi = 0, len(text)
        while lo < hi:
            mid = (lo+hi+1)//2
            if font.measure(text[:mid] + '…') <= width:
                lo = mid
            else:
                hi = mid-1
        return text[:lo] + '…'

    @staticmethod
    def _date(value):
        try:
            date = datetime.fromtimestamp(int(value))
            now = datetime.now()
            if date.date() == now.date():
                return date.strftime('%H:%M')
            return date.strftime('%m-%d' if date.year == now.year else '%Y-%m-%d')
        except (TypeError, ValueError, OSError, OverflowError):
            return '时间未知'

    def _draw(self):
        self._draw_id = None
        self.canvas.delete('row')
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if not self.visible:
            title = '没有找到聊天' if self.model.chats else '聊天列表尚未加载'
            note = '试试换个关键词或筛选条件' if self.model.chats else '登录微信后点击右上角检测微信账号'
            self.canvas.create_text(w/2, max(75, h/2-12), text=title, font=self.name_font, fill=MUTED, tags='row')
            self.canvas.create_text(w/2, max(102, h/2+18), text=note, width=max(100, w-40),
                                    font=self.small_font, fill='#a0aab4', tags='row')
            return
        start = max(0, int(self.canvas.canvasy(0)//self.row_height))
        end = min(len(self.visible), start + math.ceil(h/self.row_height) + 2)
        for index in range(start, end):
            c = self.visible[index]
            username = c['username']
            top = index*self.row_height
            bottom = top+self.row_height
            selected = username in self.model.selected
            focus = self.focused == username and self.canvas.focus_get() == self.canvas
            rounded_rect(self.canvas, 3, top+1, w-3, bottom-1, 9,
                         fill=PALE if selected else '#f7fafc' if self.hovered == username else WHITE,
                         outline='#94e0c6' if focus else '', tags='row')
            self.canvas.create_line(0, bottom-1, w, bottom-1, fill='#edf2f7', tags='row')
            cy = (top+bottom)/2
            rounded_rect(self.canvas, 16, cy-9, 34, cy+9, 4,
                         fill=GREEN if selected else WHITE, outline=GREEN if selected else '#cfdae7', tags='row')
            if selected:
                self.canvas.create_line(20, cy, 24, cy+4, 30, cy-4, width=2, fill=WHITE, tags='row')
            palette = (('#daf9fb', '#087f98'), ('#d6fae8', '#17694e'), ('#dff2ff', '#1d78a7'),
                       ('#f0e1ff', '#843db4'), ('#e3e6ff', '#4b4eaf'), ('#ffebd0', '#ac5b1b'))
            color, avatar_ink = palette[sum(ord(char) for char in username) % len(palette)]
            rounded_rect(self.canvas, 52, cy-23, 98, cy+23, 12, fill=color, outline='', tags='row')
            name = str(c.get('name') or username)
            self.canvas.create_text(75, cy, text=name[:1], fill=avatar_ink, font=(BODY_FONT[0], 15, 'bold'), tags='row')
            date = self._date(c.get('last_time'))
            date_w = self.tiny_font.measure(date)
            rounded_rect(self.canvas, w-date_w-34, cy-22, w-17, cy, 6,
                         fill='#f7f9fc', outline='#edf1f6', tags='row')
            self.canvas.create_text(w-25, cy-11, anchor='e', text=date, fill='#899bb4', font=self.tiny_font, tags='row')
            kind = '群聊' if c.get('is_group') else '好友'
            badge_w = self.tiny_font.measure(kind) + 12
            name_room = max(30, w-118-date_w-34-badge_w-20)
            name = self._fit(name, name_room, self.name_font)
            self.canvas.create_text(116, cy-11, text=name, anchor='w', fill=INK, font=self.name_font, tags='row')
            badge_x = 116+self.name_font.measure(name)+8
            rounded_rect(self.canvas, badge_x, cy-20, badge_x+badge_w, cy-2, 4,
                         fill='#e3f7ee' if selected else '#f0f3f7', outline='', tags='row')
            self.canvas.create_text(badge_x+badge_w/2, cy-11, text=kind,
                                    fill='#438a70' if selected else '#8a9ab0', font=self.tiny_font, tags='row')
            nick = c.get('nick_name')
            subtitle = f'昵称：{nick}' if nick and nick != c.get('name') else username
            self.canvas.create_text(116, cy+14, text=self._fit(subtitle, max(30, w-133), self.small_font),
                                    anchor='w', fill='#91a1b8', font=self.small_font, tags='row')

    def _row_at(self, y):
        index = int(self.canvas.canvasy(y)//self.row_height)
        return self.visible[index]['username'] if 0 <= index < len(self.visible) else None

    def _click(self, event):
        if self.enabled:
            username = self._row_at(event.y)
            if username:
                self.focused = username
                self.canvas.focus_set()
                self.model.toggle(username)
                self.render()
        # Allow the toplevel's outside-click handler to dismiss account settings.

    def _motion(self, event):
        self._hover(self._row_at(event.y))

    def _hover(self, username):
        if self.hovered != username:
            self.hovered = username
            self._queue_draw()

    def _wheel(self, event):
        self.canvas.yview_scroll(-int(event.delta/120)*3, 'units')
        return 'break'

    def _space(self, _event=None):
        if self.enabled:
            self.model.toggle(self.focused)
            self.render()
        return 'break'

    def _navigate(self, key):
        if not self.visible:
            return 'break'
        ids = [c['username'] for c in self.visible]
        index = ids.index(self.focused) if self.focused in ids else 0
        page = max(1, self.canvas.winfo_height()//self.row_height)
        index = {'Home': 0, 'End': len(ids)-1, 'Up': index-1, 'Down': index+1,
                 'Prior': index-page, 'Next': index+page}[key]
        index = min(max(index, 0), len(ids)-1)
        self.focused = ids[index]
        y = index*self.row_height
        top = self.canvas.canvasy(0)
        if y < top:
            self.canvas.yview_moveto(y/(len(ids)*self.row_height))
        elif y+self.row_height > top+self.canvas.winfo_height():
            self.canvas.yview_moveto((y+self.row_height-self.canvas.winfo_height())/(len(ids)*self.row_height))
        self._queue_draw()
        return 'break'

    def select_visible(self):
        if self.enabled:
            ids = {c['username'] for c in self.visible}
            if ids and ids <= self.model.selected:
                self.model.selected.difference_update(ids)
            else:
                self.model.select_visible(self.visible)
            self.render()

    def clear(self):
        if self.enabled:
            self.model.clear()
            self.render()
