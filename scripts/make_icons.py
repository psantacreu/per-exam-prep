"""Draw the home-screen icons (app/icons/*.png): the header's anchor logo on navy.

Run once; the PNGs are committed. Drawn at 4x and downscaled for smooth edges.
"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "app" / "icons"
NAVY, RING, INK = "#0b2545", "#5eaee6", "#e8eef6"


def bezier(p0, p1, p2, p3, steps=40):
    for i in range(steps + 1):
        t = i / steps
        yield tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t ** 2 * c + t ** 3 * d
                    for a, b, c, d in zip(p0, p1, p2, p3))


def icon(size):
    big = size * 4
    img = Image.new("RGB", (big, big), NAVY)
    d = ImageDraw.Draw(img)
    # The logo's 32-unit viewBox, shrunk to ~62% so it sits inside the maskable safe zone.
    unit = big * 0.62 / 32
    off = (big - 32 * unit) / 2

    def pt(x, y):
        return (off + x * unit, off + y * unit)

    def line(points, width, fill=INK):
        # a round brush stamped densely along the path: smooth joins and round caps
        pts = [pt(*p) for p in points]
        r = width * unit / 2
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            n = max(1, int(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** .5 / 2))
            for i in range(n + 1):
                x, y = x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n
                d.ellipse((x - r, y - r, x + r, y + r), fill=fill)

    cx, cy, r = *pt(16, 16), 15 * unit
    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=RING, width=round(1.5 * unit))
    line([(16, 9), (16, 25)], 2)
    line([(11, 10.5), (21, 10.5)], 2)
    line(list(bezier((16, 25), (11.5, 25), (8, 22), (7.5, 18))), 2)
    line(list(bezier((16, 25), (20.5, 25), (24, 22), (24.5, 18))), 2)
    dx, dy, dr = *pt(16, 6.5), 2 * unit
    d.ellipse((dx - dr, dy - dr, dx + dr, dy + dr), outline=INK, width=round(1.6 * unit))
    return img.resize((size, size), Image.LANCZOS)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    for size, name in ((180, "apple-touch-icon.png"), (192, "icon-192.png"), (512, "icon-512.png")):
        icon(size).save(OUT / name, optimize=True)
        print(OUT / name)
