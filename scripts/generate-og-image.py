#!/usr/bin/env python3
"""Generate the static 1200x630 Open Graph card (SEO-8).

    python3 scripts/generate-og-image.py

Writes ``web/public/og-image.png``. Committed rather than generated at build
time: the card changes about never, and a build-time dependency on Pillow would
add a Python toolchain to the Node image for one static file.

Colours are the crest-grounded design tokens from ``web/app/globals.css`` (PR
#117) — not eyeballed. If that palette changes, update the constants here and
re-run, otherwise the card drifts away from the site it represents.
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

REPO = Path(__file__).resolve().parent.parent
LOGO = REPO / "web" / "public" / "logo.png"
OUT = REPO / "web" / "public" / "og-image.png"

WIDTH, HEIGHT = 1200, 630

# web/app/globals.css
INK_950 = (5, 14, 14)
INK_0 = (252, 254, 254)
TEAL_400 = (82, 163, 161)
TEAL_600 = (2, 116, 114)

TITLE = "SHARKS NEWS AGGREGATOR"
SUBTITLE = "Every San Jose Sharks story in one place"
DETAIL = "Trades · Signings · Injuries · Prospects · Barracuda"
FOOTNOTE = "Updated every 10 minutes · Free · No ads · No tracking"

# Oswald/IBM Plex are fetched by next/font at build time and aren't on disk
# here, so fall back through the fonts a mac/linux box actually has.
FONT_CANDIDATES = {
    "bold": [
        "/System/Library/Fonts/Supplemental/Impact.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "regular": [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
}


def load_font(kind: str, size: int):
    for path in FONT_CANDIDATES[kind]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size)


def main() -> None:
    if not LOGO.exists():
        raise SystemExit(f"missing crest: {LOGO}")

    card = Image.new("RGB", (WIDTH, HEIGHT), INK_950)
    draw = ImageDraw.Draw(card)

    # Teal wash from the left so the crest sits on tone rather than flat black.
    for x in range(WIDTH):
        t = max(0.0, 1.0 - (x / (WIDTH * 0.72))) ** 1.6
        draw.line(
            [(x, 0), (x, HEIGHT)],
            fill=tuple(
                int(INK_950[i] + (TEAL_900_BLEND[i] - INK_950[i]) * t) for i in range(3)
            ),
        )

    draw.rectangle([0, HEIGHT - 10, WIDTH, HEIGHT], fill=TEAL_600)

    crest = Image.open(LOGO).convert("RGBA")
    box = 340
    crest.thumbnail((box, box), Image.LANCZOS)
    crest_x, crest_y = 78, (HEIGHT - crest.height) // 2 - 8
    card.paste(crest, (crest_x, crest_y), crest)

    # Lay the text out as one block and centre it against the crest, rather than
    # hand-placing each line — otherwise the group drifts high and the card ends
    # up with a dead lower third.
    text_x = crest_x + box + 58
    lines = [
        (TITLE, load_font("bold", 60), INK_0, 22),
        (SUBTITLE, load_font("regular", 32), INK_0, 14),
        (DETAIL, load_font("regular", 24), TEAL_400, 26),
        (FOOTNOTE, load_font("regular", 21), TEAL_400, 0),
    ]

    heights = []
    for content, font, _, gap in lines:
        top, bottom = draw.textbbox((0, 0), content, font=font)[1::2]
        heights.append((bottom - top, gap, top))
    block_height = sum(h + g for h, g, _ in heights)

    y = (HEIGHT - block_height) // 2 - 12
    for (content, font, colour, _), (height, gap, top) in zip(lines, heights):
        draw.text((text_x, y - top), content, font=font, fill=colour)
        y += height + gap

    card.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT.relative_to(REPO)} ({OUT.stat().st_size // 1024} KB)")


TEAL_900_BLEND = (2, 47, 46)  # --teal-900

if __name__ == "__main__":
    main()
