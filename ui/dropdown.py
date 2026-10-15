"""Matching single and multi-select dropdowns for the native desktop UI."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
import ctypes
from ctypes import wintypes
import os

from ui.theme import WHITE, INK, MUTED, LINE, GREEN, GREEN_DARK, PALE, BODY_FONT, rounded_rect


def monitor_work_area(widget):
    if os.name == 'nt':
        class MonitorInfo(ctypes.Structure):
            _fields_ = [('size', wintypes.DWORD), ('monitor', wintypes.RECT),
                        ('work', wintypes.RECT), ('flags', wintypes.DWORD)]
        try:
            user = ctypes.WinDLL('user32', use_last_error=True)
            user.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
            user.MonitorFromPoint.restype = wintypes.HANDLE
            user.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MonitorInfo)]
            user.GetMonitorInfoW.restype = wintypes.BOOL
            point = wintypes.POINT(widget.winfo_rootx()+widget.winfo_width()//2,
                                  widget.winfo_rooty()+widget.winfo_height()//2)
            monitor = user.MonitorFromPoint(point, 2)
            info = MonitorInfo()
            info.size = ctypes.sizeof(info)
            if monitor and user.GetMonitorInfoW(monitor, ctypes.byref(info)):
                return info.work.left, info.work.top, info.work.right, info.work.bottom
        except (AttributeError, OSError):
            pass
    left, top = widget.winfo_vrootx(), widget.winfo_vrooty()
    return left, top, left+widget.winfo_vrootwidth(), top+widget.winfo_vrootheight()


def popup_position(anchor, menu, work_area):
    ax, ay, _aw, ah = anchor
    width, height = menu
    left, top, right, bottom = work_area
    x = max(left, min(ax, right-width))
    y = ay+ah+5
    if y+height > bottom:
        y = ay-height-5
    return x, max(top, min(y, bottom-height))


class Dropdown(tk.Canvas):
    row_height = 40

    def __init__(self, parent, variable=None, values=(), *, variables=None, labels=None,
                 width=24, state='readonly'):
        super().__init__(parent, width=max(90, width*9), height=42,
                         background=parent.cget('background'), borderwidth=0,
                         highlightthickness=0, takefocus=True, cursor='hand2')
        self.variable, self.variables = variable, variables
        self.values = tuple(values)
        self.labels = labels or {value: value for value in self.values}
        self._state, self._hover, self._active = state, False, 0
        self.popup = self.popup_canvas = None
        self._focus_check_id = None
        self._font = tkfont.Font(self, font=BODY_FONT)
        self._traces = []
        observed = variables.values() if variables is not None else (variable,)
        for var in observed:
            self._traces.append((var, var.trace_add('write', self._value_changed)))
        self.bind('<Configure>', lambda _: self._draw())
        self.bind('<Enter>', lambda _: self._set_hover(True))
        self.bind('<Leave>', lambda _: self._set_hover(False))
        self.bind('<FocusIn>', lambda _: self._draw())
        self.bind('<FocusOut>', lambda _: self._draw())
        self.bind('<ButtonRelease-1>', lambda _: self.invoke())
        self.bind('<Unmap>', lambda _: self.close_popup(restore_focus=False))
        for key in ('space', 'Return', 'Down', 'Up', 'Alt-Down'):
            self.bind('<'+key+'>', self._open_key)
        self._owner = self.winfo_toplevel()
        self._owner_binding = self._owner.bind('<Configure>', self._owner_configured, add='+')
        self._draw()

    def get(self):
        if self.variables is not None:
            return '、'.join(self.labels[v] for v in self.values if self.variables[v].get()) or '请选择保存格式'
        return self.labels.get(self.variable.get(), self.variable.get())

    def set(self, value):
        if self.variable is None or value not in self.values:
            raise ValueError('Invalid dropdown value')
        self.variable.set(value)

    def configure(self, cnf=None, **kwargs):
        if not hasattr(self, '_state'):
            return super().configure(cnf, **kwargs)
        if isinstance(cnf, dict):
            kwargs = {**cnf, **kwargs}
            cnf = None
        if 'state' in kwargs:
            self._state = kwargs.pop('state')
            disabled = self._state == 'disabled'
            if disabled:
                self.close_popup(restore_focus=False)
            super().configure(takefocus=not disabled, cursor='' if disabled else 'hand2')
        result = super().configure(cnf, **kwargs) if cnf or kwargs else None
        self._draw()
        return result

    config = configure

    def cget(self, key):
        if key == 'state' and hasattr(self, '_state'):
            return self._state
        if key == 'values' and hasattr(self, 'values'):
            return self.values
        return super().cget(key)

    def _set_hover(self, hovered):
        self._hover = hovered
        self._draw()

    def _value_changed(self, *_args):
        self._draw()
        self._draw_options()

    def _draw(self):
        self.delete('field')
        w, h = self.winfo_width(), 42
        if w < 30:
            return
        disabled = self._state == 'disabled'
        focused = self.focus_get() == self or self.popup is not None
        border = LINE if disabled else GREEN if focused else '#badaca' if self._hover else LINE
        bg = '#f6f8f9' if disabled else '#fcfefd' if self._hover else WHITE
        rounded_rect(self, 1, 1, w-1, h-1, 9, fill=bg, outline=border, width=1, tags='field')
        value, available = self.get(), w-48
        if self._font.measure(value) > available:
            while value and self._font.measure(value+'…') > available:
                value = value[:-1]
            value += '…'
        empty = self.variables is not None and not any(var.get() for var in self.variables.values())
        self.create_text(14, h/2, anchor='w', text=value, font=BODY_FONT,
                         fill='#a4afb6' if disabled else MUTED if empty else INK, tags='field')
        x, y = w-19, h/2
        direction = -1 if self.popup is not None else 1
        self.create_line(x-4, y-2*direction, x, y+2*direction, x+4, y-2*direction,
                         fill='#adb6bc' if disabled else MUTED, width=1.5, tags='field')

    def _open_key(self, _event):
        self.invoke()
        return 'break'

    def invoke(self):
        if self._state == 'disabled':
            return
        if self.popup is not None:
            self.close_popup()
            return
        self.focus_set()
        selected = [i for i, value in enumerate(self.values) if self._selected(value)]
        self._active = selected[0] if selected else 0
        popup = self.popup = tk.Toplevel(self, background='#edf2ef')
        popup.withdraw()
        popup.overrideredirect(True)
        popup.transient(self._owner)
        width = max(self.winfo_width(), max((self._font.measure(self.labels[v])+64 for v in self.values), default=128))
        height = len(self.values)*self.row_height+12
        x, y = popup_position((self.winfo_rootx(), self.winfo_rooty(), self.winfo_width(), self.winfo_height()),
                              (width, height), monitor_work_area(self))
        popup.geometry(f'{width}x{height}+{x}+{y}')
        canvas = self.popup_canvas = tk.Canvas(popup, width=width, height=height, borderwidth=0,
                                               highlightthickness=0, background=WHITE, takefocus=True)
        canvas.pack(fill='both', expand=True)
        canvas.bind('<Motion>', self._popup_motion)
        canvas.bind('<ButtonRelease-1>', self._popup_click)
        canvas.bind('<Escape>', lambda _: self.close_popup() or 'break')
        canvas.bind('<Up>', lambda _: self._move(-1))
        canvas.bind('<Down>', lambda _: self._move(1))
        canvas.bind('<Home>', lambda _: self._move_to(0))
        canvas.bind('<End>', lambda _: self._move_to(len(self.values)-1))
        canvas.bind('<space>', lambda _: self._choose(self._active) or 'break')
        canvas.bind('<Return>', self._confirm_key)
        canvas.bind('<Tab>', lambda _: self._traverse(False))
        canvas.bind('<Shift-Tab>', lambda _: self._traverse(True))
        popup.bind('<ButtonRelease-1>', self._outside_click)
        popup.bind('<FocusOut>', self._queue_focus_check)
        self._draw_options()
        popup.deiconify()
        popup.lift()
        popup.grab_set()
        canvas.focus_force()
        self._draw()

    def _selected(self, value):
        return bool(self.variables[value].get()) if self.variables is not None else self.variable.get() == value

    def _draw_options(self):
        canvas = self.popup_canvas
        if canvas is None:
            return
        canvas.delete('all')
        width = int(canvas.cget('width'))
        height = len(self.values)*self.row_height+12
        rounded_rect(canvas, 1, 1, width-1, height-1, 10, fill=WHITE, outline=LINE, width=1)
        for i, value in enumerate(self.values):
            selected = self._selected(value)
            top, cy = 6+i*self.row_height, 6+(i+.5)*self.row_height
            if selected or i == self._active:
                rounded_rect(canvas, 6, top+2, width-6, top+self.row_height-2, 7,
                             fill=PALE if selected else '#f4f7f5', outline='')
            if self.variables is not None:
                rounded_rect(canvas, 16, cy-7, 30, cy+7, 4, fill=GREEN if selected else WHITE,
                             outline=GREEN if selected else '#c9d5ce', width=1)
                if selected:
                    canvas.create_line(19, cy, 22, cy+3, 27, cy-3, fill=WHITE, width=1.7)
            elif selected:
                canvas.create_line(width-28, cy, width-24, cy+4, width-17, cy-4, fill=GREEN, width=1.7)
            canvas.create_text(42 if self.variables is not None else 16, cy, text=self.labels[value],
                               anchor='w', font=BODY_FONT, fill=GREEN_DARK if selected else INK)

    def _popup_motion(self, event):
        index = int((event.y-6)//self.row_height)
        if 0 <= index < len(self.values) and index != self._active:
            self._active = index
            self._draw_options()

    def _popup_click(self, event):
        index = int((event.y-6)//self.row_height)
        if 0 <= index < len(self.values):
            self._active = index
            self._choose(index)
        return 'break'

    def _choose(self, index):
        if self._state == 'disabled' or not 0 <= index < len(self.values):
            return
        value = self.values[index]
        if self.variables is not None:
            self.variables[value].set(not self.variables[value].get())
        else:
            self.variable.set(value)
            self.close_popup()
            self.event_generate('<<ComboboxSelected>>')

    def _move(self, delta):
        return self._move_to((self._active+delta) % len(self.values))

    def _move_to(self, index):
        self._active = index
        self._draw_options()
        return 'break'

    def _confirm_key(self, _event):
        if self.variables is None:
            self._choose(self._active)
        else:
            self.close_popup()
        return 'break'

    def _traverse(self, backwards):
        self.close_popup()
        target = self.tk_focusPrev() if backwards else self.tk_focusNext()
        if target:
            target.focus_set()
        return 'break'

    def _outside_click(self, event):
        popup = self.popup
        if popup and not (popup.winfo_rootx() <= event.x_root < popup.winfo_rootx()+popup.winfo_width()
                          and popup.winfo_rooty() <= event.y_root < popup.winfo_rooty()+popup.winfo_height()):
            self.close_popup()
        return 'break'

    def _queue_focus_check(self, _event):
        if self.popup is not None and self._focus_check_id is None:
            self._focus_check_id = self.after_idle(self._check_popup_focus)

    def _check_popup_focus(self):
        self._focus_check_id = None
        focused = self.focus_get()
        if self.popup is not None and (focused is None or focused.winfo_toplevel() != self.popup):
            self.close_popup(restore_focus=False)

    def _owner_configured(self, event):
        if event.widget == self._owner:
            self.close_popup(restore_focus=False)

    def close_popup(self, restore_focus=True):
        if self._focus_check_id is not None:
            self.after_cancel(self._focus_check_id)
            self._focus_check_id = None
        popup = self.popup
        self.popup = self.popup_canvas = None
        if popup is not None:
            if popup.grab_current() == popup:
                popup.grab_release()
            popup.destroy()
            if restore_focus and self._state != 'disabled':
                # A destroyed borderless popup can leave its Windows owner
                # inactive; focus_set alone does not restore keyboard input.
                self.focus_force()
        self._draw()

    def destroy(self):
        self.close_popup(restore_focus=False)
        self._owner.unbind('<Configure>', self._owner_binding)
        for variable, trace in self._traces:
            variable.trace_remove('write', trace)
        super().destroy()
