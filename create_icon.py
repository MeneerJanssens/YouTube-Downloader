import sys

from PIL import Image, ImageDraw


def make_frame(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    r = size // 7
    draw.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=(204, 0, 0, 255))

    cx = size // 2
    lw = max(2, size // 10)
    aw = size * 5 // 14
    ah = size * 3 // 14
    top = size * 3 // 20
    tip = size * 13 // 20
    bar_y = size * 15 // 20
    bar_h = max(1, size // 14)
    margin = size // 7
    white = (255, 255, 255, 255)

    draw.rectangle([cx - lw // 2, top, cx + lw // 2, tip - ah + lw], fill=white)
    draw.polygon([(cx, tip), (cx - aw // 2, tip - ah), (cx + aw // 2, tip - ah)], fill=white)
    draw.rectangle([margin, bar_y, size - margin, bar_y + bar_h], fill=white)

    return img


# Render every size separately so the small icons stay crisp.
SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
frames = [make_frame(s) for s, _ in SIZES]

frames[0].save("icon.ico", format="ICO", sizes=SIZES, append_images=frames[1:])
frames[-1].save("icon.png")

# .icns is only writable by Pillow on macOS (used by the CI macOS build).
if sys.platform == "darwin":
    try:
        frames[0].save("icon.icns", format="ICNS", append_images=frames[1:])
        print("icon.icns saved")
    except Exception as e:
        print("warning: could not write icon.icns:", e)

print("icons saved")
