"""Render Romy Calloway graphics (1080x1350 JPEG) from a post.json.

Usage:
    python scripts/render.py posts/queue/2026-10-28-meet-romy   # one post
    python scripts/render.py --all                              # every post in queue/ without images

Slide types (in post.json -> "slides"):
    cover  : kicker (optional), title, subtitle (optional)
    text   : number (optional), heading, body
    quote  : quote, author (optional, e.g. "Answer the Landline")
    cta    : title, body (optional)
    book   : image (book cover, e.g. assets/covers/answer-the-landline.jpg), kicker (optional), title (optional)
    photo  : image (path inside the repo), title (optional)
"""
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FONTS = ROOT / "assets" / "fonts"
BRAND = json.loads((ROOT / "brand" / "style.json").read_text(encoding="utf-8"))

W, H = 1080, 1350
MARGIN = 96
C = BRAND["colors"]


def font(kind, size):
    files = {"serif": "CormorantGaramond.ttf", "italic": "CormorantGaramond-Italic.ttf",
             "sans": "Inter.ttf", "sans_bold": "Inter.ttf", "display": "Inter.ttf"}
    weights = {"serif": "Medium", "italic": "Italic", "sans": "Regular", "sans_bold": "SemiBold", "display": "Bold"}
    f = ImageFont.truetype(str(FONTS / files[kind]), size)
    try:
        f.set_variation_by_name(weights[kind])
    except Exception:
        pass
    return f


def wrap(draw, text, fnt, max_w):
    lines = []
    for para in str(text).split("\n"):
        words, line = para.split(), ""
        for w in words:
            test = f"{line} {w}".strip()
            if draw.textlength(test, font=fnt) <= max_w:
                line = test
            else:
                if line:
                    lines.append(line)
                line = w
        lines.append(line)
    return lines


def block(draw, text, kind, size, max_w, max_h, min_size=24, spacing=1.18):
    """Return (font, lines, line_height, height), shrinking the font until the text fits."""
    while True:
        fnt = font(kind, size)
        lines = wrap(draw, text, fnt, max_w)
        lh = int(size * spacing)
        h = lh * len(lines)
        too_wide = any(draw.textlength(ln, font=fnt) > max_w for ln in lines)
        if (h <= max_h and not too_wide) or size <= min_size:
            return fnt, lines, lh, h
        size -= 4


def draw_lines(draw, lines, fnt, lh, x, y, fill, align="left", width=None):
    for ln in lines:
        lx = x
        if align == "center":
            lx = x + (width - draw.textlength(ln, font=fnt)) / 2
        draw.text((lx, y), ln, font=fnt, fill=fill)
        y += lh
    return y


def spaced(draw, xy, text, fnt, fill, tracking=4, center_w=None):
    x, y = xy
    if center_w:
        total = sum(draw.textlength(ch, font=fnt) + tracking for ch in text) - tracking
        x = x + (center_w - total) / 2
    for ch in text:
        draw.text((x, y), ch, font=fnt, fill=fill)
        x += draw.textlength(ch, font=fnt) + tracking
    return x


def red_line(draw, x, y, w=90):
    draw.rectangle([x, y, x + w, y + 6], fill=C["accent"])


def chrome(img, draw, idx, total):
    fg = C["muted"]
    small = font("sans", 22)
    spaced(draw, (MARGIN, H - 92), BRAND["handle"].upper(), small, fg, tracking=3)
    if total > 1:
        t = f"{idx:02d} / {total:02d}"
        draw.text((W - MARGIN - draw.textlength(t, font=small), H - 92), t, font=small, fill=fg)
    draw.line([(MARGIN, H - 120), (W - MARGIN, H - 120)], fill=C["line"], width=1)


def slide_cover(s, draw):
    y = 300
    if s.get("kicker"):
        spaced(draw, (MARGIN, y), s["kicker"].upper(), font("sans_bold", 24), C["accent"], tracking=6)
        y += 70
    fnt, lines, lh, h = block(draw, s["title"], "display", 96, W - 2 * MARGIN, 560, spacing=1.08)
    y = draw_lines(draw, lines, fnt, lh, MARGIN, y, C["text"]) + 30
    red_line(draw, MARGIN, y)
    if s.get("subtitle"):
        y += 60
        fnt, lines, lh, _ = block(draw, s["subtitle"], "italic", 50, W - 2 * MARGIN, 260)
        draw_lines(draw, lines, fnt, lh, MARGIN, y, C["muted"])


def slide_text(s, draw):
    y = 230
    if s.get("number"):
        draw.text((MARGIN, y), str(s["number"]), font=font("italic", 96), fill=C["accent"])
        y += 150
    fnt, lines, lh, _ = block(draw, s["heading"], "display", 66, W - 2 * MARGIN, 300, spacing=1.12)
    y = draw_lines(draw, lines, fnt, lh, MARGIN, y, C["text"]) + 36
    red_line(draw, MARGIN, y, 70)
    y += 56
    fnt, lines, lh, _ = block(draw, s.get("body", ""), "sans", 42, W - 2 * MARGIN, H - y - 200, spacing=1.45)
    draw_lines(draw, lines, fnt, lh, MARGIN, y, C["text"])


def slide_quote(s, draw):
    draw.text((MARGIN - 10, 170), "“", font=font("italic", 260), fill=C["accent"])
    fnt, lines, lh, h = block(draw, s["quote"], "italic", 84, W - 2 * MARGIN, 640, spacing=1.12)
    y = (H - h) // 2
    y = draw_lines(draw, lines, fnt, lh, MARGIN, y, C["text"])
    if s.get("author"):
        spaced(draw, (MARGIN, y + 40), "— " + s["author"].upper(), font("sans", 24), C["muted"], tracking=4)


def slide_cta(s, draw):
    fnt, lines, lh, h = block(draw, s["title"], "display", 84, W - 2 * MARGIN, 420, spacing=1.08)
    y = (H - h) // 2 - 80
    y = draw_lines(draw, lines, fnt, lh, MARGIN, y, C["text"], align="center", width=W - 2 * MARGIN) + 30
    red_line(draw, W // 2 - 45, y)
    y += 50
    if s.get("body"):
        fnt, lines, lh, _ = block(draw, s["body"], "sans", 34, W - 2 * MARGIN - 80, 260, spacing=1.45)
        draw_lines(draw, lines, fnt, lh, MARGIN, y, C["muted"], align="center", width=W - 2 * MARGIN)


def slide_book(s, img, draw):
    """Book cover centred on the dark background with a soft shadow; optional kicker and title below."""
    has_text = bool(s.get("title") or s.get("kicker"))
    max_h = 860 if has_text else 1000
    cover = Image.open(ROOT / s["image"]).convert("RGB")
    cover.thumbnail((W - 2 * MARGIN - 120, max_h), Image.LANCZOS)
    cw, ch = cover.size
    x, y = (W - cw) // 2, 110 if has_text else (H - 120 - ch) // 2
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rectangle([x + 14, y + 22, x + cw + 14, y + ch + 22], fill=170)
    shadow = shadow.filter(ImageFilter.GaussianBlur(26))
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shadow)
    img.paste(cover, (x, y))
    ty = y + ch + 60
    if s.get("kicker"):
        spaced(draw, (MARGIN, ty), s["kicker"].upper(), font("sans_bold", 24), C["accent"], tracking=6,
               center_w=W - 2 * MARGIN)
        ty += 56
    if s.get("title"):
        fnt, lines, lh, _ = block(draw, s["title"], "italic", 54, W - 2 * MARGIN, H - 140 - ty, spacing=1.12)
        draw_lines(draw, lines, fnt, lh, MARGIN, ty, C["text"], align="center", width=W - 2 * MARGIN)


def slide_photo(s, img, draw):
    photo = Image.open(ROOT / s["image"]).convert("RGB")
    photo = ImageOps.fit(photo, (W, H), method=Image.LANCZOS)
    img.paste(photo, (0, 0))
    if s.get("title"):
        shade = Image.new("L", (W, H), 0)
        sd = ImageDraw.Draw(shade)
        for i in range(620):  # dark gradient at the bottom for legibility
            sd.line([(0, H - 620 + i), (W, H - 620 + i)], fill=int(225 * (i / 620) ** 1.3))
        img.paste(Image.new("RGB", (W, H), (8, 10, 16)), (0, 0), shade)
        fnt, lines, lh, h = block(draw, s["title"], "display", 80, W - 2 * MARGIN, 330, spacing=1.08)
        draw_lines(draw, lines, fnt, lh, MARGIN, H - 175 - h, C["text"])
        return True
    return None  # bare photo: no text, no frame


def render_post(folder):
    folder = Path(folder)
    post = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    # fonts have no emoji glyphs: strip them from slide text (captions keep theirs)
    clean = lambda v: "".join(ch for ch in v if ord(ch) < 0x2190).strip() if isinstance(v, str) else v
    slides = [{k: (v if k == "image" else clean(v)) for k, v in s.items()} for s in post["slides"]]
    out = []
    for i, s in enumerate(slides, 1):
        img = Image.new("RGB", (W, H), C["background"])
        draw = ImageDraw.Draw(img)
        frame = True
        t = s.get("type", "text")
        if t == "cover":
            slide_cover(s, draw)
        elif t == "quote":
            slide_quote(s, draw)
        elif t == "cta":
            slide_cta(s, draw)
        elif t == "book":
            slide_book(s, img, draw)
        elif t == "photo":
            frame = slide_photo(s, img, draw) is not None
        else:
            slide_text(s, draw)
        if frame:
            chrome(img, draw, i, len(slides))
        path = folder / f"{i:02d}.jpg"
        img.save(path, "JPEG", quality=92, optimize=True)
        out.append(path)
    print(f"rendered {len(out)} slide(s) -> {folder}")
    return out


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "--all":
        for d in sorted((ROOT / "posts" / "queue").glob("*/")):
            if (d / "post.json").exists() and not (d / "01.jpg").exists():
                if json.loads((d / "post.json").read_text(encoding="utf-8")).get("type") == "reel":
                    continue  # reels are made by scripts/reel.py
                render_post(d)
    else:
        for a in args:
            render_post(a)
