# Lisbon AI 2026 on your Lock Screen

Publishes the [Lisbon AI 2026](https://lisbonai.org) programme to
[00Widget](https://00widget.com), so the conference schedule lives on your
phone instead of in a browser tab you keep re-opening.

Two surfaces, from one schedule:

**Live Activity** — Lock Screen and Dynamic Island. What is on stage now, the
next three talks with their speakers, and a countdown to the end of the current
one.

```
Lisbon AI · Day 1                             Agents
Agentic Memory in a nutshell: Do's and Don'ts  ~12 min
  ▸ Agentic Memory in a nutshell   Vitalii Ratushnyi · Harmix.AI     now
    Products that fix themselves   Peter Kirkham · PostHog        ~15:21
    Apps Are the New Tools         Pedro Rodrigues · Supabase     ~15:38
    + 1 more
```

**Card** — Home Screen widget. The current talk with its full abstract from
[lisbonai.org/talks](https://lisbonai.org/talks/), the track and slot, and
what follows it. Outside conference hours it becomes a countdown to the next
day's doors, carrying the opening talk's blurb, so it is safe to leave up.

The conference is **23–24 September 2026** at the Champalimaud Centre for the
Unknown, Belém, Lisbon.

## What 00Widget is

[00Widget](https://00widget.com) is an iOS app plus an HTTP API for putting
live state onto Apple surfaces — Home Screen widgets, Lock Screen Live
Activities, the Dynamic Island, Apple Watch and Apple TV — without writing an
app of your own. You install it, it registers push tokens for your devices,
and anything that can POST JSON can then draw on them.

You publish typed state rather than UI: no HTML, no layout, no colours. You
pick a shape and fill it in, and the app decides how it renders on each
surface. The two used here:

- A **card** is standing state, something you check on — a balance, a queue
  depth, tomorrow's first talk. It reaches Home Screen widgets on a rationed
  refresh budget.
- A **Live Activity** is work with a start and an end that you report on while
  it runs — a build, a deploy, a conference day. It is the only surface that
  reaches the Lock Screen and Dynamic Island, and updates are pushed straight
  to the screen.

This repo is one producer talking to that API: ~600 lines of Python, two JSON
files, no dependencies. The API is `api.00widget.com`, authenticated with a
publisher token from the app.

## Setup

```sh
cp .env.example .env     # then paste your 00Widget publisher token in
```

Python 3.9+, no dependencies. `.env` is gitignored and no token has ever been
committed, which is why this repo can be public.

## Running it

On each conference morning:

```sh
./lisbonai_widget.py --day 1 --watch
```

That starts the Live Activity, publishes the card, pushes a new state at every
talk change plus a 10-minute heartbeat, and ends the activity when the day is
over. Ctrl-C ends it cleanly too.

| Flag | What it does |
| --- | --- |
| `--day N` | which conference day's programme to publish (default 1) |
| `--watch` | run all day, pushing at every change |
| `--resume` | with `--watch`, adopt the activity already running instead of restarting it |
| `--update` | a single push to the running activity, rather than a start |
| `--card-only` / `--no-card` | publish one surface without the other |
| `--end` | end the activity now |
| `--at HH:MM` | pretend it is this time of day |
| `--now-is HH:MM` | slide the programme so this moment lands on the real clock |
| `--offset HOURS` | shift the programme from its real date; `-24` rehearses day 1 a day early |
| `--date YYYY-MM-DD` | hang the programme on a specific date (default: today) |
| `--poll SECONDS` | how often `--watch` re-checks the schedule (default 20) |
| `--speed N` | with `--at`, run the clock N times faster — for fast-forwarding a whole day |
| `--dry-run` | print the payloads instead of sending them |

### Rehearsing

Times are matched by time of day, so running day 1's programme a day early is:

```sh
./lisbonai_widget.py --day 1 --offset -24 --watch
```

Use `--now-is` rather than `--at` for anything you intend to look at on the
phone. The device ticks its countdown against its own clock, so a simulated
14:40 on a schedule anchored to the 23rd shows a two-day countdown;
`--now-is 14:40` slides the whole day so that moment is genuinely now.

To swap this process onto new code mid-day, stop it and restart with
`--resume`. Without it the first push is a `start`, and starting an activity
that is already running restarts it — which the user sees as one banner
dismissing and another animating in. `--resume` also reads the running
activity's age from the API, so the restart guard below stays correct.

## Data

- `schedule.json` — both days, transcribed from
  [lisbonai.org/schedule](https://lisbonai.org/schedule/).
- `talks.json` — abstracts, scraped from
  [lisbonai.org/talks](https://lisbonai.org/talks/). Regenerate with
  `./fetch_talks.py` whenever the site adds talks.

The two are joined on speaker name, accent-insensitively, so `Oguz Gultepe`
matches `Oğuz Gültepe` and a talk retitled on the site still finds its slot.

### Talk times are partly derived, and say so

The site publishes times per *block* — "Agents, 2:30–4:30 PM, seven talks" —
not per talk, so talks are spread evenly across their block. A time carries a
leading `~` wherever we worked it out rather than read it off the site:

| Time | Written | Because |
| --- | --- | --- |
| Breaks, lunch, doors, opening | `11:15` | published |
| First talk of a block, its start | `09:45` | the block's own start |
| Last talk of a block, its end | `16:30` | the block's own end |
| Everything else | `~10:15` | our even split |

So `Agents · ~16:12–16:30` reads correctly: we guessed when that talk starts,
and the site told us when the block ends. The countdown uses minute
granularity, so iOS renders it as `~12 min` rather than a ticking clock that
looks more certain than it is.

If per-talk times are published later, give each talk its own `start`/`end` in
`schedule.json` and mark them exact; the tildes disappear on their own.

## Things learned the hard way

Each of these is a constraint that is invisible until it bites, and each one
shapes the code.

**iOS ends a Live Activity after about 8 hours.** A conference day is eleven,
so `--watch` restarts the activity once before the system kills it. The rule
that survived contact with reality is *this activity cannot reach the end of
the programme, and a fresh one started now could* — both halves matter. Without
the second, it restarts on every poll of every break that is simply too early
to help; a plain age threshold produced ten restarts in a simulated day. With
both, it fires exactly once, during lunch, whatever time it was launched.

A restart costs a visible dismiss-and-reappear, which is why it is aimed at a
break rather than mid-talk.

**The 8 hours start when the activity does, not when the day does.** So
`--watch` can be launched the night before: it publishes the card immediately
and holds the banner until 15 minutes before doors. Started at midnight, an
activity spends its entire ceiling saying "starts soon" and is gone before
anyone is on stage.

**`time.monotonic()` stops while a Mac sleeps.** A clock built on it wakes up
hours behind and then states the wrong talk with complete confidence. A real
run reads the wall clock; only simulated ones are driven by elapsed time.

**The API returns timestamps in UTC.** Parsing `startedAt` as local time
overstated a resumed activity's age by the UTC offset, so the restart guard
fired an hour early — visible only as a banner blinking at the wrong moment.

**A Home Screen widget's reloads are rationed.** Roughly two an hour sustained
with a burst of six, while the afternoon tracks change talk every ~17 minutes.
The card is therefore published only when the talk actually changes, never on
the heartbeat — with the heartbeat included the budget is gone by mid-
afternoon and the card silently lags.

**A card's briefing sections are capped at 500 characters** and real abstracts
are routinely longer, so paragraphs are split on sentence boundaries rather
than truncated. Sections are also revealed progressively by widget size: a
medium widget draws only the first one, so the first section must be the blurb
and not the title the card's headline already carries.

**The Live Activity title is frozen at start**, along with `kind` and
`deepLink`. So the title is `Lisbon AI · Day 1` and everything that moves lives
in `value`, `items`, `progress` and `endsAt`. That is also why there is one
activity id per day, `lisbonai-2026-day{N}`.

**Every push carries `staleAt`.** If this process dies, the Lock Screen marks
itself out of date instead of showing a talk that finished an hour ago. Going
quiet is the one failure on this API that returns `200` to every call you did
make.

**The API edge refuses urllib's default User-Agent** with a `403` and
Cloudflare error 1010, which says nothing about the cause. Requests send an
explicit one.

## Files

| | |
| --- | --- |
| `lisbonai_widget.py` | the publisher — schedule → Live Activity + card |
| `fetch_talks.py` | scrapes the talks page into `talks.json` |
| `schedule.json` | the programme, both days |
| `talks.json` | abstracts, generated |

## License

[MIT](LICENSE). Schedule and talk content belong to
[Lisbon AI](https://lisbonai.org) and are reproduced here for the widget's
own use.
