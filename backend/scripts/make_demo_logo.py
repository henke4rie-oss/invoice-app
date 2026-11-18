"""Regenerate the demo business logo (backend/app/demo_assets/northwind-logo.png).

Pure standard library (zlib + struct), so no image dependency is needed:

    python backend/scripts/make_demo_logo.py

A rounded square with an indigo->violet gradient and a white "N", antialiased by 4x4 supersampling.
No text or fonts: the invoice already prints the business name beside the logo.
"""
import struct
import sys
import zlib
from pathlib import Path

SIZE = 256
SUPER = 4  # 4x4 samples per pixel
MARGIN, RADIUS = 8, 58
START, END = (0x63, 0x66, 0xF1), (0xA8, 0x55, 0xF7)  # indigo-500 -> purple-500 (blue/purple only)

# The "N": left stem, right stem, diagonal (coordinates in the 256x256 canvas)
LETTER = [
    [(80, 70), (102, 70), (102, 186), (80, 186)],
    [(154, 70), (176, 70), (176, 186), (154, 186)],
    [(80, 70), (104, 70), (176, 186), (152, 186)],
]
OUT = Path(__file__).resolve().parent.parent / "app" / "demo_assets" / "northwind-logo.png"


def in_polygon(x, y, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def in_tile(x, y):
    half = SIZE / 2 - MARGIN
    dx = max(abs(x - SIZE / 2) - (half - RADIUS), 0)
    dy = max(abs(y - SIZE / 2) - (half - RADIUS), 0)
    return dx * dx + dy * dy <= RADIUS * RADIUS


def gradient(x, y):
    t = (x + y) / (2 * SIZE)
    return tuple(a + (b - a) * t for a, b in zip(START, END))


def render():
    rows = []
    n = SUPER * SUPER
    for py in range(SIZE):
        row = bytearray([0])  # PNG filter type 0 (none)
        for px in range(SIZE):
            covered = 0
            r = g = b = 0.0
            for sy in range(SUPER):
                for sx in range(SUPER):
                    x = px + (sx + 0.5) / SUPER
                    y = py + (sy + 0.5) / SUPER
                    if not in_tile(x, y):
                        continue
                    covered += 1
                    if any(in_polygon(x, y, p) for p in LETTER):
                        cr, cg, cb = 255, 255, 255
                    else:
                        cr, cg, cb = gradient(x, y)
                    r, g, b = r + cr, g + cg, b + cb
            if covered:
                row += bytes((round(r / covered), round(g / covered), round(b / covered), round(255 * covered / n)))
            else:
                row += bytes((0, 0, 0, 0))
        rows.append(bytes(row))
    return b"".join(rows)


def chunk(kind, data):
    body = kind + data
    return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body) & 0xFFFFFFFF)


def main():
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))  # 8-bit RGBA
           + chunk(b"IDAT", zlib.compress(render(), 9))
           + chunk(b"IEND", b""))
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(png)
    print(f"wrote {OUT} ({len(png)} bytes)")


if __name__ == "__main__":
    sys.exit(main())
