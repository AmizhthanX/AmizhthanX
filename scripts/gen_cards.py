#!/usr/bin/env python3
"""Generate self-hosted GitHub stats SVG cards.

Third-party card services (github-readme-stats, activity-graph) run on free
tiers that get paused or billed out, which breaks the profile README with no
warning. This renders the same cards locally from the GitHub GraphQL API so
the images are committed to the repo and can never fail to load.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

USER = os.environ.get("GH_USER", "AmizhthanX")
NAME = os.environ.get("GH_NAME", "Amizhthan Senguttuvan")
OUT = Path(__file__).resolve().parent.parent / "assets"

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


def frame(w, h, t, body, title):
    c = THEMES[t]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(title)}">
<style>
  .t {{ font: 600 16px 'Segoe UI', Ubuntu, Sans-Serif; fill: {c['title']} }}
  .k {{ font: 400 13px 'Segoe UI', Ubuntu, Sans-Serif; fill: {c['text']} }}
  .v {{ font: 700 13px 'Segoe UI', Ubuntu, Sans-Serif; fill: {c['title']} }}
  .s {{ font: 400 11px 'Segoe UI', Ubuntu, Sans-Serif; fill: {c['muted']} }}
</style>
<rect x="0.5" y="0.5" width="{w-1}" height="{h-1}" rx="8" fill="{c['bg']}" stroke="{c['border']}"/>
<text x="24" y="34" class="t">{esc(title)}</text>
{body}
</svg>'''


def card_stats(d, t):
    rows = [("Total Stars Earned", d["stars"]), ("Total Commits", d["commits"]),
            ("Total PRs", d["prs"]), ("Total Issues", d["issues"]),
            ("Public Repositories", d["repos"]), ("Followers", d["followers"])]
    body = "".join(
        f'<text x="24" y="{68 + i*24}" class="k">{esc(k)}</text>'
        f'<text x="440" y="{68 + i*24}" class="v" text-anchor="end">{v}</text>'
        for i, (k, v) in enumerate(rows))
    body += f'<text x="24" y="{68 + len(rows)*24 + 8}" class="s">{d["contributions"]} contributions in the last year</text>'
    return frame(464, 68 + len(rows) * 24 + 24, t, body, f"{USER}'s GitHub Stats")


def card_langs(d, t):
    c, x, w, bar_y = THEMES[t], 24, 292, 56
    body, legend = "", ""
    for i, (name, pct, col) in enumerate(d["langs"]):
        seg = max(w * pct / 100, 2)
        body += f'<rect x="{x:.1f}" y="{bar_y}" width="{seg:.1f}" height="10" fill="{col}"/>'
        x += seg
        row, col_i = i // 2, i % 2
        lx, ly = 24 + col_i * 152, 92 + row * 22
        legend += (f'<circle cx="{lx+5}" cy="{ly-4}" r="5" fill="{col}"/>'
                   f'<text x="{lx+17}" y="{ly}" class="k">{esc(name)}</text>'
                   f'<text x="{lx+140}" y="{ly}" class="s" text-anchor="end">{pct:.1f}%</text>')
    body = (f'<rect x="24" y="{bar_y}" width="{w}" height="10" rx="5" fill="{c["empty"]}"/>'
            f'<g clip-path="url(#r)">{body}</g>'
            f'<defs><clipPath id="r"><rect x="24" y="{bar_y}" width="{w}" height="10" rx="5"/></clipPath></defs>'
            + legend)
    rows = (len(d["langs"]) + 1) // 2
    return frame(340, 92 + rows * 22 + 16, t, body, "Most Used Languages")


def card_heatmap(d, t):
    c, pal = THEMES[t], HEAT[t]
    weeks = d["weeks"]
    cell, gap, x0, y0 = 10, 3, 30, 52
    peak = max((day["contributionCount"] for w in weeks for day in w["contributionDays"]), default=0)
    sq, months, seen = "", "", set()
    for wi, w in enumerate(weeks):
        wx = x0 + wi * (cell + gap)
        for day in w["contributionDays"]:
            n = day["contributionCount"]
            lvl = 0 if n == 0 else min(4, 1 + int(n / max(peak, 1) * 3.999))
            dy = y0 + day["weekday"] * (cell + gap)
            sq += (f'<rect x="{wx}" y="{dy}" width="{cell}" height="{cell}" rx="2" '
                   f'fill="{pal[lvl]}"><title>{day["date"]}: {n}</title></rect>')
        m = w["contributionDays"][0]["date"][:7]
        label = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][int(m[5:7])-1]
        if m not in seen and wi < len(weeks) - 2:
            seen.add(m)
            months += f'<text x="{wx}" y="{y0-8}" class="s">{label}</text>'
    for i, lbl in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        sq += f'<text x="0" y="{y0 + i*(cell+gap) + 9}" class="s">{lbl}</text>'
    w_total = x0 + len(weeks) * (cell + gap) + 16
    h_total = y0 + 7 * (cell + gap) + 34
    ly = h_total - 12
    legend = f'<text x="{w_total-186}" y="{ly}" class="s">Less</text>'
    for i, col in enumerate(pal):
        legend += f'<rect x="{w_total-156+i*14}" y="{ly-9}" width="10" height="10" rx="2" fill="{col}"/>'
    legend += f'<text x="{w_total-80}" y="{ly}" class="s">More</text>'
    legend += f'<text x="24" y="{ly}" class="s">{d["contributions"]} contributions in the last year</text>'
    return frame(w_total, h_total, t, months + sq + legend, "Contribution Activity")


def banner(kind):
    """Header/footer wave banner. Self-hosted so the profile does not depend on
    capsule-render.vercel.app, which is the same class of free instance that
    took down the stats cards."""
    w, h = (1000, 200) if kind == "header" else (1000, 110)
    if kind == "header":
        wave = ("M0,120 C150,170 260,70 420,105 C580,140 700,60 860,95 "
                "C920,108 970,120 1000,112 L1000,0 L0,0 Z")
        text = (f'<text x="500" y="88" text-anchor="middle" class="n">{esc(NAME)}</text>'
                f'<text x="500" y="122" text-anchor="middle" class="d">'
                f'Software Developer &#183; AI/ML &#183; Full-Stack</text>')
    else:
        wave = ("M0,0 C150,52 260,-14 420,22 C580,58 700,-14 860,18 "
                "C920,30 970,42 1000,34 L1000,110 L0,110 Z")
        text = ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}" role="img" aria-label="{esc(NAME)}">
<defs>
  <linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0%" stop-color="#0F2027"/>
    <stop offset="50%" stop-color="#203A43"/>
    <stop offset="100%" stop-color="#2C5364"/>
  </linearGradient>
</defs>
<style>
  .n {{ font: 700 44px 'Segoe UI', Ubuntu, Sans-Serif; fill: #ffffff; letter-spacing: .5px }}
  .d {{ font: 400 17px 'Segoe UI', Ubuntu, Sans-Serif; fill: #9fd4e0 }}
</style>
<path d="{wave}" fill="url(#g)"/>
{text}
</svg>'''


def main():
    d = fetch()
    OUT.mkdir(exist_ok=True)
    for t in THEMES:
        (OUT / f"stats-{t}.svg").write_text(card_stats(d, t))
        (OUT / f"langs-{t}.svg").write_text(card_langs(d, t))
        (OUT / f"heatmap-{t}.svg").write_text(card_heatmap(d, t))
    (OUT / "header.svg").write_text(banner("header"))
    (OUT / "footer.svg").write_text(banner("footer"))
    print(f"Generated 8 assets for @{USER}: "
          f"{d['stars']}* {d['repos']} repos {d['contributions']} contributions")


if __name__ == "__main__":
    main()
