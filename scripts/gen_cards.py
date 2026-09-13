#!/usr/bin/env python3
"""Generate the self-hosted SVG cards for the profile README.

Third-party card services (github-readme-stats, activity-graph) run on free
tiers that get paused or billed out, which breaks the profile README with no
warning. Everything here is rendered from the GitHub GraphQL API and committed
to the repo, so it can never fail to load.

Design: black, white and greys only. Fonts are embedded (see
scripts/subset_fonts.py) because SVGs loaded through <img> can't fetch web
fonts, and system fallbacks vary by platform. Motion is limited to a slow
fade-in and a quiet star field; content rests in its final visible state, so
anything that ignores animation still shows the full card. Random layouts use
fixed seeds so the daily refresh doesn't churn the files.
"""
import base64
import json
import os
import random
import subprocess
import sys
from pathlib import Path

USER = os.environ.get("GH_USER", "AmizhthanX")
NAME = os.environ.get("GH_NAME", "Amizhthan Senguttuvan")
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
FONTS = OUT / "fonts"

BLACK = "#000000"
WHITE = "#ffffff"
SOFT = "#b3b3b3"
GREY = "#7a7a7a"
LINE = "#262626"
HEAT = ["#141414", "#3d3d3d", "#707070", "#b0b0b0", "#ffffff"]

SERIF = "'Card Serif', Georgia, 'Times New Roman', serif"
MONO = "'Card Mono', ui-monospace, Menlo, Consolas, monospace"

MOTION = """
@keyframes fade { from { opacity: 0 } }
@keyframes twinkle { 50% { opacity: .15 } }
.in { animation: fade .9s ease-out backwards }
@media (prefers-reduced-motion: reduce) { * { animation: none !important } }
"""


def gql(query):
    r = subprocess.run(["gh", "api", "graphql", "-f", f"query={query}"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"GraphQL failed: {r.stderr[:400]}")
    return json.loads(r.stdout)["data"]


def esc(s):
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def fetch():
    d = gql("""
    { user(login: "%s") {
        followers { totalCount }
        contributionsCollection {
          totalCommitContributions
          totalPullRequestContributions
          totalIssueContributions
          contributionCalendar {
            totalContributions
            weeks { contributionDays { date contributionCount weekday } }
          }
        }
        # privacy: PUBLIC keeps output identical no matter whose token runs this.
        # Without it a `repo`-scoped local token counts private repos and a
        # CI GITHUB_TOKEN does not, so the card flip-flops on every run.
        repositories(first: 100, ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) {
          totalCount
          nodes {
            stargazerCount
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name } }
            }
          }
        }
    } }""" % USER)["user"]

    cc = d["contributionsCollection"]
    repos = d["repositories"]["nodes"]

    langs = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            langs[e["node"]["name"]] = langs.get(e["node"]["name"], 0) + e["size"]
    total = sum(langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1])[:6]

    return dict(
        stars=sum(r["stargazerCount"] for r in repos),
        repos=d["repositories"]["totalCount"],
        followers=d["followers"]["totalCount"],
        commits=cc["totalCommitContributions"],
        prs=cc["totalPullRequestContributions"],
        issues=cc["totalIssueContributions"],
        contributions=cc["contributionCalendar"]["totalContributions"],
        weeks=cc["contributionCalendar"]["weeks"],
        langs=[(n, size / total * 100) for n, size in top],
    )


def font_css(*families):
    files = {"Card Serif": "CardSerif.woff2", "Card Mono": "CardMono.woff2"}
    return "".join(
        f'@font-face {{ font-family: "{f}"; src: url(data:font/woff2;base64,'
        f'{base64.b64encode((FONTS / files[f]).read_bytes()).decode()}) format("woff2") }}'
        for f in families)


def grow(attr, to, delay, dur):
    """One-shot growth of `attr` from 0 after `delay`; rests at `to`."""
    total = delay + dur
    return (f'<animate attributeName="{attr}" dur="{total:.3f}s" fill="freeze" calcMode="spline" '
            f'keyTimes="0;{delay / total:.4f};1" keySplines="0 0 1 1;.2 .7 .2 1" '
            f'values="0;0;{to:.1f}"/>')


def svg(w, h, label, css, body):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(label)}">\n<style>{css}</style>\n{body}\n</svg>\n')


def card(w, h, title, body, aside="", serif=False):
    # Embed the serif only where big numbers use it; each face is ~10-19 KB of base64.
    css = font_css(*(["Card Serif"] if serif else []), "Card Mono") + MOTION + (
        f".label {{ font: 400 11px {MONO}; letter-spacing: 1.6px; fill: {GREY} }}"
        f".small {{ font: 400 11px {MONO}; fill: {GREY} }}"
        f".text {{ font: 400 12px {MONO}; fill: {WHITE} }}"
        f".num {{ font: 400 40px {SERIF}; fill: {WHITE} }}")
    head = (f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="10" fill="{BLACK}" stroke="{LINE}"/>'
            f'<text x="28" y="38" class="label">{esc(title.upper())}</text>'
            + (f'<text x="{w - 28}" y="38" class="small" text-anchor="end">{esc(aside)}</text>' if aside else "")
            + f'<path d="M28,54.5 H{w - 28}" stroke="{LINE}"/>')
    return svg(w, h, title, css, head + body)


def card_stats(d):
    cells = [(d["stars"], "Stars"), (d["commits"], "Commits, 12 mo"), (d["prs"], "PRs, 12 mo"),
             (d["repos"], "Public repos"), (d["issues"], "Issues, 12 mo"), (d["followers"], "Followers")]
    body = "".join(
        f'<g class="in" style="animation-delay:{.1 + i * .06:.2f}s">'
        f'<text x="{28 + (i % 3) * 144}" y="{106 + (i // 3) * 68}" class="num">{v:,}</text>'
        f'<text x="{28 + (i % 3) * 144}" y="{126 + (i // 3) * 68}" class="small">{esc(k)}</text></g>'
        for i, (v, k) in enumerate(cells))
    return card(460, 220, "GitHub", body, serif=True)


def card_langs(d):
    body = ""
    track_x, track_w = 164, 124
    for i, (name, pct) in enumerate(d["langs"]):
        y = 84 + i * 23
        body += (f'<g class="in" style="animation-delay:{.1 + i * .06:.2f}s">'
                 f'<text x="28" y="{y}" class="text">{esc(name)}</text>'
                 f'<rect x="{track_x}" y="{y - 5}" width="{track_w}" height="1" fill="{LINE}"/>'
                 f'<rect x="{track_x}" y="{y - 5.5}" width="{track_w * pct / 100:.1f}" height="2" fill="{WHITE}">'
                 f'{grow("width", track_w * pct / 100, .3 + i * .06, .8)}</rect>'
                 f'<text x="332" y="{y}" class="small" text-anchor="end">{pct:.1f}%</text></g>')
    return card(360, 220, "Languages", body)


def card_heatmap(d):
    weeks = d["weeks"]
    cell, gap, x0, y0 = 13, 4, 56, 96
    pitch = cell + gap
    peak = max((day["contributionCount"] for w in weeks for day in w["contributionDays"]), default=0)
    cols, months, seen = "", "", set()
    for wi, w in enumerate(weeks):
        wx = x0 + wi * pitch
        sq = ""
        for day in w["contributionDays"]:
            n = day["contributionCount"]
            lvl = 0 if n == 0 else min(4, 1 + int(n / max(peak, 1) * 3.999))
            sq += (f'<rect x="{wx}" y="{y0 + day["weekday"] * pitch}" width="{cell}" height="{cell}" rx="2" '
                   f'fill="{HEAT[lvl]}"><title>{day["date"]}: {n}</title></rect>')
        cols += f'<g class="in" style="animation-delay:{wi * .012:.3f}s">{sq}</g>'
        m = w["contributionDays"][0]["date"][:7]
        if m not in seen and wi < len(weeks) - 2:
            seen.add(m)
            label = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m[5:7]) - 1]
            months += f'<text x="{wx}" y="{y0 - 12}" class="small">{label}</text>'
    for i, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        cols += f'<text x="{x0 - 10}" y="{y0 + i * pitch + 10}" class="small" text-anchor="end">{lbl}</text>'

    w_total = x0 + len(weeks) * pitch + 39
    ly = y0 + 7 * pitch + 30
    legend = f'<text x="{w_total - 158}" y="{ly}" class="small" text-anchor="end">Less</text>'
    for i, col in enumerate(HEAT):
        legend += f'<rect x="{w_total - 148 + i * 17}" y="{ly - 10}" width="{cell}" height="{cell}" rx="2" fill="{col}" stroke="{LINE}" stroke-width=".5"/>'
    legend += f'<text x="{w_total - 28}" y="{ly}" class="small" text-anchor="end">More</text>'
    return card(w_total, ly + 26, "Contributions", months + cols + legend,
                aside=f"{d['contributions']} in the last year")


def header():
    W, H = 1000, 220
    rng = random.Random(7)
    text_zone = lambda x, y: x < 700 and 40 < y < 180

    stars = []
    while len(stars) < 170:
        # Denser toward the right, clear of the name.
        x, y = W * rng.random() ** .6, rng.uniform(6, H - 6)
        if text_zone(x, y):
            continue
        r = rng.choice((.35, .5, .5, .7, .7, .9, 1.2))
        style = (f' style="animation:twinkle {rng.uniform(3, 7):.1f}s ease-in-out {rng.uniform(0, 6):.1f}s infinite"'
                 if rng.random() < .18 else "")
        stars.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r}" fill="{WHITE}" opacity="{rng.uniform(.2, .9):.2f}"{style}/>')

    ox, oy, rx, ry = 850, 112, 118, 34
    orbit = (f'<g transform="rotate(-16 {ox} {oy})">'
             f'<ellipse cx="{ox}" cy="{oy}" rx="{rx}" ry="{ry}" fill="none" stroke="{WHITE}" stroke-opacity=".22" stroke-width=".8"/>'
             f'<ellipse cx="{ox}" cy="{oy}" rx="{rx * 1.55:.0f}" ry="{ry * 1.55:.0f}" fill="none" stroke="{WHITE}" stroke-opacity=".1" stroke-width=".8" stroke-dasharray="1 5"/>'
             f'<circle cx="{ox}" cy="{oy}" r="4" fill="{WHITE}"/>'
             f'<circle r="2" fill="{WHITE}"><animateMotion dur="30s" repeatCount="indefinite" '
             f'path="M{ox + rx},{oy} A{rx},{ry} 0 1,1 {ox - rx},{oy} A{rx},{ry} 0 1,1 {ox + rx},{oy}"/></circle></g>')

    css = font_css("Card Serif", "Card Mono") + MOTION + (
        f".label {{ font: 400 11px {MONO}; letter-spacing: 2.4px; fill: {GREY} }}"
        f".name {{ font: 400 64px {SERIF}; fill: {WHITE}; letter-spacing: -.5px }}")
    body = (f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{BLACK}" stroke="{LINE}"/>'
            f'{"".join(stars)}{orbit}'
            f'<text x="56" y="80" class="label in">SOFTWARE DEVELOPER · INDIA</text>'
            f'<text x="54" y="150" class="name in" style="animation-delay:.15s">{esc(NAME)}</text>')
    return svg(W, H, NAME, css, body)


def main():
    d = fetch()
    OUT.mkdir(exist_ok=True)
    (OUT / "header.svg").write_text(header())
    (OUT / "stats.svg").write_text(card_stats(d))
    (OUT / "langs.svg").write_text(card_langs(d))
    (OUT / "heatmap.svg").write_text(card_heatmap(d))
    print(f"Generated 4 assets for @{USER}: "
          f"{d['stars']}* {d['repos']} repos {d['contributions']} contributions")


if __name__ == "__main__":
    main()
