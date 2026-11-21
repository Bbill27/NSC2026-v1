"""
===============================================================================
CerebroMotion - Hospital Theme & PIL Drawing Kit
===============================================================================
One place for the light "hospital" colour palette (used by both the Tkinter
screens and the camera-rendered screens) plus small PIL helpers shared by the
Interactive Tutorial and the Piano Tiles game.
===============================================================================
"""

from __future__ import annotations

import os

# =============================================================================
# 1. COLOUR TOKENS (light clinical palette, high contrast for elderly eyes)
# =============================================================================
BG = "#eef3f8"            # page background (soft blue-grey)
SURFACE = "#ffffff"       # cards
SURFACE_ALT = "#e3edf7"   # hover / secondary buttons
BORDER = "#cfdbe8"
PRIMARY = "#0a66b2"       # hospital blue
PRIMARY_DARK = "#084f8a"
SUCCESS = "#0f9d6e"       # green (correct / done)
WARN = "#d98200"
DANGER = "#d64545"
TEXT = "#1b2b3c"
MUTED = "#5a6b7e"
HEADING = "#0b2e4f"
ON_PRIMARY = "#ffffff"


def rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


R_BG, R_SURFACE, R_SURFACE_ALT, R_BORDER = rgb(BG), rgb(SURFACE), rgb(SURFACE_ALT), rgb(BORDER)
R_PRIMARY, R_PRIMARY_DARK = rgb(PRIMARY), rgb(PRIMARY_DARK)
R_SUCCESS, R_WARN, R_DANGER = rgb(SUCCESS), rgb(WARN), rgb(DANGER)
R_TEXT, R_MUTED, R_HEADING = rgb(TEXT), rgb(MUTED), rgb(HEADING)

# Finger colours (index, middle, ring, pinky) - distinct and colour-blind friendly
FINGER_RGB = [(37, 117, 252), (16, 163, 127), (232, 135, 0), (190, 70, 160)]

# =============================================================================
# 2. FONTS (Thai-capable, Windows first, Linux fallbacks for development)
# =============================================================================
_BOLD = ["LeelaUIb.ttf", "leelawdb.ttf", "tahomabd.ttf",
         "/usr/share/fonts/opentype/tlwg/Loma-Bold.otf",
         "/usr/share/fonts/truetype/noto/NotoSansThai-Bold.ttf", "DejaVuSans-Bold.ttf"]
_REG = ["LeelawUI.ttf", "leelawad.ttf", "tahoma.ttf",
        "/usr/share/fonts/opentype/tlwg/Loma.otf",
        "/usr/share/fonts/truetype/noto/NotoSansThai-Regular.ttf", "DejaVuSans.ttf"]
_font_cache: dict[tuple, object] = {}


def font(size: int, bold: bool = True):
    from PIL import ImageFont
    key = (int(size), bold)
    if key in _font_cache:
        return _font_cache[key]
    f = None
    for cand in (_BOLD if bold else _REG):
        try:
            f = ImageFont.truetype(cand, int(size))
            break
        except Exception:
            continue
    if f is None:
        f = ImageFont.load_default()
    _font_cache[key] = f
    return f


# =============================================================================
# 3. PIL DRAWING HELPERS
# =============================================================================
def text_size(draw, text, fnt):
    bb = draw.textbbox((0, 0), text, font=fnt)
    return bb[2] - bb[0], bb[3] - bb[1], bb


def text_center(draw, cx, cy, text, fnt, fill):
    w, h, bb = text_size(draw, text, fnt)
    draw.text((cx - w / 2 - bb[0], cy - h / 2 - bb[1]), text, font=fnt, fill=fill)


def text_left(draw, x, cy, text, fnt, fill):
    w, h, bb = text_size(draw, text, fnt)
    draw.text((x - bb[0], cy - h / 2 - bb[1]), text, font=fnt, fill=fill)
    return w


def card(draw, box, fill=R_SURFACE, outline=R_BORDER, radius=18, width=2):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def button(draw, box, label, fnt, style="primary"):
    """Draws a big rounded button. Styles: primary | secondary | danger | success."""
    fills = {
        "primary": (R_PRIMARY, R_PRIMARY_DARK, (255, 255, 255)),
        "secondary": (R_SURFACE, R_BORDER, R_HEADING),
        "danger": ((255, 255, 255), R_DANGER, R_DANGER),
        "success": (R_SUCCESS, (10, 120, 84), (255, 255, 255)),
    }
    fill, outline, fg = fills.get(style, fills["primary"])
    draw.rounded_rectangle(box, radius=int((box[3] - box[1]) / 2.6), fill=fill, outline=outline, width=3)
    text_center(draw, (box[0] + box[2]) / 2, (box[1] + box[3]) / 2, label, fnt, fg)


def check_icon(draw, cx, cy, r, ok):
    """Green circle with a tick, or an empty grey circle."""
    if ok:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=R_SUCCESS)
        draw.line([(cx - r * 0.45, cy), (cx - r * 0.1, cy + r * 0.38), (cx + r * 0.5, cy - r * 0.35)],
                  fill=(255, 255, 255), width=max(3, int(r * 0.28)))
    else:
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=(170, 182, 196), width=max(2, int(r * 0.18)))


def note_icon(draw, cx, cy, r, color=(255, 255, 255)):
    """Music note drawn with shapes (the Thai UI fonts have no note glyph)."""
    hx = r * 0.28
    draw.ellipse([cx - r * 0.55, cy + r * 0.25, cx - r * 0.55 + r * 0.62, cy + r * 0.25 + r * 0.46], fill=color)
    draw.line([(cx - r * 0.55 + r * 0.58, cy + r * 0.48), (cx - r * 0.55 + r * 0.58, cy - r * 0.62)],
              fill=color, width=max(2, int(r * 0.13)))
    draw.polygon([(cx + hx * 0.1, cy - r * 0.62), (cx + r * 0.62, cy - r * 0.34), (cx + r * 0.62, cy - r * 0.05),
                  (cx + hx * 0.1, cy - r * 0.32)], fill=color)


def inside(box, x, y) -> bool:
    return box[0] <= x <= box[2] and box[1] <= y <= box[3]


def place_camera(img, frame_bgr, box, lms=None):
    """
    Fits the (already mirrored) camera frame inside `box` on a PIL image and
    draws the hand skeleton on top. Returns the (x, y, w, h) actually used.
    """
    from PIL import Image
    from utils import _ensure_cv2
    from vision import draw_skeleton
    cv2 = _ensure_cv2()

    bx0, by0, bx1, by1 = [int(v) for v in box]
    bw, bh = bx1 - bx0, by1 - by0
    fh, fw = frame_bgr.shape[:2]
    s = min(bw / fw, bh / fh)
    nw, nh = max(1, int(fw * s)), max(1, int(fh * s))
    small = cv2.resize(frame_bgr, (nw, nh))
    if lms:
        draw_skeleton(small, lms)
    x0, y0 = bx0 + (bw - nw) // 2, by0 + (bh - nh) // 2
    img.paste(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)), (x0, y0))
    return x0, y0, nw, nh


_SafeDraw = None


def _safe_draw_class():
    """ImageDraw whose rounded_rectangle never crashes on small windows (radius is clamped to the shape)."""
    global _SafeDraw
    if _SafeDraw is None:
        from PIL import ImageDraw

        class SafeDraw(ImageDraw.ImageDraw):
            def rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, **kw):
                if len(xy) == 2:
                    (x0, y0), (x1, y1) = xy
                else:
                    x0, y0, x1, y1 = xy
                x0, x1 = sorted((x0, x1))
                y0, y1 = sorted((y0, y1))
                x0, y0, x1, y1 = int(x0), int(y0), int(max(x1, x0 + 1)), int(max(y1, y0 + 1))
                r = max(0, min(int(radius), (min(x1 - x0, y1 - y0) // 2) - 1))
                return super().rounded_rectangle([x0, y0, x1, y1], radius=r, fill=fill, outline=outline,
                                                 width=width, **kw)
        _SafeDraw = SafeDraw
    return _SafeDraw


def new_screen(w, h):
    from PIL import Image
    img = Image.new("RGB", (int(w), int(h)), R_BG)
    return img, _safe_draw_class()(img)


def json_path(filename: str) -> str:
    """Runtime data lives in Documents/NSC Medical Suite (same as settings/users)."""
    d = os.path.join(os.path.expanduser("~"), "Documents", "NSC Medical Suite")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)
