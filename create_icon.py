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


base = make_frame(256)
base.save("icon.ico", format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
base.save("icon.png")
print("icon.ico and icon.png saved")
