#!/usr/bin/env python3
"""Generate the self-hosted, animated SVG assets for the profile README.

Third-party card services (github-readme-stats, activity-graph, capsule-render,
readme-typing-svg) run on free tiers that get paused or billed out, which breaks
the profile README with no warning. Everything here is rendered from the GitHub
GraphQL API and committed to the repo, so it can never fail to load.

Animation notes:
- GitHub loads these through <img>, so there is no JavaScript. Motion is SMIL
  (typing, waves, orbit, bar growth) plus CSS keyframes (fades, twinkle, blink).
- Resting state is always the final, visible state and animations run *from*
  hidden, so a renderer that ignores animation still shows the complete image.
- Typed text is monospace with textLength pinned to len * char width, so the
  reveal clip and cursor line up with the glyphs whichever font resolves.
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

THEMES = {
    "dark":  dict(bg="#0d1117", border="#30363d", title="#5cc8d7", text="#c9d1d9",
                  muted="#8b949e", empty="#161b22"),
    "light": dict(bg="#ffffff", border="#d0d7de", title="#1f6f8b", text="#24292f",
                  muted="#57606a", empty="#ebedf0"),
}
HEAT = {
    "dark":  ["#161b22", "#0e4b56", "#136b7c", "#2d97ab", "#5cc8d7"],
    "light": ["#ebedf0", "#c6e6ec", "#8ccfdb", "#4aa8bd", "#1f6f8b"],
}

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

BASE_CSS = """
@keyframes fade-up { from { opacity: 0; transform: translateY(8px) } }
@keyframes fade-in { from { opacity: 0 } }
@keyframes slide-in { from { opacity: 0; transform: translateX(-10px) } }
@keyframes twinkle { 0%, 100% { opacity: .15 } 50% { opacity: .9 } }
@keyframes blink { 50% { opacity: 0 } }
.fu { animation: fade-up .7s cubic-bezier(.2, .8, .2, 1) backwards }
.fi { animation: fade-in .6s ease-out backwards }
.si { animation: slide-in .5s cubic-bezier(.2, .8, .2, 1) backwards }
.blink { animation: blink 1s steps(1) infinite }
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


def wave(width, period, amp, base, edge, phase=0.0):
    """Closed sine-wave shape filled toward y=edge; width should be view + period."""
    n = max(2, int(width / period * 32))
    pts = " ".join(
        f"{i * width / n:.1f},{base + amp * math.sin(2 * math.pi * (i * width / n) / period + phase):.1f}"
        for i in range(n + 1))
    return f"M0,{edge} L{pts} L{width},{edge} Z"


def drift(path, fill, period, dur, reverse=False, opacity=1.0):
    """Translate a periodic wave by exactly one period, forever: a seamless loop."""
    a, b = (f"-{period}", "0") if reverse else ("0", f"-{period}")
    return (f'<g><animateTransform attributeName="transform" type="translate" from="{a} 0" '
            f'to="{b} 0" dur="{dur}s" repeatCount="indefinite"/>'
            f'<path d="{path}" fill="{fill}" opacity="{opacity}"/></g>')


# --- data cards -------------------------------------------------------------

def frame(w, h, t, body, title):
    c = THEMES[t]
    css = BASE_CSS + (
        f".t {{ font: 600 16px {SANS}; fill: {c['title']} }}"
        f".k {{ font: 400 13px {SANS}; fill: {c['text']} }}"
        f".v {{ font: 700 13px {SANS}; fill: {c['title']} }}"
        f".s {{ font: 400 11px {SANS}; fill: {c['muted']} }}")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
            f'role="img" aria-label="{esc(title)}">\n<style>{css}</style>\n'
            f'<rect x="0.5" y="0.5" width="{w - 1}" height="{h - 1}" rx="8" fill="{c["bg"]}" stroke="{c["border"]}"/>'
            f'<text x="24" y="34" class="t fi">{esc(title)}</text>'
            f'<rect x="24" y="42" width="44" height="2" rx="1" fill="{c["title"]}">{grow("width", 44, .3, .6)}</rect>\n'
            f'{body}\n</svg>\n')


def card_stats(d, t):
    rows = [("Total Stars Earned", d["stars"]), ("Total Commits", d["commits"]),
            ("Total PRs", d["prs"]), ("Total Issues", d["issues"]),
            ("Public Repositories", d["repos"]), ("Followers", d["followers"])]
    body = "".join(
        f'<g class="si" style="animation-delay:{.25 + i * .09:.2f}s">'
        f'<text x="24" y="{72 + i * 24}" class="k">{esc(k)}</text>'
        f'<text x="440" y="{72 + i * 24}" class="v" text-anchor="end">{v}</text></g>'
        for i, (k, v) in enumerate(rows))
    body += (f'<text x="24" y="{72 + len(rows) * 24 + 8}" class="s fi" style="animation-delay:.95s">'
             f'{d["contributions"]} contributions in the last year</text>')
    return frame(464, 72 + len(rows) * 24 + 24, t, body, f"{USER}'s GitHub Stats")


def card_langs(d, t):
    c, x, w, bar_y = THEMES[t], 24.0, 292, 60
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
    body = (f'<rect x="24" y="{bar_y}" width="{w}" height="10" rx="5" fill="{c["empty"]}"/>'
            f'<defs><clipPath id="bar"><rect x="24" y="{bar_y}" width="{w}" height="10" rx="5"/></clipPath></defs>'
            f'<g clip-path="url(#bar)">{bar}</g>' + legend)
    return frame(340, 96 + len(d["langs"]) * 24, t, body, "Most Used Languages")


def card_heatmap(d, t):
    c, pal = THEMES[t], HEAT[t]
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
            sq += (f'<rect x="{wx}" y="{y0 + day["weekday"] * pitch}" width="{cell}" height="{cell}" rx="2" '
                   f'fill="{pal[lvl]}"><title>{day["date"]}: {n}</title></rect>')
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
    scan = (f'<defs><linearGradient id="beam"><stop offset="0" stop-color="{c["title"]}" stop-opacity="0"/>'
            f'<stop offset=".7" stop-color="{c["title"]}" stop-opacity=".28"/>'
            f'<stop offset="1" stop-color="{c["title"]}" stop-opacity="0"/></linearGradient>'
            f'<clipPath id="grid"><rect x="{x0}" y="{y0 - 2}" width="{grid_w}" height="{grid_h + 2}"/></clipPath></defs>'
            f'<g clip-path="url(#grid)"><rect x="{x0 - 48}" y="{y0 - 2}" width="48" height="{grid_h + 2}" fill="url(#beam)">'
            f'<animateTransform attributeName="transform" type="translate" begin="1.4s" dur="7s" '
            f'repeatCount="indefinite" keyTimes="0;.55;1" values="0 0;{grid_w + 48} 0;{grid_w + 48} 0"/></rect></g>')

    w_total = x0 + grid_w + 16
    h_total = y0 + grid_h + 34
    ly = h_total - 12
    legend = f'<g class="fi" style="animation-delay:1.1s"><text x="{w_total - 186}" y="{ly}" class="s">Less</text>'
    for i, col in enumerate(pal):
        legend += f'<rect x="{w_total - 156 + i * 14}" y="{ly - 9}" width="10" height="10" rx="2" fill="{col}"/>'
    legend += (f'<text x="{w_total - 80}" y="{ly}" class="s">More</text>'
               f'<text x="24" y="{ly}" class="s">{d["contributions"]} contributions in the last year</text></g>')
    return frame(w_total, h_total, t, months + cols + scan + legend, "Contribution Activity")


# --- header, footer, terminal -----------------------------------------------

def header():
    W, H = 1000, 230
    size, y = 19, 150
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
             f'width="{cw * .55:.1f}" height="{size:.1f}" rx="1" fill="#5cc8d7">'
             f'{smil("x", cursor, total)}</rect></g>')

    rng = random.Random(42)
    stars = []
    while len(stars) < 44:
        sx, sy = rng.uniform(10, W - 10), rng.uniform(10, 150)
        if 200 < sx < 800 and 28 < sy < 170:
            continue  # keep the text area clean
        r = rng.choice((.7, .9, 1.1, 1.4))
        stars.append(f'<circle cx="{sx:.0f}" cy="{sy:.0f}" r="{r}" fill="#fff" opacity=".5" '
                     f'style="animation:twinkle {rng.uniform(2.5, 5.5):.1f}s ease-in-out '
                     f'{rng.uniform(0, 4):.1f}s infinite"/>')

    ox, oy, rx, ry = 880, 74, 74, 20
    orbit = (f'<g transform="rotate(-16 {ox} {oy})">'
             f'<ellipse cx="{ox}" cy="{oy}" rx="{rx}" ry="{ry}" fill="none" stroke="#fff" stroke-opacity=".2" stroke-dasharray="2 5"/>'
             f'<circle cx="{ox}" cy="{oy}" r="16" fill="url(#planet)"/>'
             f'<g><animateMotion dur="16s" repeatCount="indefinite" rotate="auto" '
             f'path="M{ox - rx},{oy} a{rx},{ry} 0 1,0 {2 * rx},0 a{rx},{ry} 0 1,0 -{2 * rx},0"/>'
             f'<rect x="-10" y="-2" width="7" height="4" fill="#5cc8d7" opacity=".85"/>'
             f'<rect x="3" y="-2" width="7" height="4" fill="#5cc8d7" opacity=".85"/>'
             f'<rect x="-2.5" y="-3" width="5" height="6" rx="1" fill="#fff"/></g></g>')

    css = BASE_CSS + (
        f".hi {{ font: 600 12px {SANS}; letter-spacing: 4px; fill: #9fd4e0 }}"
        f".name {{ font: 700 46px {SANS}; letter-spacing: .5px }}"
        f".role {{ font: 500 {size}px {MONO}; fill: #bfeaf2 }}")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(NAME)} — {esc(ROLES[0])}">
<style>{css}</style>
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#0F2027"/><stop offset=".5" stop-color="#203A43"/><stop offset="1" stop-color="#2C5364"/>
  </linearGradient>
  <radialGradient id="glow"><stop offset="0" stop-color="#5cc8d7" stop-opacity=".3"/><stop offset="1" stop-color="#5cc8d7" stop-opacity="0"/></radialGradient>
  <radialGradient id="planet" cx=".35" cy=".35"><stop offset="0" stop-color="#9ff0fb"/><stop offset=".6" stop-color="#1f6f8b"/><stop offset="1" stop-color="#0F2027"/></radialGradient>
  <linearGradient id="shine" gradientUnits="userSpaceOnUse" x1="-300" y1="0" x2="0" y2="0">
    <stop offset="0" stop-color="#ffffff"/><stop offset=".5" stop-color="#9ff0fb"/><stop offset="1" stop-color="#ffffff"/>
    <animateTransform attributeName="gradientTransform" type="translate" from="0 0" to="1300 0" dur="5s" repeatCount="indefinite"/>
  </linearGradient>
  <mask id="shape" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
    {drift(wave(W + 640, 640, 13, 164, 0), "#fff", 640, 9)}
  </mask>
</defs>
{drift(wave(W + 520, 520, 11, 186, 0, .8), "#2C5364", 520, 13, reverse=True, opacity=.35)}
{drift(wave(W + 400, 400, 9, 176, 0, 2.1), "#203A43", 400, 10, opacity=.6)}
<g mask="url(#shape)">
  <rect width="{W}" height="{H}" fill="url(#bg)"/>
  <ellipse cx="500" cy="96" rx="280" ry="72" fill="url(#glow)">
    <animateTransform attributeName="transform" type="translate" values="-150 0;150 0;-150 0" dur="18s" repeatCount="indefinite" calcMode="spline" keyTimes="0;.5;1" keySplines=".45 0 .55 1;.45 0 .55 1"/>
  </ellipse>
  {"".join(stars)}
  {orbit}
</g>
<text x="500" y="56" text-anchor="middle" class="hi fi">HI THERE, I&#8217;M</text>
<text x="500" y="106" text-anchor="middle" class="name fu" style="animation-delay:.15s" fill="url(#shine)">{esc(NAME)}</text>
{roles}
{caret}
</svg>
'''


def footer():
    W, H = 1000, 110
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" aria-hidden="true">
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#2C5364"/><stop offset=".5" stop-color="#203A43"/><stop offset="1" stop-color="#0F2027"/>
  </linearGradient>
  <mask id="shape" maskUnits="userSpaceOnUse" x="0" y="0" width="{W}" height="{H}">
    {drift(wave(W + 640, 640, 12, 58, H), "#fff", 640, 9, reverse=True)}
  </mask>
</defs>
{drift(wave(W + 520, 520, 10, 36, H, .8), "#2C5364", 520, 13, opacity=.35)}
{drift(wave(W + 400, 400, 9, 46, H, 2.1), "#203A43", 400, 10, reverse=True, opacity=.6)}
<rect width="{W}" height="{H}" fill="url(#bg)" mask="url(#shape)"/>
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

    css = BASE_CSS + (
        f".tt {{ font: 500 12px {SANS}; fill: #8b949e }}"
        f".term {{ font: 400 {size}px {MONO} }}"
        ".k { fill: #5cc8d7 } .v, .c { fill: #e6edf3 } .b { fill: #d2a8ff }"
        ".s { fill: #a5d6ff } .p { fill: #7ee787; font-weight: 700 }")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="about.yaml: {esc(NAME)}, Software Developer, India">
<style>{css}</style>
<defs><clipPath id="win"><rect width="{W}" height="{H}" rx="10"/></clipPath></defs>
<g clip-path="url(#win)">
  <rect width="{W}" height="{H}" fill="#0d1117"/>
  <rect width="{W}" height="34" fill="#161b22"/>
</g>
<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="none" stroke="#30363d"/>
<path d="M0,34.5 H{W}" stroke="#30363d"/>
<circle cx="22" cy="17" r="6" fill="#ff5f57"/><circle cx="42" cy="17" r="6" fill="#febc2e"/><circle cx="62" cy="17" r="6" fill="#28c840"/>
<text x="{W / 2}" y="21" text-anchor="middle" class="tt">amizhthan@github: ~/about.yaml</text>
<g>
  <animate attributeName="opacity" dur="{total:.3f}s" repeatCount="indefinite" keyTimes="0;{fade_a:.4f};{fade_b:.4f};1" values="1;1;0;0"/>
  {lines}
  <text x="{x}" y="{idle_y}" class="term" xml:space="preserve"><tspan class="p">$ </tspan></text>
  <g class="blink">
    <rect x="{x}" y="{cy:.1f}" width="{cw:.1f}" height="{size + 2}" fill="#5cc8d7" visibility="hidden">
      {smil("x", cmd_x, total)}{smil("visibility", [(0, "visible"), (cmd_done - .2, "hidden")], total)}
    </rect>
    <rect x="{x + 2 * cw + 1:.1f}" y="{idle_y - size * .82:.1f}" width="{cw:.1f}" height="{size + 2}" fill="#5cc8d7">
      {smil("visibility", [(0, "hidden"), (idle_at, "visible")], total)}
    </rect>
  </g>
</g>
</svg>
'''


def main():
    d = fetch()
    OUT.mkdir(exist_ok=True)
    for t in THEMES:
        (OUT / f"stats-{t}.svg").write_text(card_stats(d, t))
        (OUT / f"langs-{t}.svg").write_text(card_langs(d, t))
        (OUT / f"heatmap-{t}.svg").write_text(card_heatmap(d, t))
    (OUT / "header.svg").write_text(header())
    (OUT / "footer.svg").write_text(footer())
    (OUT / "about.svg").write_text(about())
    print(f"Generated 9 assets for @{USER}: "
          f"{d['stars']}* {d['repos']} repos {d['contributions']} contributions")


if __name__ == "__main__":
    main()
