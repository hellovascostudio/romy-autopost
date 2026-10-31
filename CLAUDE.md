# romy-autopost

Automated Instagram posting for @romycallowaywrites (pen name Romy Calloway, warm witty romance, *Out of Office* series).
Read `brand/romy.md` before writing any content, and `plan/` for the current month plan.
Same system as hellovascostudio/isla-autopost; keep the two repos separate.

## How it works
- Each post is a folder `posts/queue/YYYY-MM-DD-slug/` with a `post.json`.
- `scripts/render.py` turns the slides into `01.jpg, 02.jpg …` (1080x1350).
- `.github/workflows/publish.yml` checks every 10 minutes (a scheduled run loops for ~5.5 h) and publishes every post whose `publish_at` has passed,
  then moves it to `posts/published/`. Never edit or delete anything in `posts/published/`.
- The repo must stay public: Instagram fetches the images from raw.githubusercontent.com.
- Only content merged into `main` gets published. New weeks always go through a pull request so Shelley approves them first.

## post.json
- `publish_at`: ISO time with offset, Europe/Amsterdam (`+01:00` in winter, `+02:00` in summer).
- `caption`: full caption incl. hashtags. ≤2200 chars, ≤30 hashtags.
- `slides`: types `cover`, `text`, `quote`, `cta`, `book` (cover image + optional kicker/title), `photo`.
  One slide = single-image post; 2–10 slides = carousel.

## Reels (book excerpts with voice-over)
- `post.json` with `"type": "reel"`: `book`, `cover`, `hook`, `excerpt` (lines), `end`, `caption`; `style` is `"page"`.
  Field details are at the top of `scripts/reel.py`.
- The reel is a designed book page (Remotion project in `video/`): cream paper, Cormorant Garamond, the words turn
  to ink as the voice reads them, pages turn, a title page with the hook and an end page with the cover.
  No stock footage, no drawn scenes. Mark the one key sentence with `"key": true` (italic + gold wavy underline).
- `excerpt` lines must be copied VERBATIM from the book. Only scenes from the first third: no spoilers. Under ~75 seconds.
- `.github/workflows/render-reels.yml` makes `reel.mp4` + `thumb.jpg` on the week branch after a push.
  Watch the result before opening the PR. In the PR, show `thumb.jpg` and link `reel.mp4`.

## Weekly routine (Sundays)
1. `git pull`. Look at `posts/published/`, `posts/queue/` and `plan/` to avoid repeats and follow the plan.
2. Check the coming week for reading moments (Christmas reads, Black Friday, Kindle deals, F1 race weekends for book 2).
3. Write 7 posts (one a day) across the pillars, at least one book spotlight per live book and one reel.
   Times: 18:30 weekdays, 10:00 weekends.
4. Branch `week-YYYY-WW`, add folders, `python scripts/render.py --all`, look at every image (text fits, no overlaps), commit, push.
5. PR titled `Week WW: <short theme>` with per post: day/time, caption, and images as
   `![](https://raw.githubusercontent.com/hellovascostudio/romy-autopost/<branch>/posts/queue/<folder>/01.jpg)`.
   End with: "Merge om deze week in te plannen. Wil je iets anders? Reageer hier of in Claude."
6. Never merge it yourself and never publish directly.
