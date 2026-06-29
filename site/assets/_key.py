"""Key pure-white studio backgrounds to alpha for the G4Studio hardware sprites.
Border flood-fill + center-seed for ring objects + strict interior-hole removal
+ halo erosion + slight feather + autocrop. Also writes a contact sheet to verify
the cutouts on sky-blue and maroon backgrounds."""
import os
from collections import deque
from PIL import Image, ImageFilter

SRC = r"C:\Users\sarta\.cursor\projects\C-Users-sarta-AppData-Local-Temp-af7715b9-68c0-47e1-8cd8-2c14b1e62aea\assets"
DST = r"C:\Users\sarta\g4studio\site\assets"
FILES = ["bolt.png", "nut.png", "screw.png", "gear.png", "washer.png", "so101.png"]
CENTER_SEED = {"nut.png", "washer.png", "gear.png"}


def is_bg_loose(r, g, b):
    mx, mn = max(r, g, b), min(r, g, b)
    return mx >= 205 and (mx - mn) <= 24


def is_white_strict(r, g, b):
    return min(r, g, b) >= 232


def key(name):
    im = Image.open(os.path.join(SRC, name)).convert("RGBA")
    w, h = im.size
    px = im.load()
    seen = bytearray(w * h)
    q = deque()

    def push(x, y):
        if 0 <= x < w and 0 <= y < h and not seen[y * w + x]:
            q.append((x, y))

    for x in range(w):
        push(x, 0); push(x, h - 1)
    for y in range(h):
        push(0, y); push(w - 1, y)
    if name in CENTER_SEED:
        push(w // 2, h // 2)

    while q:
        x, y = q.popleft()
        idx = y * w + x
        if seen[idx]:
            continue
        seen[idx] = 1
        r, g, b, a = px[x, y]
        if not is_bg_loose(r, g, b):
            continue
        px[x, y] = (r, g, b, 0)
        push(x + 1, y); push(x - 1, y); push(x, y + 1); push(x, y - 1)

    # halo erosion: clear opaque bg-ish pixels adjacent to transparency
    for _ in range(2):
        clear = []
        for y in range(h):
            row = y * w
            for x in range(w):
                r, g, b, a = px[x, y]
                if a == 0 or not is_bg_loose(r, g, b):
                    continue
                if ((x > 0 and px[x - 1, y][3] == 0) or (x < w - 1 and px[x + 1, y][3] == 0)
                        or (y > 0 and px[x, y - 1][3] == 0) or (y < h - 1 and px[x, y + 1][3] == 0)):
                    clear.append((x, y, r, g, b))
        for x, y, r, g, b in clear:
            px[x, y] = (r, g, b, 0)

    # interior strict-white holes/slots not reachable from the border
    sseen = bytearray(w * h)
    maxarea = 0.18 * w * h
    for y0 in range(h):
        for x0 in range(w):
            if sseen[y0 * w + x0]:
                continue
            r, g, b, a = px[x0, y0]
            if a == 0 or not is_white_strict(r, g, b):
                sseen[y0 * w + x0] = 1
                continue
            comp = []
            qq = deque([(x0, y0)])
            border = False
            while qq:
                cx, cy = qq.popleft()
                ci = cy * w + cx
                if sseen[ci]:
                    continue
                sseen[ci] = 1
                cr, cg, cb, ca = px[cx, cy]
                if ca == 0 or not is_white_strict(cr, cg, cb):
                    continue
                comp.append((cx, cy))
                if cx in (0, w - 1) or cy in (0, h - 1):
                    border = True
                for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                    if 0 <= nx < w and 0 <= ny < h and not sseen[ny * w + nx]:
                        qq.append((nx, ny))
            if comp and not border and 20 <= len(comp) <= maxarea:
                for cx, cy in comp:
                    rr, gg, bb, _ = px[cx, cy]
                    px[cx, cy] = (rr, gg, bb, 0)

    alpha = im.split()[3].filter(ImageFilter.GaussianBlur(0.6))
    im.putalpha(alpha)
    bbox = im.getbbox()
    if bbox:
        l, t, r, b = bbox
        pad = 8
        im = im.crop((max(0, l - pad), max(0, t - pad), min(w, r + pad), min(h, b + pad)))
    im.save(os.path.join(DST, name))
    print("keyed", name, im.size)
    return im


keyed = {n: key(n) for n in FILES}

# contact sheet: row1 sky, row2 maroon
cell, pad = 200, 10
cols = len(FILES)
sheet = Image.new("RGBA", (cols * cell, 2 * cell), (255, 255, 255, 255))
bgs = [(188, 228, 245, 255), (58, 15, 18, 255)]
for ri, bg in enumerate(bgs):
    band = Image.new("RGBA", (cols * cell, cell), bg)
    sheet.alpha_composite(band, (0, ri * cell))
    for ci, n in enumerate(FILES):
        spr = keyed[n].copy()
        spr.thumbnail((cell - 2 * pad, cell - 2 * pad))
        ox = ci * cell + (cell - spr.width) // 2
        oy = ri * cell + (cell - spr.height) // 2
        sheet.alpha_composite(spr, (ox, oy))
sheet.convert("RGB").save(os.path.join(DST, "_contact.png"))
print("contact sheet written")
