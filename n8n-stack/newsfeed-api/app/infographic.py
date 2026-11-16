"""Morning news infographic: pick the big stories, have Gemini write Thai cards,
render them with headless Chromium, and push the PNG(s) to Telegram.

Pipeline (`build_morning`): Jev catch-up scoring -> `select_stories` ->
`write_cards` (one Gemini call) -> `render_html` -> `render_png` -> Telegram.
Any failure in the LLM/render/send steps falls back to the old text digest so
the news still arrives.

CLI preview (sends nothing):  python -m app.infographic --dry-run
"""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import subprocess
import tempfile
import time
from datetime import datetime
from io import BytesIO
from typing import Any, Literal
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, field_validator

from . import db, jevscore, notify
from .config import settings

log = logging.getLogger("infographic")

HEADLINE_MAX = 45
WHY_MAX = 60
CARDS_PER_IMAGE = 6
MIN_STORIES = 2
MAX_CANDIDATES = 25
BIG_MIN_PROB = 0.5             # Jev P(breaking) needed to count as front-page news
GEMINI_BREAKING_MIN_PROB = 0.3
# Thai national front-page news has a smaller global footprint, so Jev's
# market/world-wide 'breaking' bar is lowered for topic=thailand.
THAI_MIN_PROB = 0.35
EXCERPT_FOR_LLM = 400
IMAGE_WIDTH = 1080
OUT_DIR = "/tmp/infographic"

CATEGORIES = ("world", "markets", "tech_ai", "thailand")
CATEGORY_STYLE = {  # icon, Thai label, bar colour (CSS background)
    "world": ("🌍", "โลก", "#3b82f6"),
    "markets": ("💹", "เศรษฐกิจ-ตลาด", "#22c55e"),
    "tech_ai": ("🤖", "เทค-AI", "#a855f7"),
    "thailand": ("🇹🇭", "ไทย", "linear-gradient(#ef4444, #f5b301)"),
}
ARROW_COLOUR = {"world": "#60a5fa", "markets": "#4ade80", "tech_ai": "#c084fc", "thailand": "#fbbf24"}
THAI_DAYS = ["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์", "เสาร์", "อาทิตย์"]
THAI_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
               "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


# --------------------------------------------------------------------------- #
# Story selection
# --------------------------------------------------------------------------- #
def _prob(row: dict[str, Any], label: str) -> float:
    probs = row.get("probabilities") or {}
    if label in probs:
        return float(probs[label])
    # no probability vector: fall back to the confidence of the chosen label
    return float(row.get("confidence") or 0.0) if row.get("jev_importance") == label else 0.0


def pick_stories(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Pure selection logic over rows from `_window_rows`.

    Big = Jev P(breaking) >= BIG_MIN_PROB. Gemini 'breaking' only counts when
    Jev has no score or gives it at least GEMINI_BREAKING_MIN_PROB (Gemini
    tags analysis/opinion pieces as breaking too often). With fewer than
    MIN_STORIES big items, the highest-probability 'notable' ones fill up.
    """
    breaking = []
    for r in rows:
        p = _prob(r, "breaking")
        scored = r.get("jev_importance") is not None
        big = scored and p >= (THAI_MIN_PROB if r.get("topic") == "thailand" else BIG_MIN_PROB)
        if r.get("gemini_importance") == "breaking" and (not scored or p >= GEMINI_BREAKING_MIN_PROB):
            big = True
        if big:
            breaking.append((p if scored else 0.5, r))
    breaking.sort(key=lambda t: t[0], reverse=True)
    stories = [r for _, r in breaking[:MAX_CANDIDATES]]

    quiet_day = len(breaking) == 0
    if len(stories) < MIN_STORIES:
        taken = {r["id"] for r in stories}
        notable = [
            (_prob(r, "notable"), r) for r in rows
            if r["id"] not in taken and r.get("jev_importance") == "notable"
            and r.get("topic") != "other"
        ]
        notable.sort(key=lambda t: t[0], reverse=True)
        stories += [r for _, r in notable[: MIN_STORIES - len(stories)]]
    return {"stories": stories, "quiet_day": quiet_day}


def _window_rows(hours: int) -> list[dict[str, Any]]:
    with db.pool.connection() as conn:
        return conn.execute(
            """
            SELECT ni.id, ni.url, ni.title, ni.summary_rss, ni.published_at,
                   ni.tg_notified_at, f.name AS feed_name,
                   js.importance AS jev_importance, js.confidence, js.probabilities,
                   js.topic, js.topic_confidence,
                   CASE WHEN e.status = 'ok' THEN e.importance END AS gemini_importance
            FROM news_items ni
            JOIN feeds f ON f.id = ni.feed_id
            LEFT JOIN jev_scores js ON js.news_item_id = ni.id
            LEFT JOIN enrichments e ON e.news_item_id = ni.id
            WHERE COALESCE(ni.published_at, ni.fetched_at) > now() - make_interval(hours => %s)
            ORDER BY COALESCE(ni.published_at, ni.fetched_at) DESC
            """,
            (hours,),
        ).fetchall()


def select_stories(hours: int = 24) -> dict[str, Any]:
    """Big stories from the last `hours`, plus ids to mark notified afterwards."""
    rows = _window_rows(hours)
    picked = pick_stories(rows)
    picked["unnotified_ids"] = [r["id"] for r in rows if r["tg_notified_at"] is None]
    picked["window_items"] = len(rows)
    return picked


# --------------------------------------------------------------------------- #
# Cards (one Gemini call)
# --------------------------------------------------------------------------- #
class Card(BaseModel):
    ids: list[int]
    category: Literal["world", "markets", "tech_ai", "thailand"]
    breaking: bool = False
    headline_th: str
    why_th: str

    @field_validator("headline_th", "why_th")
    @classmethod
    def _strip(cls, v: str) -> str:
        return v.strip()


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def normalize_card(card: Card) -> Card:
    """Safety net for over-long text; every why line starts with '→'."""
    why = card.why_th.lstrip("→ ").strip()
    return card.model_copy(update={
        "headline_th": _truncate(card.headline_th, HEADLINE_MAX),
        "why_th": _truncate("→ " + why, WHY_MAX),
    })


CARDS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "cards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "ids": {"type": "array", "items": {"type": "integer"}},
                    "category": {"type": "string", "enum": list(CATEGORIES)},
                    "breaking": {"type": "boolean"},
                    "headline_th": {"type": "string"},
                    "why_th": {"type": "string"},
                },
                "required": ["ids", "category", "breaking", "headline_th", "why_th"],
            },
        }
    },
    "required": ["cards"],
}

CARDS_PROMPT = f"""\
You write a morning news infographic for an ordinary Thai reader. Input: a JSON
list of news items (id, source, topic_hint, title, excerpt). Output: JSON
{{"cards": [...]}} where each card is one story.

Rules:
- Merge items that cover the same story (several outlets, same event) into ONE
  card; `ids` lists every merged item id. Each id appears in at most one card.
- Write in Thai. Keep English only for proper names, tickers and terms with no
  good Thai equivalent (e.g. Nvidia, Fed, OpenAI).
- `headline_th`: short punchy Thai headline, at most {HEADLINE_MAX} characters
  (count carefully; aim for 25-40).
- `why_th`: one line, HARD limit {WHY_MAX} characters including the arrow (aim
  for 35-50, count carefully), starting with "→ ", saying
  what this means for an ordinary Thai reader (cost of living, savings, jobs,
  safety, tech they use...).
- `category`: world | markets | tech_ai | thailand (topic_hint is a hint only).
- `breaking`: true only for genuinely front-page, market-wide or world-level news.
- Use ONLY facts in the given text. No predictions, no investment advice, no
  buy/sell calls, no price targets.
- Order cards by importance, most important first. Skip items that are not
  real news (reviews, deals, how-tos) unless nothing else is left.
"""


def _story_payload(stories: list[dict[str, Any]]) -> str:
    return json.dumps(
        [
            {
                "id": s["id"],
                "source": s.get("feed_name"),
                "topic_hint": s.get("topic"),
                "title": s["title"],
                "excerpt": jevscore.clean_excerpt(s.get("summary_rss"), EXCERPT_FOR_LLM),
            }
            for s in stories
        ],
        ensure_ascii=False,
    )


def _parse_cards(text: str, valid_ids: set[int]) -> list[Card]:
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    raw = json.loads(text)
    items = raw["cards"] if isinstance(raw, dict) else raw
    cards: list[Card] = []
    seen: set[int] = set()
    for entry in items:
        card = Card.model_validate(entry)
        ids = [i for i in card.ids if i in valid_ids and i not in seen]
        if not ids or not card.headline_th or not card.why_th:
            continue
        seen.update(ids)
        cards.append(normalize_card(card.model_copy(update={"ids": ids})))
    if not cards:
        raise ValueError("model returned no usable cards")
    return cards


def _generate(model: str, payload: str) -> str:
    from google.genai import types

    from .enrich import _get_gemini_client

    gemma = model.startswith("gemma")
    prompt = CARDS_PROMPT + ("\nReturn ONLY the JSON object, no prose.\n" if gemma else "")
    cfg: dict[str, Any] = {"temperature": 0.2, "max_output_tokens": 4096}
    if not gemma:  # gemma has no JSON mode / system instruction
        cfg["system_instruction"] = prompt
        cfg["response_mime_type"] = "application/json"
        cfg["response_schema"] = CARDS_SCHEMA
    contents = payload if not gemma else f"{prompt}\nItems:\n{payload}"
    response = _get_gemini_client().models.generate_content(
        model=model, contents=contents, config=types.GenerateContentConfig(**cfg)
    )
    if not response.text:
        raise ValueError("model returned no text")
    return response.text


def write_cards(stories: list[dict[str, Any]]) -> tuple[list[Card], str]:
    """One Gemini call; tries `settings.card_models` in order. Returns (cards, model)."""
    payload = _story_payload(stories)
    valid_ids = {s["id"] for s in stories}
    errors = []
    for model in [m.strip() for m in settings.card_models.split(",") if m.strip()]:
        try:
            return _parse_cards(_generate(model, payload), valid_ids), model
        except Exception as exc:  # noqa: BLE001 - try the next model
            log.warning("card model %s failed: %s", model, str(exc)[:200])
            errors.append(f"{model}: {str(exc)[:120]}")
    raise RuntimeError("all card models failed: " + " | ".join(errors))


# --------------------------------------------------------------------------- #
# HTML / PNG
# --------------------------------------------------------------------------- #
def thai_date(dt: datetime) -> str:
    return f"{THAI_DAYS[dt.weekday()]} {dt.day} {THAI_MONTHS[dt.month - 1]} {dt.year + 543}"


_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { width: 1080px; background: #0f1115; color: #f3f4f6; padding: 56px 48px 40px;
  font-family: 'Noto Sans Thai', 'Noto Sans Thai UI', 'Loma', sans-serif, 'Noto Color Emoji'; }
.head { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 14px; }
.title { font-size: 68px; font-weight: 800; }
.date { font-size: 34px; color: #9ca3af; }
.count { font-size: 30px; color: #6b7280; margin-bottom: 36px; }
.quiet { font-size: 40px; font-weight: 700; color: #fbbf24; margin-bottom: 36px; }
.card { display: flex; background: #1a1d24; border-radius: 28px; margin-bottom: 28px; overflow: hidden; }
.bar { width: 18px; flex: none; }
.body { padding: 30px 36px 32px; flex: 1; }
.meta { display: flex; align-items: center; gap: 14px; font-size: 30px; color: #9ca3af; margin-bottom: 14px; }
.icon { font-size: 36px; }
.badge { background: rgba(220,38,38,.18); border: 2px solid #ef4444; color: #fca5a5; font-weight: 700;
  font-size: 26px; padding: 0 16px; border-radius: 999px; }
.headline { font-size: 50px; font-weight: 800; line-height: 1.34; margin-bottom: 14px; text-wrap: balance; }
.why { font-size: 36px; line-height: 1.45; color: #c3c8d2; text-wrap: pretty; }
.arrow { font-weight: 800; margin-right: 10px; }
.foot { margin-top: 30px; font-size: 28px; color: #6b7280; text-align: center; }
"""


def render_html(cards: list[Card], date_label: str, quiet_day: bool = False,
                page: int = 1, pages: int = 1) -> str:
    """One image's worth of cards (callers chunk by CARDS_PER_IMAGE)."""
    esc = html.escape
    page_note = f" ({page}/{pages})" if pages > 1 else ""
    parts = [
        f"<!doctype html><html lang='th'><head><meta charset='utf-8'><style>{_CSS}</style></head><body>",
        f"<div class='head'><div class='title'>ข่าวเช้า{esc(page_note)}</div>"
        f"<div class='date'>{esc(date_label)}</div></div>",
    ]
    if quiet_day and page == 1:
        parts.append("<div class='quiet'>วันนี้ไม่มีข่าวใหญ่</div>")
    else:
        parts.append(f"<div class='count'>{len(cards)} เรื่องสำคัญ</div>")
    for c in cards:
        icon, label, colour = CATEGORY_STYLE[c.category]
        badge = "<span class='badge'>🔴 ด่วน</span>" if c.breaking else ""
        parts.append(
            f"<div class='card'><div class='bar' style='background:{colour}'></div><div class='body'>"
            f"<div class='meta'><span class='icon'>{icon}</span><span>{esc(label)}</span>{badge}</div>"
            f"<div class='headline'>{esc(c.headline_th)}</div>"
            f"<div class='why'><span class='arrow' style='color:{ARROW_COLOUR[c.category]}'>→</span>"
            f"{esc(c.why_th.lstrip('→ ').strip())}</div></div></div>"
        )
    if page == pages:
        parts.append("<div class='foot'>อ่านทั้งหมด: newsfeed</div>")
    parts.append("</body></html>")
    return "".join(parts)


def build_pages(cards: list[Card], date_label: str, quiet_day: bool) -> list[str]:
    chunks = [cards[i:i + CARDS_PER_IMAGE] for i in range(0, len(cards), CARDS_PER_IMAGE)] or [[]]
    return [render_html(ch, date_label, quiet_day, n, len(chunks)) for n, ch in enumerate(chunks, 1)]


def _crop_to_content(png: bytes, pad: int = 36) -> bytes:
    from PIL import Image, ImageChops

    img = Image.open(BytesIO(png)).convert("RGB")
    bg = Image.new("RGB", img.size, img.getpixel((0, img.height - 1)))
    bbox = ImageChops.difference(img, bg).getbbox()
    bottom = min(img.height, (bbox[3] if bbox else img.height) + pad)
    out = BytesIO()
    img.crop((0, 0, img.width, bottom)).save(out, "PNG", optimize=True)
    return out.getvalue()


def render_png(pages: str | list[str], cards_per_page: int = CARDS_PER_IMAGE) -> list[bytes]:
    """Render each HTML page with headless Chromium and crop the empty bottom."""
    if isinstance(pages, str):
        pages = [pages]
    out: list[bytes] = []
    with tempfile.TemporaryDirectory(prefix="infographic-") as tmp:
        for n, page in enumerate(pages):
            src, dst = os.path.join(tmp, f"p{n}.html"), os.path.join(tmp, f"p{n}.png")
            with open(src, "w", encoding="utf-8") as fh:
                fh.write(page)
            height = 500 + cards_per_page * 760  # generous; cropped afterwards
            cmd = [
                "chromium", "--headless=new", "--no-sandbox", "--disable-gpu",
                "--disable-dev-shm-usage", "--hide-scrollbars", "--force-device-scale-factor=1",
                "--single-process", "--no-zygote", f"--user-data-dir={tmp}/profile",
                f"--window-size={IMAGE_WIDTH},{height}", f"--screenshot={dst}", f"file://{src}",
            ]
            proc = subprocess.run(cmd, capture_output=True, timeout=60)
            if not os.path.exists(dst):
                raise RuntimeError(f"chromium produced no screenshot: {proc.stderr.decode()[-300:]}")
            with open(dst, "rb") as fh:
                out.append(_crop_to_content(fh.read()))
    return out


# --------------------------------------------------------------------------- #
# Telegram
# --------------------------------------------------------------------------- #
_API = "https://api.telegram.org/bot{token}/{method}"


def _post(method: str, data: dict[str, Any], files: dict[str, Any]) -> None:
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        raise notify.TelegramError("TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID is not set")
    last: Exception | None = None
    for attempt in range(3):
        try:
            resp = httpx.post(
                _API.format(token=settings.telegram_bot_token, method=method),
                data=data, files=files, timeout=60.0,
            )
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            last = notify.TelegramRetryable(f"network error: {exc}")
        except httpx.HTTPError as exc:
            # the request may already have reached Telegram: retrying could double-send
            raise notify.TelegramError(f"network error after send: {exc}") from exc
        else:
            if resp.status_code == 200:
                return
            err = f"telegram {resp.status_code}: {resp.text[:300]}"
            if resp.status_code != 429 and resp.status_code < 500:
                raise notify.TelegramError(err)
            last = notify.TelegramRetryable(err)
        time.sleep(2 * (attempt + 1))
    raise last  # type: ignore[misc]


def send_photo(png: bytes, caption: str) -> None:
    _post("sendPhoto",
          {"chat_id": settings.telegram_chat_id, "caption": caption, "parse_mode": "HTML"},
          {"photo": ("morning.png", png, "image/png")})


def send_album(pngs: list[bytes], caption: str) -> None:
    media, files = [], {}
    for i, png in enumerate(pngs):
        item: dict[str, Any] = {"type": "photo", "media": f"attach://p{i}"}
        if i == 0:
            item.update(caption=caption, parse_mode="HTML")
        media.append(item)
        files[f"p{i}"] = (f"morning{i}.png", png, "image/png")
    _post("sendMediaGroup",
          {"chat_id": settings.telegram_chat_id, "media": json.dumps(media)}, files)


def make_caption(date_label: str, n_cards: int) -> str:
    url = html.escape(settings.newsfeed_web_url)
    return f"📰 ข่าวเช้า {html.escape(date_label)} · {n_cards} เรื่อง\n👉 {url}"


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _fallback_text_digest(dry_run: bool) -> dict[str, Any]:
    """The old text digest over all unnotified items."""
    items = db.select_unnotified(limit=settings.digest_max_items, enriched_only=False)
    if not items:
        # never stay silent: an empty morning usually means ingest is broken
        if not dry_run:
            notify.send_telegram("📰 ข่าวเช้า: ไม่มีข่าวใหม่ใน 24 ชม. (ระบบดึงข่าวอาจเสีย)")
        return {"messages": 0 if dry_run else 1, "items": 0}
    label = datetime.now(ZoneInfo(settings.digest_tz)).strftime("%a %d %b")
    messages = notify.format_digest(items, web_url=settings.newsfeed_web_url, date_label=label)
    if dry_run:
        return {"messages": len(messages), "items": len(items)}
    sent = notify.send_all(messages)
    return {"messages": sent, "items": db.mark_notified([i["id"] for i in items])}


def build_morning(dry_run: bool = False) -> dict[str, Any]:
    now = datetime.now(ZoneInfo(settings.digest_tz))
    date_label = thai_date(now)
    result: dict[str, Any] = {"date": date_label, "dry_run": dry_run, "fallback": False}
    result["jev"] = jevscore.score_pending(hours=48)

    try:
        sel = select_stories(24)
        result.update(window_items=sel["window_items"], quiet_day=sel["quiet_day"],
                      candidates=len(sel["stories"]))
        if not sel["stories"]:
            raise RuntimeError(f"no stories ({sel['window_items']} items in window)")

        cards, model = write_cards(sel["stories"])
        if not cards:
            raise RuntimeError(f"{model} returned no cards")
        pngs = render_png(build_pages(cards, date_label, sel["quiet_day"]))
        result.update(model=model, cards=[c.model_dump() for c in cards])

        if dry_run:
            os.makedirs(OUT_DIR, exist_ok=True)
            stamp = now.strftime("%Y%m%d-%H%M%S")
            paths = []
            for n, png in enumerate(pngs, 1):
                path = f"{OUT_DIR}/morning-{stamp}-{n}.png"
                with open(path, "wb") as fh:
                    fh.write(png)
                paths.append(path)
            return {**result, "files": paths, "sent": False}

        caption = make_caption(date_label, len(cards))
        if len(pngs) == 1:
            send_photo(pngs[0], caption)
        else:
            send_album(pngs, caption)
    except Exception as exc:  # noqa: BLE001 - news must still arrive
        log.exception("infographic failed, falling back to text digest")
        result.update(fallback=True, error=str(exc)[:300])
        result["text_digest"] = _fallback_text_digest(dry_run)
        return result

    try:
        marked = db.mark_notified(sel["unnotified_ids"])
    except Exception:  # noqa: BLE001 - already sent; never turn this into a resend
        log.exception("mark_notified failed after send")
        marked = -1
    return {**result, "sent": True, "images": len(pngs), "marked": marked}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the morning infographic")
    parser.add_argument("--dry-run", action="store_true", help="render PNGs, send nothing")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    db.pool.open()
    try:
        out = build_morning(dry_run=args.dry_run or False)
    finally:
        db.pool.close()
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))


if __name__ == "__main__":
    main()
