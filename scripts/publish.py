"""Publish due posts from posts/queue/ to Instagram via the Instagram API (Instagram Login).

A post is due when post.json "publish_at" <= now. After publishing, the folder is moved to
posts/published/ (the workflow commits that move), so nothing is ever posted twice.

Env:
    IG_ACCESS_TOKEN  long-lived Instagram user token (GitHub secret)
    RAW_BASE         public base URL for repo files, e.g.
                     https://raw.githubusercontent.com/hellovascostudio/romy-autopost/main
    DRY_RUN=1        validate and print only, publish nothing

Usage:
    python scripts/publish.py           # publish everything that is due
    python scripts/publish.py --check   # only check that the token works
"""
import json
import os
import shutil
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "posts" / "queue"
DONE = ROOT / "posts" / "published"
API = "https://graph.instagram.com/v23.0"
TOKEN = os.environ.get("IG_ACCESS_TOKEN", "")
RAW_BASE = os.environ.get("RAW_BASE", "").rstrip("/")
DRY = os.environ.get("DRY_RUN") == "1"


class ApiError(Exception):
    pass


def call(method, path, **params):
    params["access_token"] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f"{API}/{path}"
    if method == "GET":
        req = urllib.request.Request(f"{url}?{data.decode()}")
    else:
        req = urllib.request.Request(url, data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace").replace(TOKEN, "***") if TOKEN else ""
        raise ApiError(f"{method} {path} -> {e.code}: {body}") from None


def wait_ready(container_id, tries=30, delay=5):
    for _ in range(tries):
        res = call("GET", container_id, fields="status_code,status")
        st = res.get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise ApiError(f"container {container_id} status {st}: {res.get('status', '')}")
        time.sleep(delay)
    raise ApiError(f"container {container_id} not ready in time")


def validate(folder, post):
    errs = []
    if not post.get("caption"):
        errs.append("caption ontbreekt")
    if len(post.get("caption", "")) > 2200:
        errs.append("caption langer dan 2200 tekens")
    if post.get("caption", "").count("#") > 30:
        errs.append("meer dan 30 hashtags")
    if post.get("type") == "reel":
        video = folder / "reel.mp4"
        if not video.exists():
            errs.append("reel.mp4 ontbreekt; draai de workflow 'Render reels' op de week-branch")
        return [video], errs
    imgs = sorted(folder.glob("[0-9][0-9].jpg"))
    if not imgs:
        errs.append("geen afbeeldingen (01.jpg ...) gevonden; draai scripts/render.py")
    if len(imgs) > 10:
        errs.append("meer dan 10 afbeeldingen in een carrousel")
    return imgs, errs


def publish(folder, post, imgs, user_id):
    rel = folder.relative_to(ROOT).as_posix()
    urls = [f"{RAW_BASE}/{urllib.parse.quote(rel)}/{p.name}" for p in imgs]
    caption = post["caption"]
    if post.get("type") == "reel":
        params = {"media_type": "REELS", "video_url": urls[0], "caption": caption, "share_to_feed": "true"}
        if (folder / "thumb.jpg").exists():
            params["cover_url"] = f"{RAW_BASE}/{urllib.parse.quote(rel)}/thumb.jpg"
        c = call("POST", f"{user_id}/media", **params)["id"]
        wait_ready(c, tries=60, delay=10)  # video processing takes a few minutes
        return call("POST", f"{user_id}/media_publish", creation_id=c)["id"]
    if len(urls) == 1:
        c = call("POST", f"{user_id}/media", image_url=urls[0], caption=caption)["id"]
    else:
        kids = []
        for u in urls:
            kid = call("POST", f"{user_id}/media", image_url=u, is_carousel_item="true")["id"]
            wait_ready(kid)
            kids.append(kid)
        c = call("POST", f"{user_id}/media", media_type="CAROUSEL", children=",".join(kids), caption=caption)["id"]
    wait_ready(c)
    return call("POST", f"{user_id}/media_publish", creation_id=c)["id"]


def main():
    if not TOKEN:
        sys.exit("IG_ACCESS_TOKEN ontbreekt (zet hem als GitHub secret).")
    me = call("GET", "me", fields="user_id,username")
    user_id = me.get("user_id") or me["id"]
    print(f"Ingelogd als @{me.get('username')}")
    if "--check" in sys.argv:
        return

    if not RAW_BASE:
        sys.exit("RAW_BASE ontbreekt.")
    now = datetime.now(timezone.utc)
    failed = False
    for folder in sorted(p for p in QUEUE.iterdir() if (p / "post.json").exists()):
        post = json.loads((folder / "post.json").read_text(encoding="utf-8"))
        when = datetime.fromisoformat(post["publish_at"])
        if when.tzinfo is None:
            print(f"! {folder.name}: publish_at mist tijdzone, overgeslagen")
            failed = True
            continue
        if when > now:
            print(f"- {folder.name}: gepland voor {when.isoformat()}")
            continue
        imgs, errs = validate(folder, post)
        if errs:
            print(f"! {folder.name}: " + "; ".join(errs))
            failed = True
            continue
        if DRY:
            print(f"[dry-run] zou {folder.name} plaatsen ({len(imgs)} afbeelding(en))")
            continue
        try:
            media_id = publish(folder, post, imgs, user_id)
        except ApiError as e:
            print(f"! {folder.name}: {e}")
            failed = True
            continue
        post["published_at"] = now.isoformat()
        post["media_id"] = media_id
        (folder / "post.json").write_text(json.dumps(post, indent=2, ensure_ascii=False), encoding="utf-8")
        DONE.mkdir(parents=True, exist_ok=True)
        shutil.move(str(folder), str(DONE / folder.name))
        print(f"+ {folder.name}: geplaatst (media {media_id})")
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
