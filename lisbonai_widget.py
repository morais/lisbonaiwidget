#!/usr/bin/env python3
"""Publish the Lisbon AI 2026 programme to 00Widget.

Two surfaces, from one schedule:
  - a Live Activity: what is on stage now, what is next, counting down (Lock Screen)
  - a card: the current talk with its abstract from lisbonai.org/talks (Home Screen)

  ./lisbonai_widget.py --day 1 --watch          # run it for real, all day
  ./lisbonai_widget.py --day 1 --at 14:40       # one push, pretending it is 14:40
  ./lisbonai_widget.py --day 1 --now-is 14:40   # ...with the clock slid to match
  ./lisbonai_widget.py --day 1 --end

Talk-level times are estimates: lisbonai.org publishes times per block, so the
talks inside a block are spread evenly across it. See schedule.json.
"""

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import unicodedata
import urllib.request
from datetime import datetime, timedelta

ROOT = pathlib.Path(__file__).resolve().parent
DEEP_LINK = "https://lisbonai.org/schedule/"
CARD_ID = "lisbonai-now"
ROWS = 4                  # current + next 3; the Lock Screen draws 3 and "+1 more"
HEARTBEAT = 10 * 60       # push at least this often, so staleAt stays ahead
POLL = 20                 # how often --watch re-evaluates the schedule
# iOS ends a Live Activity after about 8 hours of runtime, and a conference day
# is longer than that. Restart before the system does it for us — preferably on
# a break, since a restart is a visible dismiss-and-reappear.
RESTART_PREFERRED = 6.5 * 3600
RESTART_FORCED = 7.5 * 3600


# ---------------------------------------------------------------- environment

def load_env():
    """Read .env (gitignored) into a dict, letting the real environment win."""
    env = {}
    path = ROOT / ".env"
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    env.update({k: v for k, v in os.environ.items() if k.startswith("WIDGET_")})
    if not env.get("WIDGET_TOKEN"):
        sys.exit("No WIDGET_TOKEN. Copy .env.example to .env and put your token in it.")
    env.setdefault("WIDGET_BASE_URL", "https://api.00widget.com")
    return env


# ------------------------------------------------------------------ schedule

def fold(name):
    """Normalise a speaker name so 'Oguz Gultepe' joins 'Oğuz Gültepe'."""
    stripped = unicodedata.normalize("NFKD", name)
    return "".join(c for c in stripped if not unicodedata.combining(c)).lower().strip()


def load_abstracts():
    """Map folded speaker name -> talks.json entry. Missing file is not fatal."""
    path = ROOT / "talks.json"
    if not path.exists():
        return {}
    return {fold(t["speaker"]): t for t in json.loads(path.read_text())["talks"]}


def day_date(day_number):
    """The day's own calendar date, as published."""
    data = json.loads((ROOT / "schedule.json").read_text())
    day = next((d for d in data["days"] if d["day"] == day_number), None)
    if day is None:
        sys.exit(f"No day {day_number} in schedule.json")
    return datetime.strptime(day["date"], "%Y-%m-%d").date()


def build_timeline(day_number, anchor_date, offset=timedelta(0)):
    """Flatten a schedule day into segments carrying real datetimes.

    anchor_date is the calendar date the times are hung on, which is how a
    dry run tomorrow can display the real day-1 programme.
    """
    data = json.loads((ROOT / "schedule.json").read_text())
    day = next((d for d in data["days"] if d["day"] == day_number), None)
    if day is None:
        sys.exit(f"No day {day_number} in schedule.json")

    def at(hhmm):
        h, m = (int(x) for x in hhmm.split(":"))
        return (datetime.combine(anchor_date, datetime.min.time())
                + timedelta(hours=h, minutes=m) + offset)

    segments = []
    for block in day["blocks"]:
        start, end = at(block["start"]), at(block["end"])
        if block["kind"] == "break":
            segments.append({
                "kind": "break",
                "start": start,
                "end": end,
                "label": block["title"],
                "sub": block.get("subtitle", ""),
                "track": "",
                "start_exact": True,
                "end_exact": True,
            })
            continue
        talks = block["talks"]
        span = (end - start) / len(talks)
        for i, talk in enumerate(talks):
            segments.append({
                "kind": "talk",
                "start": start + span * i,
                "end": end if i == len(talks) - 1 else start + span * (i + 1),
                "label": talk["short"],
                "sub": f"{talk['speaker']} · {talk['org']}",
                "title": talk["title"],
                "track": block["track"],
                # only the block's own edges are published; the splits inside it are ours
                "start_exact": i == 0,
                "end_exact": i == len(talks) - 1,
            })
    abstracts = load_abstracts()
    for seg in segments:
        if seg["kind"] == "talk":
            seg["detail"] = abstracts.get(fold(seg["sub"].split(" · ")[0]))
    segments.sort(key=lambda s: s["start"])
    return day, segments


def where_are_we(segments, now):
    current = next((s for s in segments if s["start"] <= now < s["end"]), None)
    upcoming = [s for s in segments if s["start"] >= now]
    return current, upcoming


# ---------------------------------------------------------------- the payload

TRACK_ICON = {
    "Models": "cube.transparent",
    "Agents": "cpu",
    "Applied AI": "wrench.and.screwdriver",
    "Evals": "checkmark.seal",
    "Security": "lock.shield",
}


def hhmm(dt):
    return dt.strftime("%H:%M")


def starts(segment):
    """A segment's start time, marked ~ when we derived it rather than read it."""
    return ("" if segment["start_exact"] else "~") + hhmm(segment["start"])


def ends(segment):
    return ("" if segment["end_exact"] else "~") + hhmm(segment["end"])


def row(segment, now, index):
    """One item row: what it is, who is giving it, when it starts."""
    running = segment["start"] <= now < segment["end"]
    item = {
        "id": f"slot-{index}",
        "title": segment["label"][:40],
        "subtitle": segment["sub"] or f"{starts(segment)}–{ends(segment)}",
        "value": "now" if running else starts(segment),
        "status": "running" if running else "unknown",
    }
    if segment["kind"] == "talk":
        item["icon"] = TRACK_ICON.get(segment["track"], "mic")
        if running:
            item["statusIcon"] = "waveform"
            item["progress"] = round(
                (now - segment["start"]).total_seconds()
                / max((segment["end"] - segment["start"]).total_seconds(), 1), 3)
    else:
        item["icon"] = "cup.and.saucer" if "coffee" in segment["label"].lower() else "sparkles"
    return item


def content_state(segments, now, next_push):
    """The whole updatable half of the activity for this moment."""
    current, upcoming = where_are_we(segments, now)
    day_start, day_end = segments[0]["start"], segments[-1]["end"]

    shown = ([current] if current else []) + [s for s in upcoming if s is not current]
    items = [row(s, now, i) for i, s in enumerate(shown[:ROWS])]

    state = {
        "items": items,
        "staleAt": iso(next_push + timedelta(minutes=3)),
        "progress": clamp((now - day_start).total_seconds()
                          / max((day_end - day_start).total_seconds(), 1)),
        "countdownGranularity": "minute",
    }

    if now < day_start:                                   # before doors
        state.update({
            "state": "Starts soon",
            "value": "Soon",
            "subtitle": f"Doors {hhmm(day_start)} · first talk "
                        f"{starts(next(s for s in segments if s['kind'] == 'talk'))}",
            "endsAt": iso(day_start),
            "signal": "neutral",
            "statusIcon": None,
            "relevanceScore": 10,
            "progress": None,
        })
    elif current is None:                                 # day is done
        state.update({
            "state": "Wrapped",
            "value": "Done",
            "subtitle": "That is a wrap for today",
            "endsAt": None,
            "signal": "neutral",
            "statusIcon": None,
            "relevanceScore": 5,
            "items": [],
            "progress": 1.0,
        })
    elif current["kind"] == "talk":                       # someone is on stage
        nxt = upcoming[0] if upcoming else None
        state.update({
            "state": f"{current['track']} track",
            "value": current["track"][:10],
            "subtitle": ellipsis(current["title"], 78),
            "endsAt": iso(current["end"]),
            "signal": "favorable",
            "statusIcon": "waveform",
            "relevanceScore": 100,
        })
    else:                                                 # break, lunch, party
        nxt = upcoming[0] if upcoming else None
        state.update({
            "state": current["label"],
            "value": "Break",
            "subtitle": ellipsis(
                (current["sub"] + " · " if current["sub"] else "")
                + (f"Next: {nxt['label']} {starts(nxt)}" if nxt else "Last session done"), 78),
            "endsAt": iso(current["end"]),
            "signal": "neutral",
            "statusIcon": "cup.and.saucer",
            "relevanceScore": 30,
        })

    return state, current, upcoming


def ellipsis(text, limit):
    return text if len(text) <= limit else text[:limit - 1].rstrip(" ,.;:—-") + "…"


def clamp(x):
    return round(min(max(x, 0.0), 1.0), 3)


def iso(dt):
    return dt.astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")[:-2] + ":00"


# ------------------------------------------------------------------ the card

SECTION_LIMIT = 500   # the card API's per-section ceiling


def paragraphs(abstract, limit=SECTION_LIMIT):
    """Abstract paragraphs, split on sentence boundaries to fit a card section."""
    out = []
    for para in abstract:
        while len(para) > limit:
            cut = max(para.rfind(". ", 0, limit), para.rfind("? ", 0, limit),
                      para.rfind("! ", 0, limit))
            if cut < limit // 3:                      # no sentence break to use
                cut = para.rfind(" ", 0, limit - 1)
            out.append(para[:cut + 1].strip())
            para = para[cut + 1:].strip()
        if para:
            out.append(para)
    return out


def build_card(segments, now, day_number, next_push):
    """A briefing card: the talk on stage, with its abstract from the talks page.

    A card is standing state the operator checks on, so it says what is
    happening now and carries the prose the Lock Screen has no room for.
    """
    current, upcoming = where_are_we(segments, now)
    nxt = next((s for s in upcoming if s is not current), None)
    card = {
        "id": CARD_ID,
        "template": "briefing",
        "title": "Lisbon AI",
        "producer": {"label": "Lisbon AI schedule", "icon": "calendar"},
        "deepLink": DEEP_LINK,
        "staleAfter": iso(next_push + timedelta(minutes=30)),
        "priority": 10,  # ahead of the household cards while the conference runs
    }

    if current and current["kind"] == "talk":
        detail = current.get("detail") or {}
        slot = f"{starts(current)}–{ends(current)}"
        sections = [{"id": "talk", "label": f"{current['track']} · {slot}",
                     "text": current["title"]}]
        for i, para in enumerate(paragraphs(detail.get("abstract", []))):
            sections.append({"id": f"abstract-{i}", "text": para})
        if nxt:
            sections.append({"id": "next", "label": f"Next · {starts(nxt)}",
                             "text": f"{nxt['label']}" + (f" — {nxt['sub']}" if nxt["kind"] == "talk" else "")})
        card.update({
            "value": current["label"],
            "subtitle": current["sub"],
            "status": "running",
            "icon": TRACK_ICON.get(current["track"], "mic"),
            "statusIcon": "waveform",
            "deadline": iso(current["end"]),
            "deepLink": detail.get("url", DEEP_LINK),
            "staleAfter": iso(current["end"] + timedelta(minutes=45)),
            "briefing": {"sections": sections[:6]},
        })
        return card

    if current:                                            # break, lunch, party
        sections = []
        if nxt and nxt["kind"] == "talk":
            detail = nxt.get("detail") or {}
            sections.append({"id": "next", "label": f"Next · {starts(nxt)}",
                             "text": f"{nxt['title']} — {nxt['sub']}"})
            for i, para in enumerate(paragraphs(detail.get("abstract", []))[:2]):
                sections.append({"id": f"abstract-{i}", "text": para})
        card.update({
            "value": current["label"],
            "subtitle": (f"Until {ends(current)}" if not current["sub"] else current["sub"]),
            "status": "paused",
            "icon": "cup.and.saucer",
            "deadline": iso(current["end"]),
            "staleAfter": iso(current["end"] + timedelta(minutes=45)),
            "briefing": {"sections": sections or [{"id": "info", "text": "Nothing on stage right now."}]},
        })
        return card

    day_start = segments[0]["start"]
    before = now < day_start
    first = next(s for s in segments if s["kind"] == "talk")
    card.update({
        "value": (f"Day {day_number} · {day_start.strftime('%a %d %b')}" if before
                  else f"Day {day_number} wrapped"),
        "subtitle": (f"Doors {hhmm(day_start)} · first talk {starts(first)}" if before
                     else "See you tomorrow"),
        "status": "unknown" if before else "finished",
        "icon": "calendar",
        "briefing": {"sections": [{"id": "first", "label": "Opens with",
                                   "text": f"{first['title']} — {first['sub']}"}]} if before else
                    {"sections": [{"id": "done", "text": "The programme is over for today."}]},
    })
    if before:
        card["deadline"] = iso(day_start)
        card["staleAfter"] = iso(day_start + timedelta(hours=1))
    else:
        card["staleAfter"] = iso(now + timedelta(hours=12))
    return card


# --------------------------------------------------------------------- client

def call(env, path, body, dry_run=False):
    url = env["WIDGET_BASE_URL"].rstrip("/") + path
    payload = json.dumps(body).encode()
    if dry_run:
        print(f"DRY RUN POST {path}\n{json.dumps(body, indent=2, ensure_ascii=False)}")
        return {"ok": True, "dryRun": True}
    req = urllib.request.Request(url, data=payload, method="POST", headers={
        "Authorization": f"Bearer {env['WIDGET_TOKEN']}",
        "Content-Type": "application/json",
        # urllib's default agent is refused by the edge in front of the API (403 / 1010)
        "User-Agent": "lisbonai-widget/1.0",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"{path} failed: HTTP {e.code} {e.read().decode()[:400]}")


def activity_id(day):
    return f"lisbonai-2026-day{day}"


def publish(env, day_number, day, segments, now, started, dry_run, with_card=True):
    next_push = now + timedelta(seconds=HEARTBEAT)
    state, current, upcoming = content_state(segments, now, next_push)
    state["externalActivityId"] = activity_id(day_number)

    if started:
        result = call(env, "/v1/live-activities/update", state, dry_run)
    else:
        state = {k: v for k, v in state.items() if v is not None}
        state.update({
            "kind": "timer",
            "title": f"Lisbon AI · Day {day_number}",
            "icon": "mic.fill",
            "deepLink": DEEP_LINK,
        })
        result = call(env, "/v1/live-activities/start", state, dry_run)
        if result.get("pushToStartAttempted") == 0:
            sys.exit("No device has registered for Live Activities — install 00Widget "
                     "and allow notifications, nothing published will be seen.")

    if with_card:
        call(env, "/v1/cards/upsert", build_card(segments, now, day_number, next_push), dry_run)

    here = current["label"] if current else "—"
    print(f"[{hhmm(now)}] {'update' if started else 'start '} · {here} · "
          f"next: {', '.join(s['label'] for s in upcoming[:2]) or '—'}"
          + (f" · warnings: {result['warnings']}" if result.get("warnings") else ""))
    return current, upcoming


def finish(env, day_number, dry_run, subtitle="Day wrapped — see you tomorrow"):
    call(env, "/v1/live-activities/end", {
        "externalActivityId": activity_id(day_number),
        "finalState": "Wrapped",
        "finalSubtitle": subtitle,
        "finalValue": "Done",
        "finalProgress": 1,
        "finalEndsAt": None,
        "finalItems": [],
        "finalStatusIcon": None,
        "finalSignal": "favorable",
        "dismissalDate": iso(datetime.now() + timedelta(minutes=30)),
    }, dry_run)
    print("ended")


# ------------------------------------------------------------------------ cli

def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--day", type=int, default=1, help="which conference day's programme to show")
    p.add_argument("--at", metavar="HH:MM", help="pretend it is this time of day")
    p.add_argument("--now-is", metavar="HH:MM", dest="now_is",
                   help="slide the whole programme so this moment lands on the real clock; "
                        "the only way a demo gets an honest countdown on the device")
    p.add_argument("--date", metavar="YYYY-MM-DD", help="hang the programme on this date (default: today)")
    p.add_argument("--offset", type=float, metavar="HOURS",
                   help="shift the programme from its real date by this many hours; "
                        "negative runs it early, so --offset -24 rehearses day 1 a day ahead")
    p.add_argument("--watch", action="store_true", help="keep it honest: push at every change until the day ends")
    p.add_argument("--speed", type=float, default=1.0, help="with --watch, run the clock this many times faster (demo)")
    p.add_argument("--poll", type=float, default=POLL, metavar="SECONDS",
                   help="with --watch, how often to re-check the schedule")
    p.add_argument("--update", action="store_true",
                   help="push to the already-running activity instead of starting one "
                        "(a start on a live id restarts it, which the user sees)")
    p.add_argument("--no-card", action="store_true", dest="no_card",
                   help="publish only the Live Activity, leaving the Home Screen card alone")
    p.add_argument("--card-only", action="store_true", dest="card_only",
                   help="publish only the card (no Lock Screen banner)")
    p.add_argument("--end", action="store_true", help="end the activity now")
    p.add_argument("--dry-run", action="store_true", help="print what would be pushed")
    args = p.parse_args()

    env = load_env()
    if args.end:
        return finish(env, args.day, args.dry_run, "Ended by hand")

    if args.offset is not None and not args.date:
        anchor = day_date(args.day)          # shift from the real date, not from today
    elif args.date:
        anchor = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        anchor = datetime.now().date()
    offset = timedelta(hours=args.offset) if args.offset is not None else timedelta(0)
    if args.now_is:
        h, m = (int(x) for x in args.now_is.split(":"))
        offset = datetime.now() - (datetime.combine(anchor, datetime.min.time())
                                   + timedelta(hours=h, minutes=m))
        args.at = None  # the real clock is the point
    day, segments = build_timeline(args.day, anchor, offset)

    def clock(elapsed=0.0):
        base = datetime.now()
        if args.at:
            h, m = (int(x) for x in args.at.split(":"))
            base = datetime.combine(anchor, datetime.min.time()) + timedelta(hours=h, minutes=m)
        return base + timedelta(seconds=elapsed * args.speed)

    now = clock()
    if args.card_only:
        call(env, "/v1/cards/upsert",
             build_card(segments, now, args.day, now + timedelta(seconds=HEARTBEAT)), args.dry_run)
        current, _ = where_are_we(segments, now)
        print(f"[{hhmm(now)}] card   · {current['label'] if current else '—'}")
        return
    current, _ = publish(env, args.day, day, segments, now, started=args.update,
                         dry_run=args.dry_run, with_card=not args.no_card)

    if not args.watch:
        return

    began = time.monotonic()
    last_key, last_push, activity_began = key(current), now, time.monotonic()
    try:
        while True:
            time.sleep(args.poll)
            now = clock(time.monotonic() - began)
            if now >= segments[-1]["end"]:
                break
            current, _ = where_are_we(segments, now)
            changed = key(current) != last_key
            running_for = (time.monotonic() - activity_began) * args.speed
            expiring = (running_for > RESTART_FORCED
                        or (running_for > RESTART_PREFERRED
                            and current is not None and current["kind"] == "break"))
            if changed or expiring or (now - last_push).total_seconds() >= HEARTBEAT:
                if expiring:
                    print(f"[{hhmm(now)}] restarting before the 8h Live Activity ceiling "
                          f"({running_for / 3600:.1f}h in)")
                    activity_began = time.monotonic()
                publish(env, args.day, day, segments, now, started=not expiring,
                        dry_run=args.dry_run, with_card=changed and not args.no_card)
                last_key, last_push = key(current), now
    except KeyboardInterrupt:
        print("\ninterrupted")
    finish(env, args.day, args.dry_run)


def key(segment):
    return segment["label"] if segment else None


if __name__ == "__main__":
    main()
