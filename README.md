# Lisbon AI 2026 — Lock Screen & Home Screen

Publishes the [Lisbon AI 2026](https://lisbonai.org) programme to
[00Widget](https://api.00widget.com), on two surfaces:

- **Live Activity** (Lock Screen / Dynamic Island) — what is on stage now, the
  next three talks, and a countdown to the end of the current one.
- **Card** (Home Screen widget) — the current talk with its abstract from
  [lisbonai.org/talks](https://lisbonai.org/talks/), and what follows it.

Conference: **23–24 September 2026**, Champalimaud Centre for the Unknown, Belém.

## Setup

```sh
cp .env.example .env     # then paste your 00Widget publisher token in
```

`.env` is gitignored — the token never enters the repo, so this can be public.
Python 3.9+, no dependencies.

## Running it

The one that matters, on each conference morning:

```sh
./lisbonai_widget.py --day 1 --watch
```

It starts the activity, pushes a new state at every talk change plus a
10-minute heartbeat, and ends the activity when the day is over. Ctrl-C also
ends it cleanly. Every push carries `staleAt`, so if the process dies the Lock
Screen says it is out of date rather than lying about the current talk.

| Command | What it does |
| --- | --- |
| `--day 1 --watch` | the real thing: run it all day |
| `--day 1 --at 14:40` | one push, pretending it is 14:40 |
| `--day 1 --now-is 14:40` | slides the programme so 14:40 is *now* — the only way a rehearsal gets an honest countdown on the device |
| `--day 1 --update` | push to the running activity instead of restarting it |
| `--day 1 --card-only` | publish just the Home Screen card |
| `--day 1 --no-card` | publish just the Lock Screen activity |
| `--day 1 --end` | end the activity |
| `--dry-run` | print the payloads instead of sending them |
| `--date 2026-09-23` | hang the programme on a specific date |

`--date` defaults to today, and times are matched by time of day. So a
rehearsal **tomorrow** with day 1's programme is just:

```sh
./lisbonai_widget.py --day 1 --watch
```

at 09:00 on the 22nd, and it behaves exactly as it will on the 23rd.

`--now-is` matters because the phone ticks its countdown against the real
clock: a simulated 14:40 on a schedule anchored to the 23rd would show a
two-day countdown. `--now-is` slides the whole day so the current moment is
real.

## Data

- `schedule.json` — both days, hand-transcribed from
  [lisbonai.org/schedule](https://lisbonai.org/schedule/).
- `talks.json` — abstracts, scraped. Regenerate with `./fetch_talks.py`
  whenever the site adds talks.

The two are joined on speaker name (accent-insensitive), so a talk renamed on
the site still matches.

**Talk times are partly derived, and say so.** The site publishes times per
*block* — "Agents, 2:30–4:30 PM, seven talks" — not per talk, so talks are
spread evenly across their block.

A time is written with a leading `~` wherever we worked it out rather than read
it off the site:

| Time | Written | Because |
| --- | --- | --- |
| Breaks, lunch, doors, opening | `11:15` | published |
| First talk of a block, its start | `09:45` | the block's own start |
| Last talk of a block, its end | `16:30` | the block's own end |
| Everything else | `~10:15` | our even split |

So `Agents · ~16:12–16:30` reads correctly: we guessed when that talk starts,
and the site told us when the block ends. The Lock Screen countdown uses
minute granularity, so iOS renders it as `~12 min` rather than a ticking clock
that looks more certain than it is.

If per-talk times are published later, give each talk a `start`/`end` in
`schedule.json`; mark them exact there and the tildes disappear.

## Notes

- One activity per day, id `lisbonai-2026-day{N}`. Re-running without
  `--update` *restarts* it, which the user sees as one banner dismissing and
  another animating in — use `--update` for a routine push.
- The card id is `lisbonai-now` and it is safe to leave published: outside
  conference hours it becomes a countdown to the next day's doors.
- Requests send an explicit `User-Agent`; the edge in front of the API refuses
  urllib's default with a 403.
