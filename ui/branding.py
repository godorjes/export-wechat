"""Shared application artwork for the window and header."""
from pathlib import Path

from PIL import Image, ImageTk


ASSETS = Path(__file__).resolve().parents[1] / 'assets'


def set_app_icon(root):
    # __file__ also resolves inside PyInstaller's bundled data directory.
    with Image.open(ASSETS / 'app.png') as source:
        logo = source.convert('RGBA')
    root._brand_images = {
        size: ImageTk.PhotoImage(logo.resize((size, size), Image.Resampling.LANCZOS), master=root)
        for size in (16, 32, 48, 60, 64, 128, 256)
    }
    root.iconphoto(True, *(root._brand_images[size] for size in (256, 128, 64, 48, 32, 16)))
