"""Render an Romy Calloway Reel (1080x1920 MP4) from a post.json with "type": "reel".

A reel is a real excerpt from a book, read by a British AI voice, over moody background video,
with burned-in subtitles and an end card with the cover.

post.json fields (besides publish_at / pillar / caption):
    type     : "reel"
    book     : book title, e.g. "Under the Lining"
    cover    : path to the cover, e.g. assets/covers/under-the-lining.jpg
    hook     : opening line shown on screen for the first seconds (our words, not a quote)
    excerpt  : list of lines, VERBATIM from the book. A line is a string, or
               {"text": "...", "pause": 1.2, "sfx": "ring"}  (pause in seconds after the line;
               sfx "ring" = a soft electronic telephone trill during that pause)
    voice    : edge-tts voice (default en-GB-SoniaNeural)
    rate     : speaking rate (default "-6%")
    style    : "page" (default) = designed book-page video made with Remotion (video/): cream paper, the words
               turn to ink as they are read, page turns, key line in italic with a red wavy underline.
               Mark a key line in the excerpt with {"text": "...", "key": true}.
               "clips" = the older stock-footage style below.
    clips    : real stock footage from Pixabay, one clip per scene:
               [{"at": 0, "pixabay": 119507, "focus": 0.5, "start": 0, "note": "cream telephone"}, ...]
               "at" = excerpt line where the clip starts; "focus" = horizontal crop position (0 left … 1 right)
               for landscape footage; "start" = seconds to skip at the beginning of the clip.
               Choose clips by looking at them first. Without clips the background is a dark, blurred cover.
    end      : {"kicker": "Out now", "title": "...", "body": "..."}  end card text

Output in the post folder: reel.mp4, thumb.jpg (cover frame for the PR and Instagram) and
clips.json (which Pixabay clip is used where, with links, for reuse in a longer video).

Usage:
    python scripts/reel.py posts/queue/2026-10-29-under-the-lining   # one reel
    python scripts/reel.py --all        # every reel in queue/ without reel.mp4
    python scripts/reel.py --all --force

Env:
    PIXABAY_API_KEY  needed for "clips" (GitHub secret)
    REEL_FAKE_TTS=1  local test without network: silence instead of a voice
"""
import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render import BRAND, C, ROOT, block, draw_lines, font, red_line, spaced  # noqa: E402

W, H = 1080, 1920
FPS = 30
MARGIN = 90
LEAD_IN = 0.9        # seconds before the voice starts
GAP = 0.35           # default pause between lines
END_CARD = 4.5       # seconds
SUB_Y = 1180         # top of the subtitle area (stays clear of the Reels UI at the bottom)
HOOK_UNTIL = 4.2     # hook text visible until (seconds)
FAKE = os.environ.get("REEL_FAKE_TTS") == "1"
PIXABAY = os.environ.get("PIXABAY_API_KEY", "")
UA = {"User-Agent": "Mozilla/5.0 (romy-autopost)"}


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"ffmpeg failed:\n{' '.join(map(str, cmd))[:600]}\n{r.stderr[-2500:]}")
    return r.stdout


def duration(path):
    out = run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)])
    return float(out.strip())


def clean(text):
    """Fonts have no emoji glyphs."""
    return "".join(ch for ch in text if ord(ch) < 0x2190).strip()


# ---------- voice ----------

async def _tts(text, voice, rate, path):
    """Write the speech to path and return the start time (seconds) of every spoken word."""
    import edge_tts
    words = []
    com = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    with open(path, "wb") as f:
        async for chunk in com.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                words.append(chunk["offset"] / 1e7)
    return words


def speak(text, voice, rate, path):
    """Return (duration, word start times)."""
    words = []
    if FAKE:
        secs = max(1.0, len(text.split()) / 2.5)
        run(["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono", "-t", f"{secs:.2f}", str(path)])
    else:
        for attempt in range(3):
            try:
                words = asyncio.run(_tts(text, voice, rate, path))
                break
            except Exception as e:  # network hiccup: retry
                if attempt == 2:
                    sys.exit(f"edge-tts failed: {e}")
    return duration(path), words


# ---------- subtitles ----------

WEAK_END = {"the", "a", "an", "of", "to", "in", "on", "at", "and", "with", "her", "his", "my", "that", "for",
            "from", "into", "as", "if", "by", "was", "were", "had", "it", "be", "but", "or", "so"}


def chunks(text, max_chars=38):
    """Split a line into short, natural subtitle phrases: break after sentence punctuation,
    otherwise at a comma or before a weak word, and never end a phrase on 'the', 'of' …"""
    out = []
    for sent in re.split(r"(?<=[.?!:])\s+", text.strip()):
        words = sent.split()
        while words:
            if len(" ".join(words)) <= max_chars:
                out.append(" ".join(words))
                break
            best, best_score = 1, -1e9
            for k in range(1, len(words)):
                part = " ".join(words[:k])
                if len(part) > max_chars:
                    break
                rest = len(" ".join(words[k:]))
                score = len(part) / max_chars                       # longer is better
                if re.search(r"[,;’']$", words[k - 1]):
                    score += 0.6                                    # break after a comma
                if words[k - 1].lower().strip(",") in WEAK_END:
                    score -= 1.0                                    # don't end on 'the'
                if rest < 12:
                    score -= 0.8                                    # avoid a tiny orphan
                if score > best_score:
                    best, best_score = k, score
            out.append(" ".join(words[:best]))
            words = words[best:]
    return out


def text_png(path, text, kind="sans_bold", size=62, max_w=W - 2 * MARGIN, y=SUB_Y, color=None, max_h=360):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fnt, lines, lh, h = block(d, text, kind, size, max_w, max_h, spacing=1.22)
    # soft dark halo behind the text for legibility on any footage
    halo = Image.new("L", (W, H), 0)
    hd = ImageDraw.Draw(halo)
    yy = y
    for ln in lines:
        lw = d.textlength(ln, font=fnt)
        x = (W - lw) / 2
        hd.rectangle([x - 26, yy - 8, x + lw + 26, yy + lh + 4], fill=150)
        yy += lh
    halo = halo.filter(ImageFilter.GaussianBlur(22))
    img.paste(Image.new("RGBA", (W, H), (6, 8, 14, 255)), (0, 0), halo)
    d = ImageDraw.Draw(img)
    draw_lines(d, lines, fnt, lh, MARGIN, y, color or C["text"], align="center", width=W - 2 * MARGIN)
    img.save(path)


def hook_png(path, post):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    halo = Image.new("L", (W, H), 0)
    ImageDraw.Draw(halo).rectangle([0, 300, W, 940], fill=150)
    img.paste(Image.new("RGBA", (W, H), (6, 8, 14, 255)), (0, 0), halo.filter(ImageFilter.GaussianBlur(80)))
    d = ImageDraw.Draw(img)
    y = 400
    spaced(d, (MARGIN, y), f"FROM {post['book'].upper()}", font("sans_bold", 28), C["accent"], tracking=6)
    y += 80
    fnt, lines, lh, h = block(d, clean(post["hook"]), "display", 92, W - 2 * MARGIN, 420, spacing=1.08)
    y = draw_lines(d, lines, fnt, lh, MARGIN, y, C["text"]) + 34
    red_line(d, MARGIN, y)
    img.save(path)


def handle_png(path):
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    spaced(d, (MARGIN, 150), BRAND["handle"].upper(), font("sans", 24), C["muted"], tracking=3)
    img.save(path)


def end_png(path, post):
    end = post.get("end", {})
    img = Image.new("RGB", (W, H), C["background"])
    d = ImageDraw.Draw(img)
    cover = Image.open(ROOT / post["cover"]).convert("RGB")
    cover.thumbnail((640, 1000), Image.LANCZOS)
    cw, ch = cover.size
    x, y = (W - cw) // 2, 260
    shadow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(shadow).rectangle([x + 16, y + 26, x + cw + 16, y + ch + 26], fill=180)
    img.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shadow.filter(ImageFilter.GaussianBlur(30)))
    img.paste(cover, (x, y))
    ty = y + ch + 80
    if end.get("kicker"):
        spaced(d, (MARGIN, ty), end["kicker"].upper(), font("sans_bold", 28), C["accent"], tracking=6,
               center_w=W - 2 * MARGIN)
        ty += 66
    fnt, lines, lh, h = block(d, clean(end.get("title", post["book"])), "display", 76, W - 2 * MARGIN, 200)
    ty = draw_lines(d, lines, fnt, lh, MARGIN, ty, C["text"], align="center", width=W - 2 * MARGIN) + 24
    red_line(d, W // 2 - 45, ty)
    ty += 46
    if end.get("body"):
        fnt, lines, lh, h = block(d, clean(end["body"]), "sans", 38, W - 2 * MARGIN, 200, spacing=1.4)
        draw_lines(d, lines, fnt, lh, MARGIN, ty, C["muted"], align="center", width=W - 2 * MARGIN)
    spaced(d, (MARGIN, H - 200), BRAND["handle"].upper(), font("sans", 24), C["muted"], tracking=3,
           center_w=W - 2 * MARGIN)
    img.save(path)


# ---------- background ----------

def pixabay_clip(clip_id, cache):
    """Download one Pixabay video (by id) into cache; return (path, hit)."""
    if not PIXABAY:
        sys.exit("PIXABAY_API_KEY ontbreekt (GitHub secret).")
    cache.mkdir(parents=True, exist_ok=True)
    url = "https://pixabay.com/api/videos/?" + urllib.parse.urlencode({"key": PIXABAY, "id": clip_id})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                hits = json.loads(r.read())["hits"]
            break
        except Exception as e:
            if attempt == 2:
                sys.exit(f"pixabay {clip_id}: {e}")
    if not hits:
        sys.exit(f"pixabay {clip_id}: not found")
    hit = hits[0]
    v = hit["videos"]
    f = v["large"] if v.get("large", {}).get("url") and v["large"].get("width", 0) >= 1280 else v["medium"]
    dest = cache / f"pixabay-{clip_id}.mp4"
    if not dest.exists():
        with urllib.request.urlopen(urllib.request.Request(f["url"], headers=UA), timeout=300) as r:
            dest.write_bytes(r.read())
    return dest, hit


GRADE = ("eq=saturation=0.78:brightness=-0.07:contrast=1.07,"
         "colorbalance=rs=-0.03:bs=0.05:rm=-0.01:bm=0.02,"
         "noise=alls=4:allf=t,vignette=PI/4.2")


def clips_background(post, total, tmp, ev, folder):
    """Cut the chosen Pixabay clips to the timeline, crop to 9:16, grade and join them."""
    specs = post["clips"]
    starts = [0.0 if i == 0 else max(0.0, ev["lines"][c["at"]] - 0.25) for i, c in enumerate(specs)]
    ends = starts[1:] + [total]
    cache = Path(os.environ.get("REEL_CACHE", tmp / "clips"))
    parts, credits = [], []
    for i, (c, a, b) in enumerate(zip(specs, starts, ends)):
        src, hit = pixabay_clip(c["pixabay"], cache)
        seg = b - a
        nat = max(0.5, duration(src) - float(c.get("start", 0)))
        slow = min(1.6, max(1.1, seg / nat))                      # a little slower = calmer, more cinematic
        fade = 0.35
        focus = float(c.get("focus", 0.5))
        p = tmp / f"seg{i:02d}.mp4"
        run(["ffmpeg", "-y", "-ss", str(c.get("start", 0)), "-stream_loop", "-1", "-i", str(src),
             "-t", f"{seg:.3f}", "-an", "-vf",
             f"setpts={slow:.3f}*PTS,scale={W}:{H}:force_original_aspect_ratio=increase,"
             f"crop={W}:{H}:x='(iw-{W})*{focus}':y='(ih-{H})/2',fps={FPS},{GRADE},"
             f"fade=t=in:st=0:d={fade},fade=t=out:st={max(0, seg - fade):.3f}:d={fade},format=yuv420p",
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "19", str(p)])
        parts.append(p)
        credits.append({"from_line": c["at"], "seconds": [round(a, 2), round(b, 2)], "pixabay_id": hit["id"],
                        "page": hit["pageURL"], "by": hit.get("user"), "tags": hit.get("tags"),
                        "note": c.get("note", "")})
        print(f"  clip {i + 1}: pixabay {hit['id']} ({c.get('note', '')}) {a:.1f}-{b:.1f}s")
    lst = tmp / "segs.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts))
    out = tmp / "bg.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(out)])
    (folder / "clips.json").write_text(json.dumps(credits, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return out, "pixabay"


def background(post, total, tmp, ev=None, folder=None):
    if post.get("clips"):
        return clips_background(post, total, tmp, ev, folder)
    out = tmp / "bg.mp4"
    # mood fallback: the cover, heavily blurred into the navy, drifting slowly upwards
    cover = Image.open(ROOT / post["cover"]).convert("RGB")
    bw, bh = int(W * 1.12), int(H * 1.12)
    bg = ImageOps.fit(cover, (bw // 4, bh // 4), method=Image.LANCZOS).filter(ImageFilter.GaussianBlur(28))
    bg = bg.resize((bw, bh), Image.BICUBIC).filter(ImageFilter.GaussianBlur(20))
    bg = Image.blend(bg, Image.new("RGB", bg.size, C["background"]), 0.62)
    bg.save(tmp / "mood.png")
    run(["ffmpeg", "-y", "-loop", "1", "-framerate", str(FPS), "-t", f"{total:.2f}", "-i", str(tmp / "mood.png"),
         "-vf", f"crop={W}:{H}:x='(iw-{W})/2':y='(ih-{H})*(1-t/{total:.2f})',{GRADE},format=yuv420p",
         "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)])
    return out, "mood"


# ---------- audio ----------

RING = ("aevalsrc='0.22*sin(2*PI*1400*t)*(0.55+0.45*sin(2*PI*20*t))"
        "*(lt(mod(t,2.2),0.4)+gte(mod(t,2.2),0.6)*lt(mod(t,2.2),1.0))':s=48000:d={d:.2f}")


# ---------- main ----------

def render_reel(folder):
    folder = Path(folder)
    post = json.loads((folder / "post.json").read_text(encoding="utf-8"))
    voice = post.get("voice", "en-GB-SoniaNeural")
    rate = post.get("rate", "-6%")
    lines = [ln if isinstance(ln, dict) else {"text": ln} for ln in post["excerpt"]]
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        # 1. voice per line, build the timeline
        page_style = post.get("style", "page") == "page"
        t = PAGE_LEAD if page_style else LEAD_IN
        voice_parts, sfx_parts, subs, line_starts, page_lines = [], [], [], [], []
        for i, ln in enumerate(lines):
            line_starts.append(t)
            mp3 = tmp / f"line{i:02d}.mp3"
            d, words = speak(ln["text"], voice, rate, mp3)
            voice_parts.append((mp3, t))
            n_tok = len(ln["text"].split())
            abs_words = [round(t + w, 3) for w in words] if len(words) == n_tok else []
            page_lines.append({"text": ln["text"], "start": round(t, 3), "end": round(t + d, 3),
                               "words": abs_words, "key": bool(ln.get("key"))})
            pieces = chunks(clean(ln["text"]))
            n_words = sum(len(p.split()) for p in pieces)
            if words and len(words) >= n_words:      # real timing: each phrase starts with its first word
                k = 0
                for j, p in enumerate(pieces):
                    a = t + words[k]
                    k += len(p.split())
                    b = t + words[k] if k < len(words) else t + d - 0.1
                    subs.append((p, a, b))
            else:                                     # fallback: spread by length
                total_chars = sum(len(p) for p in pieces)
                st, speech = t + 0.08, max(0.4, d - 0.25)
                for p in pieces:
                    dur = speech * len(p) / total_chars
                    subs.append((p, st, st + dur))
                    st += dur
            t += d
            pause = float(ln.get("pause", GAP))
            if ln.get("sfx") == "ring":
                sfx_parts.append((t + 0.2, max(pause, 2.6)))
                pause = max(pause, 2.6) + 0.3
            t += pause
        end_start = t + 0.4
        total = end_start + END_CARD
        print(f"{folder.name}: {total:.1f}s, {len(lines)} lines, {len(subs)} subtitles")

        if page_style:
            out = render_page_video(post, folder, tmp, page_lines, sfx_parts, end_start, total)
            mux_audio(out, tmp, voice_parts, sfx_parts, total, folder)
            return folder / "reel.mp4"

        # 2. graphics
        hook_png(tmp / "hook.png", post)
        handle_png(tmp / "handle.png")
        end_png(tmp / "end.png", post)
        sub_files = []
        for i, (txt, a, b) in enumerate(subs):
            p = tmp / f"sub{i:03d}.png"
            text_png(p, txt)
            # subtitles stay until the next one starts, so they don't flicker between phrases
            nxt = subs[i + 1][1] if i + 1 < len(subs) else b
            sub_files.append((p, a, min(nxt, b + 0.6)))

        # 3. background
        bg, mode = background(post, total, tmp, {"lines": line_starts, "sfx": sfx_parts}, folder)
        print(f"  background: {mode}")

        # 4. compose video + audio
        inputs = ["-i", str(bg), "-i", str(tmp / "handle.png"),
                  "-loop", "1", "-framerate", str(FPS), "-t", f"{HOOK_UNTIL:.2f}", "-i", str(tmp / "hook.png"),
                  "-loop", "1", "-framerate", str(FPS), "-t", f"{END_CARD:.2f}", "-i", str(tmp / "end.png")]
        fv = [f"[2:v]format=rgba,fade=t=out:st={HOOK_UNTIL - 0.6:.2f}:d=0.6:alpha=1[hook]",
              f"[3:v]format=rgba,fade=t=in:st=0:d=0.7:alpha=1,setpts=PTS+{end_start:.3f}/TB[end]",
              "[0:v][1:v]overlay=0:0[v0]", "[v0][hook]overlay=0:0:eof_action=pass[v1]"]
        last, n = "v1", 4
        for i, (p, a, b) in enumerate(sub_files):
            inputs += ["-i", str(p)]
            fv.append(f"[{last}][{n}:v]overlay=0:0:enable='between(t,{a:.3f},{b:.3f})'[s{i}]")
            last, n = f"s{i}", n + 1
        fv.append(f"[{last}][end]overlay=0:0:eof_action=pass,format=yuv420p[vout]")

        fa, mix = [], []
        for i, (mp3, st) in enumerate(voice_parts):
            inputs += ["-i", str(mp3)]
            ms = int(st * 1000)
            fa.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
            mix.append(f"[a{i}]")
            n += 1
        for j, (st, d) in enumerate(sfx_parts):
            ms = int(st * 1000)
            fa.append(RING.format(d=d) + f",afade=t=out:st={d - 0.3:.2f}:d=0.3,"
                      f"aformat=channel_layouts=stereo,adelay={ms}|{ms}[r{j}]")
            mix.append(f"[r{j}]")
        # low ambient drone under everything
        fa.append(f"anoisesrc=color=brown:amplitude=0.5:r=48000:d={total:.2f},lowpass=f=260,volume=0.10,"
                  f"aformat=channel_layouts=stereo[noise]")
        fa.append(f"sine=f=55:r=48000:d={total:.2f},volume=0.05,aformat=channel_layouts=stereo[hum]")
        fa.append(f"[noise][hum]amix=inputs=2:normalize=0,afade=t=in:d=1.5,"
                  f"afade=t=out:st={total - 1.5:.2f}:d=1.5[amb]")
        mix.append("[amb]")
        fa.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=longest,"
                  f"atrim=0:{total:.2f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")

        script = tmp / "graph.txt"
        script.write_text(";\n".join(fv + fa))
        out = folder / "reel.mp4"
        run(["ffmpeg", "-y", *inputs, "-filter_complex_script", str(script),
             "-map", "[vout]", "-map", "[aout]", "-t", f"{total:.2f}", "-r", str(FPS),
             "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-maxrate", "5M", "-bufsize", "10M",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
             "-movflags", "+faststart", str(out)])
        run(["ffmpeg", "-y", "-ss", "1.6", "-i", str(out), "-frames:v", "1", "-q:v", "3",
             str(folder / "thumb.jpg")])
    mb = out.stat().st_size / 1e6
    print(f"  -> {out.relative_to(ROOT)} ({mb:.1f} MB)")
    return out


PAGE_LEAD = 3.2      # title page with the hook before the voice starts
VIDEO = ROOT / "video"


def paginate(lines, width=W - 220, max_h=1250):
    """Split the excerpt over book pages, measuring the text with the same font as the video."""
    from PIL import ImageFont
    reg = ImageFont.truetype(str(ROOT / "assets/fonts/CormorantGaramond.ttf"), 66)
    ita = ImageFont.truetype(str(ROOT / "assets/fonts/CormorantGaramond-Italic.ttf"), 66)
    for f, w in ((reg, "Medium"), (ita, "SemiBold Italic")):
        try:
            f.set_variation_by_name(w)
        except Exception:
            pass
    d = ImageDraw.Draw(Image.new("L", (10, 10)))
    page, used = 0, 0
    for ln in lines:
        f = ita if ln["key"] else reg
        rows, cur = 1, ""
        for word in ln["text"].split():
            test = f"{cur} {word}".strip()
            if d.textlength(test, font=f) * 1.03 > width and cur:
                rows, cur = rows + 1, word
            else:
                cur = test
        h = rows * 94 + 40
        if used and used + h > max_h:
            page, used = page + 1, 0
        ln["page"] = page
        used += h
    return page + 1


def render_page_video(post, folder, tmp, lines, rings, end_start, total):
    import shutil
    pages = paginate(lines)
    starts = [min(l["start"] for l in lines if l["page"] == i) - 0.2 for i in range(pages)]
    starts[0] = PAGE_LEAD - 0.4
    pub = VIDEO / "public"
    (pub / "fonts").mkdir(parents=True, exist_ok=True)
    for f in (ROOT / "assets/fonts").glob("*.ttf"):
        shutil.copy(f, pub / "fonts" / f.name)
    shutil.copy(ROOT / post["cover"], pub / "cover.jpg")
    props = {
        "book": post["book"], "author": BRAND["author"], "hook": clean(post["hook"]), "hookEnd": PAGE_LEAD - 0.2,
        "endStart": round(end_start, 3), "total": round(total, 3), "lines": lines, "pages": pages,
        "pageStarts": [round(x, 3) for x in starts], "rings": [[round(a, 3), round(b, 3)] for a, b in rings],
        "cover": "cover.jpg", "end": post.get("end", {}), "handle": BRAND["handle"],
    }
    pf = tmp / "props.json"
    pf.write_text(json.dumps(props, ensure_ascii=False))
    out = tmp / "page.mp4"
    cmd = ["npx", "remotion", "render", "src/index.ts", "BookPage", str(out), f"--props={pf}", "--muted",
           "--log=error", "--concurrency=2"]
    if os.environ.get("REMOTION_BROWSER"):
        cmd.append(f"--browser-executable={os.environ['REMOTION_BROWSER']}")
    r = subprocess.run(cmd, cwd=VIDEO, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"remotion failed:\n{r.stdout[-2000:]}\n{r.stderr[-3000:]}")
    print(f"  page video: {pages} page(s)")
    return out


def mux_audio(video, tmp, voice_parts, sfx_parts, total, folder):
    inputs, fa, mix, n = ["-i", str(video)], [], [], 1
    for i, (mp3, st) in enumerate(voice_parts):
        inputs += ["-i", str(mp3)]
        ms = int(st * 1000)
        fa.append(f"[{n}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{i}]")
        mix.append(f"[a{i}]")
        n += 1
    for j, (st, d) in enumerate(sfx_parts):
        ms = int(st * 1000)
        fa.append(RING.format(d=d) + f",afade=t=out:st={d - 0.3:.2f}:d=0.3,"
                  f"aformat=channel_layouts=stereo,adelay={ms}|{ms}[r{j}]")
        mix.append(f"[r{j}]")
    fa.append(f"anoisesrc=color=brown:amplitude=0.5:r=48000:d={total:.2f},lowpass=f=260,volume=0.08,"
              f"aformat=channel_layouts=stereo,afade=t=in:d=1.5,afade=t=out:st={total - 1.5:.2f}:d=1.5[amb]")
    mix.append("[amb]")
    fa.append(f"{''.join(mix)}amix=inputs={len(mix)}:normalize=0:duration=longest,"
              f"atrim=0:{total:.2f},loudnorm=I=-14:TP=-1.5:LRA=11,aresample=48000[aout]")
    script = tmp / "agraph.txt"
    script.write_text(";\n".join(fa))
    out = folder / "reel.mp4"
    run(["ffmpeg", "-y", *inputs, "-filter_complex_script", str(script), "-map", "0:v", "-map", "[aout]",
         "-t", f"{total:.2f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-maxrate", "6M",
         "-bufsize", "12M", "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "48000",
         "-movflags", "+faststart", str(out)])
    run(["ffmpeg", "-y", "-ss", "1.2", "-i", str(out), "-frames:v", "1", "-q:v", "3", str(folder / "thumb.jpg")])
    print(f"  -> {out} ({out.stat().st_size / 1e6:.1f} MB)")


def is_reel(folder):
    p = Path(folder) / "post.json"
    return p.exists() and json.loads(p.read_text(encoding="utf-8")).get("type") == "reel"


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    force = "--force" in args
    if "--all" in args:
        for d in sorted((ROOT / "posts" / "queue").glob("*/")):
            if is_reel(d) and (force or not (d / "reel.mp4").exists()):
                render_reel(d)
    else:
        for a in args:
            if not a.startswith("--"):
                render_reel(a)
