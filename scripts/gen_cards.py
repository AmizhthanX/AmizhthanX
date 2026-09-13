#!/usr/bin/env python3
"""Generate the self-hosted, animated deep-space SVG assets for the profile README.

Third-party card services (github-readme-stats, activity-graph, capsule-render,
readme-typing-svg) run on free tiers that get paused or billed out, which breaks
the profile README with no warning. Everything here is rendered from the GitHub
GraphQL API and committed to the repo, so it can never fail to load.

Animation notes:
- GitHub loads these through <img>, so there is no JavaScript. Motion is SMIL
  (typing, orbits, meteors, disk swirl, bar growth) plus CSS keyframes (fades,
  twinkle, blink).
- Content rests in its final, visible state and animates *from* hidden, so a
  renderer that ignores animation still shows the full card. Purely decorative
  effects (meteors) rest invisible instead.
- Typed text is monospace with textLength pinned to len * char width, so the
  reveal clip and cursor line up with the glyphs whichever font resolves.
- One committed space-black look for both GitHub themes: black cards read as
  deliberate on a light page, and it keeps a single set of assets.
- Random layouts use fixed seeds so the daily CI run doesn't churn the files.
- CSS motion is switched off under prefers-reduced-motion.
"""
import json
import math
import os
import random
import subprocess
import sys
from pathlib import Path

USER = os.environ.get("GH_USER", "AmizhthanX")
NAME = os.environ.get("GH_NAME", "Amizhthan Senguttuvan")
OUT = Path(__file__).resolve().parent.parent / "assets"

SANS = "'Segoe UI', Ubuntu, 'Helvetica Neue', Sans-Serif"
MONO = "ui-monospace, SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
CHAR = 0.6  # monospace advance width as a fraction of font size

VOID = "#02030a"
CARD = "#05070d"
BORDER = "#1c2140"
TEXT = "#d6dcf0"
MUTED = "#7b84a6"
VIOLET = "#a78bfa"
CYAN = "#67e8f9"
PINK = "#f0abfc"
EMPTY = "#0f1326"
HEAT = [EMPTY, "#2e1065", "#6d28d9", "#a78bfa", "#e9d5ff"]

ROLES = [
    "Software Developer",
    "AI / ML & Computer Vision",
    "Super-resolution for satellite imagery",
    "Full-stack: Next.js · FastAPI",
    "Data engineering on Snowflake",
]

ABOUT = [
    [("p", "$ "), ("c", "cat about.yaml")],
    [("k", "name:"), ("v", "     " + NAME)],
    [("k", "role:"), ("v", "     Software Developer")],
    [("k", "location:"), ("v", " India")],
    [("k", "focus:"), ("v", "    "), ("b", "["),
     ("v", "AI/ML, Computer Vision, Data Engineering, Full-Stack"), ("b", "]")],
    [("k", "building:"), ("v", " GeoVision super-resolution · AI-assisted compiler")],
    [("k", "learning:"), ("v", " AR/VR · distributed data systems")],
    [("k", "motto:"), ("v", "    "), ("s", '"Ship it, then make it fast."')],
]

# Orion, normalised to its bounding box: x, y, radius, colour.
ORION = {
    "meissa": (.50, .00, 1.5, "#e0e7ff"),
    "betelgeuse": (.12, .22, 2.8, "#fca5a5"),
    "bellatrix": (.86, .26, 2.0, "#e0e7ff"),
    "alnitak": (.36, .56, 1.8, "#e0e7ff"),
    "alnilam": (.50, .53, 1.9, "#e0e7ff"),
    "mintaka": (.64, .50, 1.8, "#e0e7ff"),
    "saiph": (.80, .98, 1.9, "#e0e7ff"),
    "rigel": (.20, .94, 2.7, "#bfdbfe"),
}
ORION_LINES = [("meissa", "betelgeuse"), ("meissa", "bellatrix"), ("betelgeuse", "alnitak"),
               ("bellatrix", "mintaka"), ("alnitak", "alnilam"), ("alnilam", "mintaka"),
               ("alnitak", "rigel"), ("mintaka", "saiph")]

BASE_CSS = """
@keyframes fade-up { from { opacity: 0; transform: translateY(8px) } }
@keyframes fade-in { from { opacity: 0 } }
@keyframes slide-in { from { opacity: 0; transform: translateX(-10px) } }
@keyframes twinkle { 0%, 100% { opacity: .2 } 50% { opacity: 1 } }
@keyframes glint { 50% { opacity: .45 } }
@keyframes blink { 50% { opacity: 0 } }
.fu { animation: fade-up .7s cubic-bezier(.2, .8, .2, 1) backwards }
.fi { animation: fade-in .6s ease-out backwards }
.si { animation: slide-in .5s cubic-bezier(.2, .8, .2, 1) backwards }
.blink { animation: blink 1s steps(1) infinite }
@media (prefers-reduced-motion: reduce) { * { animation: none !important } }
"""

# Small elements get oversized filter regions so their glow isn't clipped.
FILTERS = """
<filter id="blur1" x="-50%" y="-300%" width="200%" height="700%"><feGaussianBlur stdDeviation="1.2"/></filter>
<filter id="blur2" x="-20%" y="-60%" width="140%" height="220%"><feGaussianBlur stdDeviation="2.4"/></filter>
<filter id="blur3" x="-10%" y="-100%" width="120%" height="300%"><feGaussianBlur stdDeviation="3.5"/></filter>
<filter id="blur8" x="-20%" y="-100%" width="140%" height="300%"><feGaussianBlur stdDeviation="8"/></filter>
<filter id="glow" x="-100%" y="-100%" width="300%" height="300%"><feGaussianBlur stdDeviation="1.6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
<filter id="glowS" x="-400%" y="-400%" width="900%" height="900%"><feGaussianBlur stdDeviation="2" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
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
              edges { size node { name color } }
            }
          }
        }
    } }""" % USER)["user"]

    cc = d["contributionsCollection"]
    repos = d["repositories"]["nodes"]

    langs = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            langs.setdefault(n, {"size": 0, "color": e["node"]["color"] or "#8b949e"})
            langs[n]["size"] += e["size"]
    total = sum(v["size"] for v in langs.values()) or 1
    top = sorted(langs.items(), key=lambda kv: -kv[1]["size"])[:6]

    return dict(
        stars=sum(r["stargazerCount"] for r in repos),
        repos=d["repositories"]["totalCount"],
        followers=d["followers"]["totalCount"],
        commits=cc["totalCommitContributions"],
        prs=cc["totalPullRequestContributions"],
        issues=cc["totalIssueContributions"],
        contributions=cc["contributionCalendar"]["totalContributions"],
        weeks=cc["contributionCalendar"]["weeks"],
        langs=[(n, v["size"] / total * 100, v["color"]) for n, v in top],
    )


# --- animation primitives ---------------------------------------------------

def smil(attr, points, total):
    """Looping discrete <animate> that steps `attr` through (seconds, value) points."""
    keys, vals = [], []
    for t, v in points:
        k = round(t / total, 5)
        if keys and k <= keys[-1]:  # rounding collapsed two steps; keep the later value
            vals[-1] = v
            continue
        keys.append(k)
        vals.append(v)
    fmt = lambda v: f"{v:.1f}" if isinstance(v, (int, float)) else v
    return (f'<animate attributeName="{attr}" calcMode="discrete" dur="{total:.3f}s" '
            f'repeatCount="indefinite" keyTimes="{";".join(map(str, keys))}" '
            f'values="{";".join(fmt(v) for v in vals)}"/>')


def grow(attr, to, delay, dur, spline=".2 .8 .2 1"):
    """One-shot growth of `attr` from 0 after `delay`; rests at `to`."""
    total = delay + dur
    return (f'<animate attributeName="{attr}" dur="{total:.3f}s" fill="freeze" calcMode="spline" '
            f'keyTimes="0;{delay / total:.4f};1" keySplines="0 0 1 1;{spline}" '
            f'values="0;0;{to:.1f}"/>')


def type_points(start, n, cw, step, hold=None, erase_step=None):
    """(time, revealed width) steps for typing n chars, optionally holding then erasing."""
    pts = [(start + k * step, k * cw) for k in range(1, n + 1)]
    if hold is not None:
        t0 = start + n * step + hold
        pts += [(t0 + j * erase_step, (n - j) * cw) for j in range(1, n + 1)]
    return pts


def typed(uid, x, y, markup, n, size, points, total, cls, full):
    """Monospace text revealed by an animated clip. `full` = visible without SMIL."""
    w = n * size * CHAR
    return (f'<clipPath id="{uid}"><rect x="{x:.1f}" y="{y - size:.1f}" '
            f'width="{w if full else 0:.1f}" height="{size * 1.45:.1f}">'
            + smil("width", [(0, 0)] + points, total) + '</rect></clipPath>'
            f'<text x="{x:.1f}" y="{y}" class="{cls}" xml:space="preserve" textLength="{w:.1f}" '
            f'lengthAdjust="spacingAndGlyphs" clip-path="url(#{uid})">{markup}</text>')


# --- space primitives -------------------------------------------------------

def starfield(rng, n, box, r=(.3, 1.1), op=(.35, .95), twinkle=.3, avoid=None, color="#fff"):
    x0, y0, x1, y1 = box
    out = []
    while len(out) < n:
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        if avoid and avoid(x, y):
            continue
        style = ""
        if rng.random() < twinkle:
            style = (f' style="animation:twinkle {rng.uniform(2.2, 5.5):.1f}s ease-in-out '
                     f'{rng.uniform(0, 5):.1f}s infinite"')
        out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{rng.uniform(*r):.2f}" fill="{color}" '
                   f'opacity="{rng.uniform(*op):.2f}"{style}/>')
    return "".join(out)


def sparkle(x, y, s, fill, extra=""):
    """Four-point star."""
    q = s * .18
    return (f'<path d="M{x:.1f},{y - s:.1f} Q{x + q:.1f},{y - q:.1f} {x + s:.1f},{y:.1f} '
            f'Q{x + q:.1f},{y + q:.1f} {x:.1f},{y + s:.1f} Q{x - q:.1f},{y + q:.1f} {x - s:.1f},{y:.1f} '
            f'Q{x - q:.1f},{y - q:.1f} {x:.1f},{y - s:.1f} Z" fill="{fill}"{extra}/>')


def twinkle_style(rng, lo=2.2, hi=4.5):
    return (f' style="animation:twinkle {rng.uniform(lo, hi):.1f}s ease-in-out '
            f'{rng.uniform(0, 4):.1f}s infinite"')


def drifting(content, width, dur):
    """Scroll a tile of stars left by one tile width, forever, with a copy trailing it."""
    return (f'<g><animateTransform attributeName="transform" type="translate" from="0 0" '
            f'to="-{width} 0" dur="{dur}s" repeatCount="indefinite"/>'
            f'{content}<g transform="translate({width} 0)">{content}</g></g>')


def meteor(x, y, angle, dur, begin, length=90, travel=260):
    """A shooting star that streaks for ~0.9s once per `dur` seconds; invisible otherwise."""
    f = .9 / dur
    return (f'<g transform="translate({x} {y}) rotate({angle})"><g opacity="0">'
            f'<animateTransform attributeName="transform" type="translate" begin="{begin}s" '
            f'dur="{dur}s" repeatCount="indefinite" keyTimes="0;{f:.4f};1" '
            f'values="0 0;{travel} 0;{travel} 0"/>'
            f'<animate attributeName="opacity" begin="{begin}s" dur="{dur}s" repeatCount="indefinite" '
            f'keyTimes="0;{f * .15:.4f};{f * .7:.4f};{f:.4f};1" values="0;1;1;0;0"/>'
            f'<rect x="-{length}" y="-.8" width="{length}" height="1.6" rx=".8" fill="url(#trail)"/>'
            f'<circle r="1.8" fill="#fff" filter="url(#glowS)"/></g></g>')


def space_defs():
    return (f'<linearGradient id="accent" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="{VIOLET}"/>'
            f'<stop offset="1" stop-color="{CYAN}"/></linearGradient>'
            f'<linearGradient id="edge" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{VIOLET}" stop-opacity=".6"/>'
            f'<stop offset=".5" stop-color="{BORDER}"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".5"/></linearGradient>'
            '<radialGradient id="nebA"><stop offset="0" stop-color="#7c3aed" stop-opacity=".22"/>'
            '<stop offset=".5" stop-color="#4c1d95" stop-opacity=".08"/><stop offset="1" stop-color="#4c1d95" stop-opacity="0"/></radialGradient>'
            '<radialGradient id="nebB"><stop offset="0" stop-color="#0ea5e9" stop-opacity=".14"/>'
            '<stop offset=".5" stop-color="#075985" stop-opacity=".05"/><stop offset="1" stop-color="#075985" stop-opacity="0"/></radialGradient>'
            '<linearGradient id="trail"><stop offset="0" stop-color="#c4b5fd" stop-opacity="0"/>'
            '<stop offset="1" stop-color="#ffffff" stop-opacity=".95"/></linearGradient>'
            + FILTERS)


# --- data cards -------------------------------------------------------------

def frame(w, h, body, title, seed, avoid=None):
    rng = random.Random(seed)
    stars = starfield(rng, max(12, w * h // 2400), (8, 8, w - 8, h - 8), r=(.3, 1.0), op=(.2, .6),
                      twinkle=.3, avoid=avoid)
    css = BASE_CSS + (
        f".t {{ font: 600 16px {SANS} }}"
        f".k {{ font: 400 13px {SANS}; fill: {TEXT} }}"
        f".v {{ font: 700 13px {SANS}; fill: {CYAN} }}"
        f".s {{ font: 400 11px {SANS}; fill: {MUTED} }}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(title)}">\n<style>{css}</style>\n'
            f'<defs>{space_defs()}<clipPath id="card"><rect width="{w}" height="{h}" rx="10"/></clipPath></defs>\n'
            f'<g clip-path="url(#card)"><rect width="{w}" height="{h}" fill="{CARD}"/>'
            f'<ellipse cx="{w}" cy="0" rx="{w * .8:.0f}" ry="{h * .9:.0f}" fill="url(#nebA)"/>'
            f'<ellipse cx="0" cy="{h}" rx="{w * .6:.0f}" ry="{h * .7:.0f}" fill="url(#nebB)"/>{stars}</g>'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="10" fill="none" stroke="url(#edge)"/>'
            f'<text x="24" y="34" class="t fi" fill="url(#accent)">{esc(title)}</text>'
            f'<rect x="24" y="42" width="44" height="2" rx="1" fill="url(#accent)">{grow("width", 44, .3, .6)}</rect>\n'
            f'{body}\n</svg>\n')


def card_stats(d):
    rows = [("Total Stars Earned", d["stars"]), ("Total Commits", d["commits"]),
            ("Total PRs", d["prs"]), ("Total Issues", d["issues"]),
            ("Public Repositories", d["repos"]), ("Followers", d["followers"])]
    body = "".join(
        f'<g class="si" style="animation-delay:{.25 + i * .09:.2f}s">'
        + sparkle(30, 72 + i * 24 - 4.5, 5, VIOLET if i % 2 == 0 else CYAN)
        + f'<text x="44" y="{72 + i * 24}" class="k">{esc(k)}</text>'
        f'<text x="440" y="{72 + i * 24}" class="v" text-anchor="end">{v}</text></g>'
        for i, (k, v) in enumerate(rows))
    body += (f'<text x="24" y="{72 + len(rows) * 24 + 8}" class="s fi" style="animation-delay:.95s">'
             f'{d["contributions"]} contributions in the last year</text>')
    return frame(464, 72 + len(rows) * 24 + 24, body, f"{USER}'s GitHub Stats", seed=101)


def card_langs(d):
    x, w, bar_y = 24.0, 292, 60
    bar, legend, at = "", "", .35
    for i, (name, pct, col) in enumerate(d["langs"]):
        seg = max(w * pct / 100, 2)
        dur = max(.9 * pct / 100, .08)
        # Segments fill back to back, linearly, so the bar reads as one sweep.
        bar += f'<rect x="{x:.1f}" y="{bar_y}" width="{seg:.1f}" height="10" fill="{col}">{grow("width", seg, at, dur, "0 0 1 1")}</rect>'
        x, at = x + seg, at + dur
        # One column: long names like "Jupyter Notebook" collide with a two-column
        # legend, and 24px rows keep this card exactly as tall as the stats card.
        ly = 96 + i * 24
        legend += (f'<g class="fi" style="animation-delay:{.45 + i * .08:.2f}s">'
                   f'<circle cx="29" cy="{ly - 4}" r="5" fill="{col}"/>'
                   f'<text x="41" y="{ly}" class="k">{esc(name)}</text>'
                   f'<text x="316" y="{ly}" class="s" text-anchor="end">{pct:.1f}%</text></g>')
    body = (f'<rect x="24" y="{bar_y}" width="{w}" height="10" rx="5" fill="{EMPTY}"/>'
            f'<defs><clipPath id="bar"><rect x="24" y="{bar_y}" width="{w}" height="10" rx="5"/></clipPath></defs>'
            f'<g clip-path="url(#bar)" filter="url(#glow)">{bar}</g>' + legend)
    return frame(340, 96 + len(d["langs"]) * 24, body, "Most Used Languages", seed=202)


def card_heatmap(d):
    rng = random.Random(303)
    weeks = d["weeks"]
    cell, gap, x0, y0 = 10, 3, 52, 66
    pitch = cell + gap
    peak = max((day["contributionCount"] for w in weeks for day in w["contributionDays"]), default=0)
    cols, months, seen = "", "", set()
    for wi, w in enumerate(weeks):
        wx = x0 + wi * pitch
        sq = ""
        for day in w["contributionDays"]:
            n = day["contributionCount"]
            lvl = 0 if n == 0 else min(4, 1 + int(n / max(peak, 1) * 3.999))
            # The busiest days glow and glint like the brightest stars.
            fx = ' filter="url(#glow)"' if lvl >= 3 else ""
            if lvl == 4:
                fx += f' style="animation:glint {rng.uniform(2.5, 4.5):.1f}s ease-in-out {rng.uniform(0, 3):.1f}s infinite"'
            sq += (f'<rect x="{wx}" y="{y0 + day["weekday"] * pitch}" width="{cell}" height="{cell}" rx="2" '
                   f'fill="{HEAT[lvl]}"{fx}><title>{day["date"]}: {n}</title></rect>')
        cols += f'<g class="fu" style="animation-delay:{.2 + wi * .018:.3f}s">{sq}</g>'
        m = w["contributionDays"][0]["date"][:7]
        label = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][int(m[5:7]) - 1]
        if m not in seen and wi < len(weeks) - 2:
            seen.add(m)
            months += f'<text x="{wx}" y="{y0 - 8}" class="s">{label}</text>'
    for i, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        cols += f'<text x="{x0 - 8}" y="{y0 + i * pitch + 9}" class="s" text-anchor="end">{lbl}</text>'

    # A faint scan beam sweeps the grid every few seconds -- a satellite pass.
    grid_w, grid_h = len(weeks) * pitch, 7 * pitch
    scan = (f'<defs><linearGradient id="beam"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/>'
            f'<stop offset=".7" stop-color="{CYAN}" stop-opacity=".25"/>'
            f'<stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>'
            f'<clipPath id="grid"><rect x="{x0}" y="{y0 - 2}" width="{grid_w}" height="{grid_h + 2}"/></clipPath></defs>'
            f'<g clip-path="url(#grid)"><rect x="{x0 - 48}" y="{y0 - 2}" width="48" height="{grid_h + 2}" fill="url(#beam)">'
            f'<animateTransform attributeName="transform" type="translate" begin="1.4s" dur="7s" '
            f'repeatCount="indefinite" keyTimes="0;.55;1" values="0 0;{grid_w + 48} 0;{grid_w + 48} 0"/></rect></g>')

    w_total = x0 + grid_w + 16
    h_total = y0 + grid_h + 34
    ly = h_total - 12
    legend = f'<g class="fi" style="animation-delay:1.1s"><text x="{w_total - 186}" y="{ly}" class="s">Less</text>'
    for i, col in enumerate(HEAT):
        legend += f'<rect x="{w_total - 156 + i * 14}" y="{ly - 9}" width="10" height="10" rx="2" fill="{col}"/>'
    legend += (f'<text x="{w_total - 80}" y="{ly}" class="s">More</text>'
               f'<text x="24" y="{ly}" class="s">{d["contributions"]} contributions in the last year</text></g>')
    in_grid = lambda x, y: x0 - 4 < x < x0 + grid_w + 4 and y0 - 4 < y < y0 + grid_h + 4
    return frame(w_total, h_total, months + cols + scan + legend, "Contribution Activity",
                 seed=404, avoid=in_grid)


# --- header, footer, divider, terminal --------------------------------------

def header():
    W, H = 1000, 260
    size, y = 19, 160
    cw = size * CHAR
    step, hold, erase, gap = .07, 1.7, .03, .45

    starts, t = [], .9  # let the name land before the first role types
    for role in ROLES:
        starts.append(t)
        t += len(role) * (step + erase) + hold + gap
    total = t

    roles, cursor = "", []
    for i, (role, s) in enumerate(zip(ROLES, starts)):
        n = len(role)
        x0 = W / 2 - n * cw / 2
        pts = type_points(s, n, cw, step, hold, erase)
        roles += typed(f"r{i}", x0, y, esc(role), n, size, pts, total, "role", full=(i == 0))
        cursor += [(s, x0 + 2)] + [(tt, x0 + wv + 2) for tt, wv in pts]
    first_x0 = W / 2 - len(ROLES[0]) * cw / 2
    cursor = [(0, first_x0 + 2)] + cursor
    caret = (f'<g class="blink"><rect x="{first_x0 + len(ROLES[0]) * cw + 2:.1f}" y="{y - size * .82:.1f}" '
             f'width="{cw * .55:.1f}" height="{size:.1f}" rx="1" fill="{CYAN}">'
             f'{smil("x", cursor, total)}</rect></g>')

    # Starfield: two slow parallax layers plus a few bright four-point sparkles.
    rng = random.Random(7)
    far = starfield(rng, 90, (0, 0, W, 225), r=(.25, .7), op=(.25, .7), twinkle=0)
    mid = starfield(rng, 42, (0, 0, W, 225), r=(.6, 1.1), op=(.45, .9), twinkle=.35)
    busy = lambda x, yy: ((200 < x < 800 and 25 < yy < 185) or (770 < x < 1000 and 20 < yy < 200)
                          or (30 < x < 225 and 25 < yy < 230))
    sparkles = []
    while len(sparkles) < 8:
        sx, sy = rng.uniform(20, W - 20), rng.uniform(14, 190)
        if not busy(sx, sy):
            sparkles.append(sparkle(sx, sy, rng.uniform(3, 5.5), "#fff", twinkle_style(rng)))

    nebula = "".join(
        f'<ellipse cx="{ex}" cy="{ey}" rx="{erx}" ry="{ery}" fill="url(#{gid})">'
        f'<animate attributeName="opacity" values="1;.55;1" dur="{d}s" repeatCount="indefinite"/>'
        f'<animateTransform attributeName="transform" type="translate" values="0 0;{mx} {my};0 0" '
        f'dur="{d * 1.7:.0f}s" repeatCount="indefinite"/></ellipse>'
        for ex, ey, erx, ery, gid, d, mx, my in (
            (230, 70, 340, 150, "nebH1", 12, 40, 10),
            (770, 190, 320, 130, "nebH2", 17, -35, -8),
            (560, -10, 270, 95, "nebH3", 9, 25, 6)))

    # Orion draws itself line by line, holds, fades, and redraws.
    bx, by, bw, bh = 52, 40, 150, 158
    pos = {k: (bx + v[0] * bw, by + v[1] * bh) for k, v in ORION.items()}
    T = 14.0
    lines = ""
    for i, (a, b) in enumerate(ORION_LINES):
        (x1, y1), (x2, y2) = pos[a], pos[b]
        L = math.hypot(x2 - x1, y2 - y1)
        s = 1.0 + i * .42
        lines += (f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#c4b5fd" '
                  f'stroke-opacity=".45" stroke-width="1" stroke-linecap="round" stroke-dasharray="{L:.1f}">'
                  f'<animate attributeName="stroke-dashoffset" dur="{T}s" repeatCount="indefinite" '
                  f'keyTimes="0;{s / T:.4f};{(s + .45) / T:.4f};1" values="{L:.1f};{L:.1f};0;0"/></line>')
    orion = (f'<g><animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
             f'keyTimes="0;{12.2 / T:.4f};{13.2 / T:.4f};1" values="1;1;0;0"/>{lines}</g>'
             + "".join(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{ORION[k][2]}" fill="{ORION[k][3]}" filter="url(#glowS)"'
                       + (twinkle_style(rng, 3, 6) if ORION[k][2] < 2 else "") + '/>'
                       for k, (px, py) in pos.items())
             + f'<text x="{bx + bw / 2}" y="{by + bh + 22}" text-anchor="middle" class="tag" opacity="0">ORION'
             f'<animate attributeName="opacity" dur="{T}s" repeatCount="indefinite" '
             f'keyTimes="0;{4.6 / T:.4f};{5.4 / T:.4f};{12.2 / T:.4f};{13.2 / T:.4f};1" values="0;0;1;1;0;0"/></text>')

    meteors = meteor(170, 18, 24, 7, 2) + meteor(560, 8, 28, 11, 5.5) + meteor(690, 36, 20, 15, 9.5)

    # Black hole: glow, back half of a swirling disk, the lensed far side of the
    # disk arcing over and under the shadow, photon ring, shadow, front half.
    cx, cy, rx, ry = 892, 108, 88, 18  # clear the end of the name by ~30px

    def disk():
        return (f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="url(#disk)" stroke-width="9" filter="url(#blur2)"/>'
                f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="none" stroke="#fff7ed" stroke-opacity=".55" stroke-width="1.3" stroke-dasharray="3 9">'
                f'<animate attributeName="stroke-dashoffset" from="0" to="-432" dur="5s" repeatCount="indefinite"/></ellipse>'
                f'<ellipse cx="{cx}" cy="{cy}" rx="{rx - 20}" ry="{ry - 5}" fill="none" stroke="#fde68a" stroke-opacity=".4" stroke-width="1" stroke-dasharray="2 10">'
                f'<animate attributeName="stroke-dashoffset" from="0" to="-432" dur="3.2s" repeatCount="indefinite"/></ellipse>')

    particles = "".join(
        f'<circle r="{r}" fill="{c}"><animateMotion dur="{d}s" begin="-{b}s" repeatCount="indefinite" '
        f'path="M{cx + orx},{cy} A{orx},{ory} 0 1,1 {cx - orx},{cy} A{orx},{ory} 0 1,1 {cx + orx},{cy}"/></circle>'
        for orx, ory, d, b, r, c in ((92, 20, 4.5, 0, 1.3, "#fde68a"), (78, 15, 3.4, 1.2, 1.1, "#fff7ed"),
                                     (100, 22, 6, 2.5, 1.2, "#fbbf24")))
    black_hole = (
        f'<ellipse cx="{cx}" cy="{cy}" rx="170" ry="80" fill="url(#bhglow)">'
        f'<animate attributeName="opacity" values="1;.65;1" dur="6s" repeatCount="indefinite"/></ellipse>'
        f'<g transform="rotate(-12 {cx} {cy})">'
        f'<g clip-path="url(#backhalf)">{disk()}</g>'
        f'<path d="M{cx - 44},{cy} A44,38 0 0,1 {cx + 44},{cy}" fill="none" stroke="url(#disk)" stroke-width="5" opacity=".85" filter="url(#blur2)"/>'
        f'<path d="M{cx - 38},{cy} A38,28 0 0,0 {cx + 38},{cy}" fill="none" stroke="url(#disk)" stroke-width="2.5" opacity=".45" filter="url(#blur1)"/>'
        f'<circle cx="{cx}" cy="{cy}" r="31" fill="none" stroke="#fde68a" stroke-width="2" filter="url(#blur1)">'
        f'<animate attributeName="stroke-opacity" values=".55;1;.55" dur="4s" repeatCount="indefinite"/></circle>'
        f'<circle cx="{cx}" cy="{cy}" r="28" fill="#000"/>'
        f'<g clip-path="url(#fronthalf)">{disk()}</g>'
        f'{particles}</g>')

    # Planet horizon: an arc of a huge circle whose top just breaks the frame.
    R, ay = 1400, 290
    top = 200
    pcy = top + R
    dx = math.sqrt(R * R - (ay - pcy) ** 2)
    arc = f"M{500 - dx:.1f},{ay} A{R},{R} 0 0,1 {500 + dx:.1f},{ay}"
    planet = (f'<path d="{arc} Z" fill="url(#ground)"/>'
              f'<path d="{arc}" fill="none" stroke="#7c3aed" stroke-width="26" stroke-opacity=".28" filter="url(#blur8)">'
              f'<animate attributeName="stroke-opacity" values=".16;.4;.16" dur="7s" repeatCount="indefinite"/></path>'
              f'<path d="{arc}" fill="none" stroke="#38bdf8" stroke-width="7" stroke-opacity=".6" filter="url(#blur3)"/>'
              f'<path d="{arc}" fill="none" stroke="#bae6fd" stroke-width="1.1" stroke-opacity=".85"/>'
              f'<ellipse cx="500" cy="{top}" rx="190" ry="14" fill="url(#flare)">'
              f'<animate attributeName="opacity" values=".5;1;.5" dur="6s" repeatCount="indefinite"/></ellipse>'
              f'<ellipse cx="500" cy="{top}" rx="46" ry="2.2" fill="#fff" filter="url(#blur1)"/>')

    satellite = (f'<g><animateMotion dur="24s" repeatCount="indefinite" rotate="auto" path="M-40,236 Q500,150 1040,236"/>'
                 f'<rect x="-11" y="-2" width="7" height="4" fill="{CYAN}" opacity=".85"/>'
                 f'<rect x="4" y="-2" width="7" height="4" fill="{CYAN}" opacity=".85"/>'
                 f'<rect x="-3" y="-3" width="6" height="6" rx="1" fill="#e2e8f0"/>'
                 f'<circle cx="0" cy="-4.5" r="1" fill="#f87171" class="blink"/></g>')

    css = BASE_CSS + (
        f".hi {{ font: 600 12px {SANS}; letter-spacing: 4px; fill: #94a3b8 }}"
        f".name {{ font: 700 46px {SANS}; letter-spacing: .5px }}"
        f".role {{ font: 500 {size}px {MONO}; fill: #ddd6fe }}"
        f".tag {{ font: 600 9px {SANS}; letter-spacing: 3px; fill: #a5b4fc }}")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(NAME)} — {esc(ROLES[0])}">
<style>{css}</style>
<defs>
  {space_defs()}
  <clipPath id="banner"><rect width="{W}" height="{H}" rx="18"/></clipPath>
  <clipPath id="backhalf"><rect x="{cx - 200}" y="{cy - 100}" width="400" height="100"/></clipPath>
  <clipPath id="fronthalf"><rect x="{cx - 200}" y="{cy}" width="400" height="100"/></clipPath>
  <radialGradient id="nebH1"><stop offset="0" stop-color="#7c3aed" stop-opacity=".32"/><stop offset=".45" stop-color="#4c1d95" stop-opacity=".12"/><stop offset="1" stop-color="#4c1d95" stop-opacity="0"/></radialGradient>
  <radialGradient id="nebH2"><stop offset="0" stop-color="#0ea5e9" stop-opacity=".22"/><stop offset=".5" stop-color="#075985" stop-opacity=".08"/><stop offset="1" stop-color="#075985" stop-opacity="0"/></radialGradient>
  <radialGradient id="nebH3"><stop offset="0" stop-color="#db2777" stop-opacity=".16"/><stop offset="1" stop-color="#db2777" stop-opacity="0"/></radialGradient>
  <radialGradient id="bhglow"><stop offset="0" stop-color="#f59e0b" stop-opacity=".32"/><stop offset=".5" stop-color="#9a3412" stop-opacity=".1"/><stop offset="1" stop-color="#9a3412" stop-opacity="0"/></radialGradient>
  <linearGradient id="disk" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#fde68a"/><stop offset=".35" stop-color="#f59e0b"/><stop offset=".75" stop-color="#9a3412"/><stop offset="1" stop-color="#451a03"/>
  </linearGradient>
  <radialGradient id="flare"><stop offset="0" stop-color="#e0f2fe" stop-opacity=".95"/><stop offset=".35" stop-color="#38bdf8" stop-opacity=".45"/><stop offset="1" stop-color="#38bdf8" stop-opacity="0"/></radialGradient>
  <linearGradient id="ground" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#16204a"/><stop offset=".3" stop-color="#080c1f"/><stop offset="1" stop-color="{VOID}"/></linearGradient>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="-360" y1="0" x2="0" y2="0">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".35" stop-color="#c4b5fd"/><stop offset=".65" stop-color="{CYAN}"/><stop offset="1" stop-color="#ffffff"/>
    <animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="1360 0" dur="6s" repeatCount="indefinite"/>
  </linearGradient>
</defs>
<g clip-path="url(#banner)">
  <rect width="{W}" height="{H}" fill="{VOID}"/>
  {nebula}
  {drifting(far, W, 240)}
  {drifting(mid, W, 140)}
  {"".join(sparkles)}
  {orion}
  {meteors}
  {black_hole}
  {planet}
  {satellite}
  <text x="500" y="52" text-anchor="middle" class="hi fi">HI THERE, I&#8217;M</text>
  <text x="500" y="108" text-anchor="middle" class="name fu" style="animation-delay:.15s" fill="#8b5cf6" opacity=".55" filter="url(#blur8)">{esc(NAME)}</text>
  <text x="500" y="108" text-anchor="middle" class="name fu" style="animation-delay:.15s" fill="url(#shine)">{esc(NAME)}</text>
  {roles}
  {caret}
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="url(#edge)"/>
</svg>
'''


def footer():
    W, H = 1000, 140
    rng = random.Random(11)
    text_zone = lambda x, y: 230 < x < 770 and 45 < y < 95
    far = starfield(rng, 60, (0, 0, W, H), r=(.25, .8), op=(.25, .7), twinkle=0)
    mid = starfield(rng, 26, (0, 0, W, H), r=(.6, 1.1), op=(.4, .9), twinkle=.4, avoid=text_zone)
    sparkles = []
    while len(sparkles) < 6:
        sx, sy = rng.uniform(20, W - 20), rng.uniform(14, H - 14)
        if not text_zone(sx, sy):
            sparkles.append(sparkle(sx, sy, rng.uniform(2.5, 4.5), "#fff", twinkle_style(rng)))

    path = "M-80,114 C280,86 720,126 1080,94"
    trail = "".join(
        f'<circle r="{2.2 - k * .3:.1f}" fill="{PINK if k % 2 else "#fbbf24"}" opacity="0">'
        f'<set attributeName="opacity" to="{.7 - k * .12:.2f}" begin="{.08 * k:.2f}s"/>'
        f'<animateMotion dur="13s" begin="{.08 * k:.2f}s" repeatCount="indefinite" path="{path}"/></circle>'
        for k in range(1, 6))
    rocket = (f'<g><animateMotion dur="13s" repeatCount="indefinite" rotate="auto" path="{path}"/>'
              '<path d="M-14,-3.2 L-26,0 L-14,3.2 Z" fill="#fbbf24" filter="url(#glowS)">'
              '<animate attributeName="d" values="M-14,-3.2 L-26,0 L-14,3.2 Z;M-14,-3.2 L-33,0 L-14,3.2 Z;M-14,-3.2 L-26,0 L-14,3.2 Z" dur=".25s" repeatCount="indefinite"/></path>'
              f'<path d="M-14,-5 L-19,-9 L-8,-5 Z" fill="{VIOLET}"/><path d="M-14,5 L-19,9 L-8,5 Z" fill="{VIOLET}"/>'
              '<path d="M-15,-5 L6,-5 C14,-5 20,-2 23,0 C20,2 14,5 6,5 L-15,5 Z" fill="#e2e8f0"/>'
              '<circle cx="6" cy="0" r="2.4" fill="#0ea5e9" stroke="#1e293b" stroke-width="1"/></g>')

    css = BASE_CSS + f".foot {{ font: 500 15px {SANS}; letter-spacing: .4px }}"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Thanks for visiting — see you among the stars">
<style>{css}</style>
<defs>
  {space_defs()}
  <clipPath id="banner"><rect width="{W}" height="{H}" rx="18"/></clipPath>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="-300" y1="0" x2="0" y2="0">
    <stop offset="0" stop-color="#cbd5e1"/><stop offset=".4" stop-color="#c4b5fd"/><stop offset=".6" stop-color="{CYAN}"/><stop offset="1" stop-color="#cbd5e1"/>
    <animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="1300 0" dur="7s" repeatCount="indefinite"/>
  </linearGradient>
</defs>
<g clip-path="url(#banner)">
  <rect width="{W}" height="{H}" fill="{VOID}"/>
  <ellipse cx="180" cy="120" rx="320" ry="110" fill="url(#nebA)"/>
  <ellipse cx="820" cy="20" rx="300" ry="100" fill="url(#nebB)"/>
  {drifting(far, W, 200)}
  {drifting(mid, W, 120)}
  {"".join(sparkles)}
  {meteor(620, 12, 22, 9, 3)}
  {sparkle(265, 66, 5, VIOLET, twinkle_style(rng))}{sparkle(735, 66, 5, CYAN, twinkle_style(rng))}
  <text x="500" y="72" text-anchor="middle" class="foot fi" fill="url(#shine)">Thanks for visiting — see you among the stars</text>
  {trail}
  {rocket}
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="18" fill="none" stroke="url(#edge)"/>
</svg>
'''


def divider():
    """Section divider: a faint star-lit line with a comet running along it."""
    W, H = 1000, 30
    rng = random.Random(5)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" aria-hidden="true">
<style>{BASE_CSS}</style>
<defs>
  {FILTERS}
  <linearGradient id="line"><stop offset="0" stop-color="{VIOLET}" stop-opacity="0"/><stop offset=".3" stop-color="{VIOLET}" stop-opacity=".55"/>
    <stop offset=".7" stop-color="{CYAN}" stop-opacity=".55"/><stop offset="1" stop-color="{CYAN}" stop-opacity="0"/></linearGradient>
  <linearGradient id="comet"><stop offset="0" stop-color="{CYAN}" stop-opacity="0"/><stop offset="1" stop-color="{CYAN}" stop-opacity=".9"/></linearGradient>
</defs>
<rect x="0" y="14.5" width="{W}" height="1" fill="url(#line)"/>
{sparkle(250, 15, 3.5, CYAN, twinkle_style(rng))}{sparkle(500, 15, 6, VIOLET, twinkle_style(rng))}{sparkle(750, 15, 3.5, CYAN, twinkle_style(rng))}
<g><animateTransform attributeName="transform" type="translate" from="-40 0" to="1080 0" dur="7s" repeatCount="indefinite"/>
  <rect x="-70" y="14" width="70" height="2" rx="1" fill="url(#comet)"/>
  <circle cx="0" cy="15" r="2.6" fill="#e0f2fe" filter="url(#glowS)"/>
</g>
</svg>
'''


def about():
    W, size, lh, x, top = 820, 15, 26, 28, 72
    cw = size * CHAR
    rows = len(ABOUT) + 1  # plus the idle prompt
    H = top + (rows - 1) * lh + 28

    cmd_n = sum(len(s) for _, s in ABOUT[0])
    t = .7
    starts = [t]
    t += cmd_n * .075 + .5
    cmd_done = t
    for line in ABOUT[1:]:
        starts.append(t)
        t += sum(len(s) for _, s in line) * .011 + .09  # output prints fast, line by line
    idle_at = t + .25
    total = max(idle_at + 9, 16)

    lines = ""
    for i, (line, s) in enumerate(zip(ABOUT, starts)):
        n = sum(len(txt) for _, txt in line)
        step = .075 if i == 0 else .011
        markup = "".join(f'<tspan class="{cls}">{esc(txt)}</tspan>' for cls, txt in line)
        lines += typed(f"l{i}", x, top + i * lh, markup, n, size,
                       type_points(s, n, cw, step), total, "term", full=True)

    cy = top - size * .82
    cmd_x = [(0, x)] + [(tt, x + wv + 1) for tt, wv in type_points(starts[0], cmd_n, cw, .075)]
    idle_y = top + (rows - 1) * lh
    fade_a, fade_b = (total - .9) / total, (total - .4) / total
    stars = starfield(random.Random(3), 46, (10, 40, W - 10, H - 8), r=(.3, 1.0), op=(.15, .5), twinkle=.3)

    css = BASE_CSS + (
        f".tt {{ font: 500 12px {SANS}; fill: {MUTED} }}"
        f".term {{ font: 400 {size}px {MONO} }}"
        f".k {{ fill: {CYAN} }} .v, .c {{ fill: #e2e8f0 }} .b {{ fill: {VIOLET} }}"
        f".s {{ fill: {PINK} }} .p {{ fill: #86efac; font-weight: 700 }}")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="about.yaml: {esc(NAME)}, Software Developer, India">
<style>{css}</style>
<defs>{space_defs()}<clipPath id="win"><rect width="{W}" height="{H}" rx="10"/></clipPath></defs>
<g clip-path="url(#win)">
  <rect width="{W}" height="{H}" fill="{CARD}"/>
  <ellipse cx="{W - 120}" cy="{H - 40}" rx="320" ry="160" fill="url(#nebA)"/>
  <ellipse cx="90" cy="60" rx="260" ry="120" fill="url(#nebB)"/>
  {stars}
  <rect width="{W}" height="34" fill="#0a0d1c" fill-opacity=".92"/>
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="none" stroke="url(#edge)"/>
<path d="M0,34.5 H{W}" stroke="{BORDER}"/>
<circle cx="22" cy="17" r="6" fill="#ff5f57"/><circle cx="42" cy="17" r="6" fill="#febc2e"/><circle cx="62" cy="17" r="6" fill="#28c840"/>
<text x="{W / 2}" y="21" text-anchor="middle" class="tt">amizhthan@github: ~/about.yaml</text>
<g>
  <animate attributeName="opacity" dur="{total:.3f}s" repeatCount="indefinite" keyTimes="0;{fade_a:.4f};{fade_b:.4f};1" values="1;1;0;0"/>
  {lines}
  <text x="{x}" y="{idle_y}" class="term" xml:space="preserve"><tspan class="p">$ </tspan></text>
  <g class="blink">
    <rect x="{x}" y="{cy:.1f}" width="{cw:.1f}" height="{size + 2}" fill="{CYAN}" visibility="hidden">
      {smil("x", cmd_x, total)}{smil("visibility", [(0, "visible"), (cmd_done - .2, "hidden")], total)}
    </rect>
    <rect x="{x + 2 * cw + 1:.1f}" y="{idle_y - size * .82:.1f}" width="{cw:.1f}" height="{size + 2}" fill="{CYAN}">
      {smil("visibility", [(0, "hidden"), (idle_at, "visible")], total)}
    </rect>
  </g>
</g>
</svg>
'''


def main():
    d = fetch()
    OUT.mkdir(exist_ok=True)
    (OUT / "stats.svg").write_text(card_stats(d))
    (OUT / "langs.svg").write_text(card_langs(d))
    (OUT / "heatmap.svg").write_text(card_heatmap(d))
    (OUT / "header.svg").write_text(header())
    (OUT / "footer.svg").write_text(footer())
    (OUT / "divider.svg").write_text(divider())
    (OUT / "about.svg").write_text(about())
    print(f"Generated 7 assets for @{USER}: "
          f"{d['stars']}* {d['repos']} repos {d['contributions']} contributions")


if __name__ == "__main__":
    main()
