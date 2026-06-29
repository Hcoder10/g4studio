"""Screenshot the real Roblox Studio window (Windows) so Gemma-4 can grade the
ACTUAL engine render — no sandbox. The plugin builds the world in Studio's edit
mode; the local server grabs the Studio window here.
"""
from __future__ import annotations

import base64
import io
from typing import Optional


def find_studio_hwnd():
    try:
        import win32gui
    except Exception:
        return None
    matches = []

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd) or ""
        cls = win32gui.GetClassName(hwnd) or ""
        if "RobloxStudio" in cls:           # the real Studio window class (RobloxStudioBeta)
            matches.insert(0, hwnd)         # prioritize the exact match
        elif title.rstrip().endswith("Roblox Studio"):  # Studio title ends this way; browser tabs don't
            matches.append(hwnd)

    win32gui.EnumWindows(cb, None)
    return matches[0] if matches else None


def capture_studio(focus: bool = True, crop_chrome: bool = True) -> Optional[bytes]:
    """Return a PNG of the Studio window, or None if it isn't open/visible."""
    try:
        import win32con
        import win32gui
        from PIL import ImageGrab
    except Exception:
        return None

    hwnd = find_studio_hwnd()
    if not hwnd:
        return None
    try:
        if focus:
            try:
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
        l, t, r, b = win32gui.GetWindowRect(hwnd)
    except Exception:
        return None
    if r - l < 300 or b - t < 200:
        return None  # minimized / tiny

    if crop_chrome:
        # trim the ribbon (top) and output bar (bottom) so the 3D viewport dominates
        t += int((b - t) * 0.11)
        b -= int((b - t) * 0.14)
        # trim a little off the sides (explorer / properties panels)
        l += int((r - l) * 0.04)
        r -= int((r - l) * 0.20)

    try:
        img = ImageGrab.grab(bbox=(l, t, r, b))
    except Exception:
        return None
    # downscale large captures so vision payloads stay light
    if img.width > 1100:
        ratio = 1100 / img.width
        img = img.resize((1100, int(img.height * ratio)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def capture_data_uri(**kw) -> Optional[str]:
    png = capture_studio(**kw)
    if not png:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode()
