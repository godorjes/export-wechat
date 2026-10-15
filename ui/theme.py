"""Small native Tk widgets for the account-folded desktop layout."""
from __future__ import annotations

import ctypes
import os
from pathlib import Path
import tkinter as tk
from tkinter import font as tkfont, ttk
import uuid

BG = '#f6f8fa'
WHITE = '#ffffff'
INK = '#1c2731'
MUTED = '#7a8692'
LINE = '#e5eaf0'
GREEN = '#13a565'
GREEN_DARK = '#07854e'
PALE = '#effaf4'
BODY_FONT = ('Microsoft YaHei UI', 10)
SMALL_FONT = ('Microsoft YaHei UI', 9)


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
    style.configure('TEntry', padding=5, borderwidth=0, fieldbackground=WHITE,
                    bordercolor=WHITE, lightcolor=WHITE, darkcolor=WHITE)
    style.configure('Vertical.TScrollbar', gripcount=0, width=9, arrowsize=8,
                    borderwidth=0, background='#dce3e8', troughcolor=WHITE,
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


class RoundedCard(tk.Canvas):
    def __init__(self, parent, *, height=550, width=350, radius=15, inset=(2, 12),
                 background=BG, border=LINE, shadow=True):
        super().__init__(parent, background=background, highlightthickness=0,
                         borderwidth=0, height=height, width=width)
        self.radius, self.inset, self.border, self.shadow = radius, inset, border, shadow
        self.body = tk.Frame(self, background=WHITE, borderwidth=0)
        self.window = self.create_window(inset[0], inset[1], window=self.body, anchor='nw')
        self.bind('<Configure>', self._resize)

    def _resize(self, event):
        w, h = event.width, event.height
        self.delete('surface')
        if self.shadow:
            rounded_rect(self, 1, 3, w-1, h-1, self.radius, fill='#eaf0ed', outline='', tags='surface')
        rounded_rect(self, 1, 1, w-2, h-3 if self.shadow else h-1, self.radius,
                     fill=WHITE, outline=self.border, width=1, tags='surface')
        self.tag_lower('surface')
        x, y = self.inset
        self.itemconfigure(self.window, width=max(1, w-2*x), height=max(1, h-2*y))


def label(parent, text=None, variable=None, *, small=False, bold=False, color=INK, background=WHITE, **kw):
    return tk.Label(parent, text=text, textvariable=variable, background=background, foreground=color,
                    font=(BODY_FONT[0], 9 if small else 10, 'bold' if bold else 'normal'),
                    borderwidth=0, anchor='w', **kw)


class RoundedButton(tk.Canvas):
    """Rounded surface with a real keyboard-focusable Tk button inside."""
    def __init__(self, parent, text, command=None, *, primary=False, height=40,
                 width=None, state='normal', small=False):
        font = (BODY_FONT[0], 9 if small else 10, 'bold' if primary else 'normal')
        width = width or tkfont.Font(font=font).measure(text) + 32
        super().__init__(parent, background=parent.cget('background'), width=width, height=height,
                         borderwidth=0, highlightthickness=0, takefocus=False)
        self.primary = primary
        self.hover = False
        self.button = tk.Button(self, text=text, command=command, font=font, relief='flat',
                                borderwidth=0, highlightthickness=0, cursor='hand2',
                                padx=0, pady=0, state=state, takefocus=True)
        self.window = self.create_window(8, 5, window=self.button, anchor='nw')
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
        bg = ('#cde7da' if disabled else GREEN_DARK if self.hover else GREEN) if self.primary else ('#f8fafb' if self.hover else WHITE)
        fg = WHITE if self.primary else INK
        border = bg if self.primary else LINE
        if self.button.focus_get() == self.button:
            border = '#94e0b8'
        self.button.configure(background=bg, activebackground=GREEN_DARK if self.primary else '#f8fafb',
                              foreground=fg, activeforeground=fg, disabledforeground=WHITE if self.primary else '#a4aeb5')
        self.delete('surface')
        w, h = max(self.winfo_width(), int(self.cget('width'))), max(self.winfo_height(), int(self.cget('height')))
        rounded_rect(self, 1, 1, w-1, h-1, 9, fill=bg, outline=border, width=1, tags='surface')
        self.tag_lower('surface')
        self.itemconfigure(self.window, width=max(1, w-16), height=max(1, h-10))

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


def combo_field(parent, variable, values, *, width=24, readonly=True):
    shell = RoundedCard(parent, height=42, radius=9, inset=(9, 5), shadow=False,
                        background=parent.cget('background'), width=width*9)
    control = ttk.Combobox(shell.body, textvariable=variable, values=values, width=width,
                           state='readonly' if readonly else 'normal')
    control.pack(fill='both', expand=True)
    return shell, control


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
