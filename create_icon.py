import math

from PIL import Image, ImageDraw


def star_points(cx, cy, outer_r, inner_r, num_points=5):
    """Возвращает координаты вершин звезды."""
    points = []
    for i in range(num_points * 2):
        angle = math.pi / 2 + i * math.pi / num_points
        radius = outer_r if i % 2 == 0 else inner_r
        x = cx + radius * math.cos(angle)
        y = cy - radius * math.sin(angle)
        points.append((x, y))
    return points


def draw_icon(size):
    """Рисует оранжевую звезду на светлом фоне."""
    light_bg = (245, 245, 250)
    orange = (255, 140, 0)

    img = Image.new("RGB", (size, size), light_bg)
    draw = ImageDraw.Draw(img)

    padding = int(size * 0.12)
    outer_r = (size - padding * 2) // 2
    inner_r = int(outer_r * 0.4)

    center = size // 2
    points = star_points(center, center, outer_r, inner_r)
    draw.polygon(points, fill=orange)

    return img


sizes = [(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)]
icons = [draw_icon(s) for s, _ in sizes]

rgb_icons = []
for icon in icons:
    if icon.mode != "RGB":
        rgb_img = icon.convert("RGB")
    else:
        rgb_img = icon
    rgb_icons.append(rgb_img)

try:
    rgb_icons[0].save(
        "app.ico",
        format="ICO",
        sizes=sizes,
        append_images=rgb_icons[1:],
    )
    print("Иконка 'app.ico' создана!")
    print("   Дизайн: оранжевая звезда на светлом фоне")
    print("   Цвета: светлый фон (#F5F5FA), оранжевая звезда (#FF8C00)")
except Exception as e:
    print(f"Ошибка при сохранении: {e}")
    print("Попытка альтернативного метода сохранения...")
    rgb_icons[0].save("app.ico", format="ICO")
    print("Иконка 'app.ico' создана (только один размер)")
