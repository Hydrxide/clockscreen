"""LED matrix rendering: a screen at a moment -> 128x64 RGB frame.

Pure Python with no hardware dependency, so the same code draws the browser
preview and the frames HController sends to the panel.
"""

from .canvas import Canvas
from .layouts import HEIGHT, WIDTH, Settings, render

__all__ = ["Canvas", "HEIGHT", "Settings", "WIDTH", "render"]
