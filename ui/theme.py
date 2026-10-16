"""Small native Tk widgets for the account-folded desktop layout."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, ttk
import uuid

BG = '#eff4f8'
WHITE = '#ffffff'
INK = '#19263d'
MUTED = '#8a9ab0'
LINE = '#e4ebf3'
GREEN = '#00bd84'
GREEN_DARK = '#078c63'
PALE = '#ecfcf5'
FIELD = '#f8fafc'
BODY_FONT = ('Microsoft YaHei UI', 11)
SMALL_FONT = ('Microsoft YaHei UI', 10)


def configure_theme(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    root.configure(background=BG)
    root.option_add('*Font', BODY_FONT)
    style.configure('.', font=BODY_FONT, background=WHITE, foreground=INK)
    style.configure('TFrame', background=WHITE)
    style.configure('TLabel', background=WHITE, foreground=INK)
    style.configure('TCheckbutton', background=WHITE, foreground='#53616e', padding=(0, 4))
    style.map('TCheckbutton', background=[('active', WHITE)], foreground=[('disabled', '#a4aeb5')])
    style.configure('TCombobox', padding=(2, 5), borderwidth=0, relief='flat',
                    fieldbackground=WHITE, background=WHITE, arrowcolor=MUTED,
                    lightcolor=WHITE, darkcolor=WHITE, bordercolor=WHITE, arrowsize=13)
    style.map('TCombobox', fieldbackground=[('disabled', '#f3f5f7'), ('readonly', WHITE)],
              selectbackground=[('readonly', WHITE)], selectforeground=[('readonly', INK)],
              foreground=[('disabled', '#a4aeb5'), ('readonly', INK)],
              background=[('active', WHITE), ('readonly', WHITE)])
    style.configure('TEntry', padding=5, borderwidth=0, fieldbackground=FIELD,
                    bordercolor=FIELD, lightcolor=FIELD, darkcolor=FIELD)
    style.configure('Vertical.TScrollbar', gripcount=0, width=9, arrowsize=8,
                    borderwidth=0, background='#dce5ee', troughcolor=WHITE,
                    bordercolor=WHITE, lightcolor=WHITE, darkcolor=WHITE)
    style.configure('Green.Horizontal.TProgressbar', background=GREEN, troughcolor='#e8eeea',
                    borderwidth=0, lightcolor=GREEN, darkcolor=GREEN, thickness=7)


def rounded_rect(canvas, x1, y1, x2, y2, radius=10, **kwargs):
    r = max(0, min(radius, (x2 - x1) / 2, (y2 - y1) / 2))
    return canvas.create_polygon(
        x1+r, y1, x2-r, y1, x2, y1, x2, y1+r,
        x2, y2-r, x2, y2, x2-r, y2, x1+r, y2,
        x1, y2, x1, y2-r, x1, y1+r, x1, y1,
        smooth=True, splinesteps=24, **kwargs)


def draw_icon(canvas, kind, x, y, size=18, color=MUTED, *, tags=()):
    def points(values):
        return [x+value*size/24 if i % 2 == 0 else y+value*size/24 for i, value in enumerate(values)]
    def line(*values):
        canvas.create_line(*points(values), fill=color, width=max(1.3, size/14),
                           capstyle='round', joinstyle='round', tags=tags)
    def box(a, b, c, d):
        canvas.create_rectangle(*points((a, b, c, d)), outline=color, width=max(1.3, size/14), tags=tags)
    if kind == 'wechat':
        for oval, tail in (((1, 2, 18, 16), (4, 13, 3, 19, 9, 15)),
                           ((9, 9, 24, 22), (19, 20, 23, 24, 22, 17))):
            canvas.create_oval(*points(oval), fill=color, outline='', tags=tags)
            canvas.create_polygon(*points(tail), fill=color, outline='', tags=tags)
        for dx, dy in ((7, 8), (12, 8), (14, 14), (19, 14)):
            canvas.create_oval(*points((dx-1, dy-1, dx+1, dy+1)), fill=GREEN_DARK, outline='', tags=tags)
    elif kind == 'folder':
        line(3, 7, 3, 19, 21, 19, 21, 7, 12, 7, 10, 4, 3, 4, 3, 7)
    elif kind == 'document':
        line(6, 3, 14, 3, 19, 8, 19, 21, 6, 21, 6, 3)
        line(14, 3, 14, 8, 19, 8)
    elif kind == 'image':
        box(3, 5, 21, 20)
        line(4, 17, 10, 11, 14, 15, 17, 12, 21, 17)
        canvas.create_oval(*points((15, 8, 17, 10)), fill=color, outline='', tags=tags)
    elif kind == 'download':
        line(12, 3, 12, 15, 8, 11)
        line(12, 15, 16, 11)
        line(4, 16, 4, 21, 20, 21, 20, 16)
    elif kind == 'refresh':
        canvas.create_arc(*points((3, 3, 21, 21)), start=30, extent=270, style='arc', outline=color,
                          width=max(1.3, size/14), tags=tags)
        line(19, 3, 20, 9, 14, 8)
    elif kind in {'info', 'help'}:
        canvas.create_oval(*points((3, 3, 21, 21)), outline=color, width=max(1.3, size/14), tags=tags)
        if kind == 'info':
            line(12, 11, 12, 17)
            canvas.create_oval(*points((11, 7, 13, 9)), fill=color, outline='', tags=tags)
        else:
            canvas.create_text(x+size/2, y+size/2, text='?', fill=color,
                               font=(BODY_FONT[0], max(8, int(size*.6)), 'bold'), tags=tags)
    elif kind == 'list':
        for dy, end in ((7, 21), (12, 21), (17, 15)):
            line(7, dy, end, dy)
            line(3, dy, 4, dy)


def icon_tile(parent, kind, color, tint, size=30):
    tile = tk.Canvas(parent, width=size, height=size, background=parent.cget('background'),
                     highlightthickness=0, borderwidth=0, takefocus=False)
    rounded_rect(tile, 1, 1, size-1, size-1, 9, fill=tint, outline='')
    draw_icon(tile, kind, (size-17)/2, (size-17)/2, 17, color)
    return tile


def pill(parent, text=None, variable=None, *, width=86, height=30,
         color=GREEN_DARK, fill=PALE, border='#b6efd9'):
    badge = RoundedCard(parent, width=width, height=height, inset=(8, 4), radius=height/2,
                        shadow=False, background=parent.cget('background'), fill=fill, border=border)
    badge.caption = label(badge.body, text, variable, small=True, bold=True, color=color, background=fill)
    badge.caption.configure(anchor='center')
    badge.caption.pack(fill='both', expand=True)
    if variable is not None:
        font = tkfont.Font(badge, font=badge.caption.cget('font'))
        def fit_caption(*_args):
            badge.configure(width=max(width, font.measure(str(variable.get()))+20))
        trace = variable.trace_add('write', fit_caption)
        def remove_trace(event):
            if event.widget == badge:
                variable.trace_remove('write', trace)
        badge.bind('<Destroy>', remove_trace, add='+')
        fit_caption()
    return badge


def heading_dot(parent):
    dot = tk.Canvas(parent, width=16, height=16, background=parent.cget('background'),
                    highlightthickness=0, borderwidth=0, takefocus=False)
    dot.create_oval(0, 0, 16, 16, fill='#e1faef', outline='')
    dot.create_oval(3, 3, 13, 13, fill=GREEN, outline='')
    return dot


def style_native_titlebar(root):
    """Colour the native caption where Windows supports per-window DWM colours."""
    if os.name != 'nt':
        return
    try:
        user = ctypes.WinDLL('user32')
        user.GetParent.argtypes = [ctypes.c_void_p]
        user.GetParent.restype = ctypes.c_void_p
        frame = user.GetParent(root.winfo_id()) or root.winfo_id()
        dwm = ctypes.WinDLL('dwmapi')
        dwm.DwmSetWindowAttribute.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        for attribute, rgb in ((35, 0x4F8E07), (36, 0xFFFFFF)):
            value = ctypes.c_uint(rgb)
            dwm.DwmSetWindowAttribute(frame, attribute, ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


class RoundedCard(tk.Canvas):
    def __init__(self, parent, *, height=550, width=350, radius=15, inset=(2, 12),
                 background=BG, border=LINE, shadow=True, fill=WHITE):
        super().__init__(parent, background=background, highlightthickness=0,
                         borderwidth=0, height=height, width=width, takefocus=False)
        self.radius, self.inset, self.border, self.shadow = radius, inset, border, shadow
        self.fill = fill
        self.body = tk.Frame(self, background=fill, borderwidth=0)
        self.window = self.create_window(inset[0], inset[1], window=self.body, anchor='nw')
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        w, h = event.width, event.height
        self.delete('surface')
        if self.shadow:
            rounded_rect(self, 1, 4, w-1, h-1, self.radius, fill='#e2e9f0', outline='', tags='surface')
        rounded_rect(self, 1, 1, w-2, h-3 if self.shadow else h-1, self.radius,
                     fill=self.fill, outline=self.border, width=1, tags=('surface', 'card_face'))
        self.tag_lower('surface')
        x, y = self.inset
        self.itemconfigure(self.window, width=max(1, w-2*x), height=max(1, h-2*y))

    def set_surface(self, fill, border):
        self.fill, self.border = fill, border
        self.body.configure(background=fill)
        self.itemconfigure('card_face', fill=fill, outline=border)


def label(parent, text=None, variable=None, *, small=False, bold=False, color=INK, background=WHITE, **kw):
    return tk.Label(parent, text=text, textvariable=variable, background=background, foreground=color,
                    font=(BODY_FONT[0], 10 if small else 11, 'bold' if bold else 'normal'),
                    borderwidth=0, anchor='w', **kw)


class RoundedButton(tk.Canvas):
    """Rounded surface with a real keyboard-focusable Tk button inside."""
    def __init__(self, parent, text, command=None, *, primary=False, height=40,
                 width=None, state='normal', small=False, icon=None, color=None, icon_color=None):
        font = (BODY_FONT[0], 10 if small else 11, 'bold' if primary else 'normal')
        width = width or tkfont.Font(font=font).measure(text) + (54 if icon else 32)
        super().__init__(parent, background=parent.cget('background'), width=width, height=height,
                         borderwidth=0, highlightthickness=0, takefocus=False)
        self.primary = primary
        self.icon, self.text_color = icon, color
        self.icon_color = icon_color
        self.hover = False
        self.button = tk.Button(self, text=text, command=command, font=font, relief='flat',
                                borderwidth=0, highlightthickness=0, cursor='hand2',
                                padx=0, pady=0, state=state, takefocus=True)
        self._label_font = tkfont.Font(self, font=font)
        self.window = self.create_window(34 if icon else 8, 5, window=self.button, anchor='nw')
        self.bind('<Configure>', lambda _: self._draw())
        for widget in (self, self.button):
            widget.bind('<Enter>', lambda _: self._hover(True))
            widget.bind('<Leave>', lambda _: self._hover(False))
        self.bind('<ButtonRelease-1>', lambda _: self.invoke())
        self.button.bind('<FocusIn>', lambda _: self._draw())
        self.button.bind('<FocusOut>', lambda _: self._draw())
        self._draw()

    def _hover(self, hover):
        self.hover = hover
        self._draw()

    def _draw(self):
        disabled = str(self.button.cget('state')) == 'disabled'
        bg = ('#dff3ec' if disabled else GREEN_DARK if self.hover else GREEN) if self.primary else (FIELD if self.hover else WHITE)
        fg = WHITE if self.primary else self.text_color or INK
        border = bg if self.primary else LINE
        if self.button.focus_get() == self.button:
            border = '#87aaff'
        self.button.configure(background=bg, activebackground=GREEN_DARK if self.primary else '#f8fafb',
                              foreground=fg, activeforeground=fg, disabledforeground='#91a5b2' if self.primary else '#a4aeb5')
        self.delete('surface')
        w, h = max(self.winfo_width(), int(self.cget('width'))), max(self.winfo_height(), int(self.cget('height')))
        rounded_rect(self, 1, 1, w-1, h-1, 9, fill=bg, outline=border, width=1, tags='surface')
        if self.icon:
            text_width = min(self._label_font.measure(self.button.cget('text'))+2, max(1, w-48))
            icon_x = max(12, (w-text_width-24)/2)
            draw_icon(self, self.icon, icon_x, (h-16)/2, 16,
                      '#91a5b2' if disabled else self.icon_color or fg, tags='surface')
            self.coords(self.window, icon_x+24, 5)
            self.itemconfigure(self.window, width=text_width, height=max(1, h-10))
        else:
            self.itemconfigure(self.window, width=max(1, w-16), height=max(1, h-10))
        self.tag_lower('surface')

    def invoke(self):
        return self.button.invoke()

    def configure(self, cnf=None, **kwargs):
        if not hasattr(self, 'button'):
            return super().configure(cnf, **kwargs)
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
            cnf = None
        for key in ('state', 'text', 'command'):
            if key in kwargs:
                self.button.configure(**{key: kwargs.pop(key)})
        result = super().configure(cnf, **kwargs) if cnf or kwargs else None
        self._draw()
        return result

    config = configure

    def cget(self, key):
        if key in ('state', 'text', 'command') and hasattr(self, 'button'):
            return self.button.cget(key)
        return super().cget(key)


def link_button(parent, text, command=None, *, state='normal', color=GREEN_DARK):
    return tk.Button(parent, text=text, command=command, state=state, relief='flat', borderwidth=0,
                     font=SMALL_FONT, background=parent.cget('background'), foreground=color,
                     activebackground=parent.cget('background'), activeforeground=GREEN,
                     disabledforeground='#a4aeb5', cursor='hand2', highlightthickness=0, padx=0, pady=4)


def combo_field(parent, variable, values, *, width=24, readonly=True, variables=None, labels=None):
    from ui.dropdown import Dropdown
    control = Dropdown(parent, variable, values, width=width, variables=variables, labels=labels,
                       state='readonly' if readonly else 'normal')
    return control, control


class ScrollFrame(tk.Frame):
    def __init__(self, parent):
        super().__init__(parent, background=WHITE)
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, background=WHITE, borderwidth=0, highlightthickness=0, width=1, height=1)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        self.scroll = ttk.Scrollbar(self, command=self.canvas.yview)
        self.scroll.grid(row=0, column=1, sticky='ns')
        self._scroll_visible = True
        self._scroll_layout_id = None
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.body = tk.Frame(self.canvas, background=WHITE)
        self.window = self.canvas.create_window(0, 0, window=self.body, anchor='nw')
        self.canvas.bind('<Configure>', self._resize)
        self.body.bind('<Configure>', self._content_resize)
        self.canvas.bind('<MouseWheel>', self._wheel)

    def _resize(self, event):
        self.canvas.itemconfigure(self.window, width=event.width)
        self._content_resize()

    def _content_resize(self, _event=None):
        self.canvas.configure(scrollregion=(0, 0, self.canvas.winfo_width(), self.body.winfo_reqheight()))
        # Changing grid membership inside a canvas Configure callback can leave
        # the canvas unmapped on Windows. Wait until the current layout settles.
        if self._scroll_layout_id is None:
            self._scroll_layout_id = self.after_idle(self._layout_scrollbar)

    def _layout_scrollbar(self):
        self._scroll_layout_id = None
        visible = self.body.winfo_reqheight() > self.canvas.winfo_height()
        if visible != self._scroll_visible:
            self._scroll_visible = visible
            if visible:
                self.scroll.grid()
            else:
                self.scroll.grid_remove()
        if not visible:
            self.canvas.yview_moveto(0)

    def destroy(self):
        if self._scroll_layout_id is not None:
            self.after_cancel(self._scroll_layout_id)
            self._scroll_layout_id = None
        super().destroy()

    def _wheel(self, event):
        if self.body.winfo_reqheight() > self.canvas.winfo_height():
            self.canvas.yview_scroll(-int(event.delta / 120), 'units')
        return 'break'

    def _focus_into_view(self, event):
        # Tk traversal knows mapped children, but not clipping by the canvas.
        total = self.body.winfo_reqheight()
        height = self.canvas.winfo_height()
        if total <= height:
            return
        y = event.widget.winfo_rooty() - self.body.winfo_rooty()
        bottom = y + event.widget.winfo_height()
        top = self.canvas.canvasy(0)
        if y < top:
            self.canvas.yview_moveto(max(0, y-6) / total)
        elif bottom > top+height:
            self.canvas.yview_moveto((bottom-height+6) / total)

    def bind_wheel(self):
        def bind_children(widget):
            widget.bind('<MouseWheel>', self._wheel)
            widget.bind('<FocusIn>', self._focus_into_view, add='+')
            for child in widget.winfo_children():
                bind_children(child)
        bind_children(self.body)


def destination_folders():
    """Read Windows' actual folders, including user redirects; never create them."""
    ids = {
        '下载文件夹（推荐）': ('374de290-123f-4565-9164-39c4925e467b', 'Downloads'),
        '桌面': ('b4bfcc3a-db2c-424c-b029-7fe99a87c641', 'Desktop'),
        '文档文件夹': ('fdd39ad0-238f-46af-adb4-6c85480369c7', 'Documents'),
    }
    folders = {}
    for name, (folder_id, fallback) in ids.items():
        folder = Path.home() / fallback
        if os.name == 'nt':
            pointer = ctypes.c_void_p()
            try:
                # SHGetKnownFolderPath / CoTaskMemFree, documented by Microsoft:
                # https://learn.microsoft.com/windows/win32/api/shlobj_core/nf-shlobj_core-shgetknownfolderpath
                shell = ctypes.WinDLL('shell32')
                ole = ctypes.WinDLL('ole32')
                get_path = shell.SHGetKnownFolderPath
                get_path.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p)]
                get_path.restype = ctypes.c_long
                ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
                guid = (ctypes.c_ubyte * 16).from_buffer_copy(uuid.UUID(folder_id).bytes_le)
                if get_path(ctypes.byref(guid), 0, None, ctypes.byref(pointer)) == 0 and pointer.value:
                    folder = Path(ctypes.wstring_at(pointer.value))
            except (AttributeError, OSError):
                pass
            finally:
                if pointer.value:
                    ole.CoTaskMemFree(pointer)
        folders[name] = str(folder / '微信聊天记录导出')
    return folders
