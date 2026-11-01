"""生成「自制人物插画」素材：纯本地绘制，无网络、无真实肖像。

运行：python scripts/make_people.py

所有人物均为虚构，图像是几何插画，不对应任何真实个人；
换用真实授权照片时，请同时更新 assets/images/people/SOURCES.md。
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT_DIR = Path(__file__).resolve().parents[1] / "assets" / "images" / "people"

PEOPLE = [
    {
        "name": "p01.png",
        "size": (900, 1200),
        "skin": (234, 192, 162),
        "hair": (38, 32, 30),
        "cloth": (58, 96, 88),
        "bg": ((246, 243, 236), (214, 224, 214)),
        "hair_style": "bun",
        "accent": (198, 160, 96),
    },
    {
        "name": "p02.png",
        "size": (900, 1200),
        "skin": (206, 156, 118),
        "hair": (24, 22, 20),
        "cloth": (28, 58, 96),
        "bg": ((240, 246, 252), (200, 214, 232)),
        "hair_style": "short",
        "helmet": True,
        "accent": (240, 196, 74),
    },
    {
        "name": "p03.png",
        "size": (900, 1200),
        "skin": (246, 205, 175),
        "hair": (92, 62, 42),
        "cloth": (124, 70, 46),
        "bg": ((250, 244, 236), (232, 214, 196)),
        "hair_style": "short",
        "glasses": True,
        "accent": (90, 90, 96),
    },
    {
        "name": "p04.png",
        "size": (480, 640),  # 故意低分辨率：用来触发 image_too_small
        "skin": (214, 170, 138),
        "hair": (18, 18, 20),
        "cloth": (92, 72, 108),
        "bg": ((244, 238, 250), (214, 204, 228)),
        "hair_style": "long",
        "accent": (180, 150, 200),
    },
]


def _gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size, top)
    draw = ImageDraw.Draw(image)
    for y in range(height):
        t = y / max(height - 1, 1)
        color = tuple(round(a + (b - a) * t) for a, b in zip(top, bottom))
        draw.line([(0, y), (width, y)], fill=color)
    return image.convert("RGBA")


def _s(value: float, scale: float) -> int:
    return round(value * scale)


def draw_person(size: tuple[int, int], person: dict, transparent: bool = False) -> Image.Image:
    width, height = size
    scale = width / 900
    skin = person["skin"]
    hair = person["hair"]
    cloth = person["cloth"]
    accent = person.get("accent", (200, 160, 96))

    if transparent:
        image = Image.new("RGBA", size, (0, 0, 0, 0))
    else:
        image = _gradient(size, person["bg"][0], person["bg"][1])
        halo = Image.new("RGBA", size, (0, 0, 0, 0))
        ImageDraw.Draw(halo).ellipse(
            [_s(120, scale), _s(150, scale), _s(780, scale), _s(820, scale)],
            fill=(255, 255, 255, 70),
        )
        image = Image.alpha_composite(image, halo.filter(ImageFilter.GaussianBlur(_s(30, scale))))

    layer = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)

    # 肩部与衣服
    draw.rounded_rectangle(
        [_s(150, scale), _s(742, scale), _s(750, scale), _s(1270, scale)],
        radius=_s(170, scale),
        fill=cloth + (255,),
    )
    # 衣领
    draw.polygon(
        [
            (_s(392, scale), _s(748, scale)),
            (_s(450, scale), _s(880, scale)),
            (_s(508, scale), _s(748, scale)),
        ],
        fill=tuple(min(255, c + 28) for c in cloth) + (255,),
    )
    draw.polygon(
        [
            (_s(418, scale), _s(752, scale)),
            (_s(450, scale), _s(838, scale)),
            (_s(482, scale), _s(752, scale)),
        ],
        fill=(250, 250, 250, 255),
    )

    # 工牌
    draw.rounded_rectangle(
        [_s(520, scale), _s(910, scale), _s(624, scale), _s(1030, scale)],
        radius=_s(14, scale),
        fill=(250, 250, 250, 245),
    )
    draw.rectangle(
        [_s(536, scale), _s(926, scale), _s(608, scale), _s(940, scale)],
        fill=accent + (255,),
    )
    for offset in (962, 982, 1002):
        draw.rectangle(
            [_s(536, scale), _s(offset, scale), _s(608, scale), _s(offset + 8, scale)],
            fill=(150, 150, 152, 190),
        )

    # 脖子
    draw.rounded_rectangle(
        [_s(398, scale), _s(590, scale), _s(502, scale), _s(790, scale)],
        radius=_s(38, scale),
        fill=tuple(max(0, c - 18) for c in skin) + (255,),
    )

    # 后发
    if person.get("hair_style") == "long":
        draw.ellipse(
            [_s(250, scale), _s(230, scale), _s(650, scale), _s(760, scale)],
            fill=tuple(max(0, c - 8) for c in hair) + (255,),
        )

    # 头
    draw.ellipse(
        [_s(298, scale), _s(282, scale), _s(602, scale), _s(668, scale)],
        fill=skin + (255,),
    )
    # 耳朵
    for cx in (292, 608):
        draw.ellipse(
            [_s(cx - 22, scale), _s(468, scale), _s(cx + 22, scale), _s(546, scale)],
            fill=tuple(max(0, c - 12) for c in skin) + (255,),
        )

    # 头发
    style = person.get("hair_style", "short")
    draw.ellipse(
        [_s(292, scale), _s(238, scale), _s(608, scale), _s(438, scale)],
        fill=hair + (255,),
    )
    if style == "long":
        draw.rounded_rectangle(
            [_s(262, scale), _s(360, scale), _s(338, scale), _s(640, scale)],
            radius=_s(36, scale),
            fill=hair + (255,),
        )
        draw.rounded_rectangle(
            [_s(562, scale), _s(360, scale), _s(638, scale), _s(640, scale)],
            radius=_s(36, scale),
            fill=hair + (255,),
        )
    if style == "bun":
        draw.ellipse(
            [_s(392, scale), _s(168, scale), _s(508, scale), _s(282, scale)],
            fill=tuple(min(255, c + 14) for c in hair) + (255,),
        )

    # 眉毛
    brow = tuple(max(0, c - 6) for c in hair)
    draw.line([(_s(356, scale), _s(444, scale)), (_s(418, scale), _s(432, scale))], fill=brow + (255,), width=_s(9, scale))
    draw.line([(_s(482, scale), _s(432, scale)), (_s(544, scale), _s(444, scale))], fill=brow + (255,), width=_s(9, scale))

    # 眼睛
    for cx in (388, 512):
        draw.ellipse(
            [_s(cx - 21, scale), _s(478, scale), _s(cx + 21, scale), _s(526, scale)],
            fill=(46, 40, 38, 255),
        )
        draw.ellipse(
            [_s(cx - 7, scale), _s(492, scale), _s(cx + 2, scale), _s(504, scale)],
            fill=(255, 255, 255, 230),
        )

    # 鼻子
    draw.line(
        [(_s(450, scale), _s(532, scale)), (_s(444, scale), _s(566, scale))],
        fill=tuple(max(0, c - 26) for c in skin) + (255,),
        width=_s(5, scale),
    )
    draw.arc(
        [_s(432, scale), _s(560, scale), _s(468, scale), _s(582, scale)],
        start=10,
        end=170,
        fill=tuple(max(0, c - 26) for c in skin) + (255,),
        width=_s(4, scale),
    )

    # 嘴
    draw.arc(
        [_s(408, scale), _s(586, scale), _s(492, scale), _s(634, scale)],
        start=15,
        end=165,
        fill=(168, 92, 88, 255),
        width=_s(8, scale),
    )

    # 头盔（飞手）：最后画，压住眉毛，避免“眉毛浮在头盔上”
    if person.get("helmet"):
        draw.rounded_rectangle(
            [_s(268, scale), _s(196, scale), _s(632, scale), _s(430, scale)],
            radius=_s(180, scale),
            fill=accent + (255,),
        )
        draw.rounded_rectangle(
            [_s(246, scale), _s(404, scale), _s(654, scale), _s(456, scale)],
            radius=_s(24, scale),
            fill=tuple(max(0, c - 30) for c in accent) + (255,),
        )
        draw.rounded_rectangle(
            [_s(300, scale), _s(216, scale), _s(382, scale), _s(404, scale)],
            radius=_s(30, scale),
            fill=(255, 255, 255, 90),
        )

    # 腮红
    blush = Image.new("RGBA", size, (0, 0, 0, 0))
    blush_draw = ImageDraw.Draw(blush)
    for cx in (348, 552):
        blush_draw.ellipse(
            [_s(cx - 30, scale), _s(548, scale), _s(cx + 30, scale), _s(596, scale)],
            fill=(224, 138, 118, 70),
        )
    layer = Image.alpha_composite(layer, blush.filter(ImageFilter.GaussianBlur(_s(6, scale))))

    # 眼镜
    if person.get("glasses"):
        draw = ImageDraw.Draw(layer)
        frame = (52, 52, 58, 255)
        draw.rounded_rectangle(
            [_s(356, scale), _s(464, scale), _s(430, scale), _s(540, scale)],
            radius=_s(16, scale),
            outline=frame,
            width=_s(7, scale),
        )
        draw.rounded_rectangle(
            [_s(470, scale), _s(464, scale), _s(544, scale), _s(540, scale)],
            radius=_s(16, scale),
            outline=frame,
            width=_s(7, scale),
        )
        draw.line([(_s(430, scale), _s(496, scale)), (_s(470, scale), _s(496, scale))], fill=frame, width=_s(7, scale))
        draw.line([(_s(356, scale), _s(492, scale)), (_s(330, scale), _s(500, scale))], fill=frame, width=_s(6, scale))
        draw.line([(_s(544, scale), _s(492, scale)), (_s(570, scale), _s(500, scale))], fill=frame, width=_s(6, scale))

    return Image.alpha_composite(image, layer)


def draw_group(size: tuple[int, int], people: list[dict]) -> Image.Image:
    width, height = size
    image = _gradient(size, (242, 238, 230), (208, 214, 220))

    ground = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(ground).ellipse(
        [width * 0.06, height * 0.78, width * 0.94, height * 1.04],
        fill=(90, 100, 110, 55),
    )
    image = Image.alpha_composite(image, ground.filter(ImageFilter.GaussianBlur(30)))

    card_width = 500
    card_height = round(card_width * 1200 / 900)
    top = height - card_height + 24
    lefts = [140, 550, 960]
    for left, person in zip(lefts, people):
        figure = draw_person((900, 1200), person, transparent=True).resize(
            (card_width, card_height), Image.Resampling.LANCZOS
        )
        image.alpha_composite(figure, (left, top))
    return image.convert("RGB")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for person in PEOPLE:
        image = draw_person(person["size"], person)
        image.convert("RGB").save(OUT_DIR / person["name"], format="PNG", optimize=True)
        print(f"{person['name']}: {person['size'][0]}x{person['size'][1]}")

    group = draw_group((1600, 900), [PEOPLE[0], PEOPLE[1], PEOPLE[3]])
    group.save(OUT_DIR / "group.png", format="PNG", optimize=True)
    print("group.png: 1600x900")


if __name__ == "__main__":
    main()
