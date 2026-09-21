#!/usr/bin/env python3
"""Scrape lisbonai.org/talks/ into talks.json — one entry per talk, with abstract.

The Live Activity only needs titles and times; the card needs the abstract, and
that only lives on the talks page. Re-run whenever the site adds talks:

    ./fetch_talks.py
"""

import html
import json
import pathlib
import re
import urllib.request

URL = "https://lisbonai.org/talks/"
OUT = pathlib.Path(__file__).resolve().parent / "talks.json"


def text(fragment):
    return html.unescape(re.sub(r"<[^>]+>", "", fragment)).strip()


def parse(page):
    talks = []
    for chunk in re.split(r'<li id="', page)[1:]:
        slug = chunk[:chunk.index('"')]
        speaker = re.search(r'<span class="text-cream">(.*?)</span>', chunk, re.S)
        org = re.search(r'<span class="text-faint[^"]*">(.*?)</span>', chunk, re.S)
        track = re.search(r'<div class="font-mono text-xs uppercase text-faint">(.*?)</div>', chunk, re.S)
        title = re.search(r'<div class="text-lg leading-snug[^"]*">(.*?)</div>', chunk, re.S)
        if not (speaker and title):
            continue
        body = [text(p) for p in re.findall(
            r'<p class="text-sm leading-relaxed text-soft">(.*?)</p>', chunk, re.S)]
        talks.append({
            "slug": slug,
            "speaker": text(speaker.group(1)),
            "org": text(org.group(1)) if org else "",
            "track": text(track.group(1)) if track else "",
            "title": text(title.group(1)),
            "abstract": [p for p in body if p],
            "url": URL + "#" + slug,
        })
    return talks


def main():
    req = urllib.request.Request(URL, headers={"User-Agent": "lisbonai-widget/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        page = resp.read().decode("utf-8", "replace")
    talks = parse(page)
    if not talks:
        raise SystemExit("Parsed nothing — the page markup probably changed.")
    OUT.write_text(json.dumps({"source": URL, "talks": talks}, indent=2, ensure_ascii=False) + "\n")
    print(f"{len(talks)} talks -> {OUT.name}")
    for t in talks:
        print(f"  {t['track']:<11} {t['speaker']:<22} {len(' '.join(t['abstract'])):>5} chars  {t['title'][:50]}")


if __name__ == "__main__":
    main()
