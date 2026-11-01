#!/usr/bin/env python3
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import urllib.request
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
README = ROOT / "README.md"
SNAPSHOT = ASSETS / "telemetry.json"
USER = os.environ.get("GH_USER", "hsayvaidya23")
FEATURED_FALLBACK = "evidence-judge"
FONT = "ui-monospace,SFMono-Regular,Menlo,Consolas,monospace"
CW = 0.62

THEMES = {
    "dark": {
        "bg": "#05070d",
        "panel": "#0a101c",
        "grid": "#22d3ee",
        "grid_op": "0.06",
        "text": "#e6f1ff",
        "dim": "#94a3bd",
        "faint": "#1c2a3d",
        "cyan": "#22d3ee",
        "mag": "#e879f9",
        "green": "#a3e635",
        "glow": "1",
        "track": "#132033",
        "scan_op": "0.06",
    },
    "light": {
        "bg": "#f5f7fb",
        "panel": "#ffffff",
        "grid": "#0e7490",
        "grid_op": "0.07",
        "text": "#0b1220",
        "dim": "#45505f",
        "faint": "#d5dde8",
        "cyan": "#0e7490",
        "mag": "#a21caf",
        "green": "#4d7c0f",
        "glow": "0.12",
        "track": "#e3e9f1",
        "scan_op": "0.04",
    },
}

QUERY = """
query($login: String!, $after: String, $featured: String!) {
  user(login: $login) {
    contributionsCollection { totalCommitContributions totalIssueContributions }
    pullRequests(states: MERGED) { totalCount }
    pinnedItems(first: 6, types: REPOSITORY) {
      nodes { ... on Repository { name description isFork isPrivate stargazerCount pushedAt primaryLanguage { name } } }
    }
    featured: repository(name: $featured) {
      name description isFork isPrivate stargazerCount pushedAt primaryLanguage { name }
    }
    repositories(first: 100, after: $after, ownerAffiliations: OWNER, privacy: PUBLIC,
                 isFork: false, orderBy: {field: PUSHED_AT, direction: DESC}) {
      pageInfo { hasNextPage endCursor }
      nodes {
        languages(first: 20, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def gql(variables):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        sys.exit("GITHUB_TOKEN is required")
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": f"{USER}-profile-render"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        sys.exit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def repo_card(r):
    return {
        "name": r["name"],
        "desc": r["description"] or "",
        "lang": (r["primaryLanguage"] or {}).get("name") or "",
        "stars": r["stargazerCount"],
        "pushed": r["pushedAt"][:10],
    }


def fetch():
    repos, after, first = [], None, None
    while True:
        user = gql({"login": USER, "after": after, "featured": FEATURED_FALLBACK})
        first = first or user
        page = user["repositories"]
        repos.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        after = page["pageInfo"]["endCursor"]
    cc = first["contributionsCollection"]
    langs = {}
    for r in repos:
        for edge in r["languages"]["edges"]:
            langs[edge["node"]["name"]] = langs.get(edge["node"]["name"], 0) + edge["size"]
    total = sum(langs.values()) or 1
    pinned = [
        repo_card(r)
        for r in first["pinnedItems"]["nodes"]
        if r and not r["isFork"] and not r["isPrivate"]
    ][:3]
    label = "PINNED"
    if not pinned and first["featured"] and not first["featured"]["isPrivate"]:
        pinned = [repo_card(first["featured"])]
        label = "FEATURED"
    return {
        "commits": cc["totalCommitContributions"],
        "merged_prs": first["pullRequests"]["totalCount"],
        "issues": cc["totalIssueContributions"],
        "langs": [[n, round(b / total, 4)] for n, b in sorted(langs.items(), key=lambda kv: -kv[1])[:6]],
        "pinned": pinned,
        "pinned_label": label,
    }


def with_sync(d):
    digest = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()
    prev = {}
    if SNAPSHOT.exists():
        prev = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    if prev.get("hash") == digest:
        sync = prev["sync"]
    else:
        sync = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        SNAPSHOT.write_text(json.dumps({"hash": digest, "sync": sync}, indent=2) + "\n", encoding="utf-8")
    return {**d, "sync": sync}


def e(s):
    return escape(str(s))


def tw(text, size):
    return len(text) * size * CW


def wrap(text, width):
    lines, cur = [], ""
    for word in text.split():
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return lines


def clip_text(text, n):
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


def fmt(n):
    return f"{n:,}"


def style(t, h):
    return f"""<style>
svg,text{{font-family:{FONT}}}
text{{white-space:pre}}
.t{{fill:{t['text']}}}.d{{fill:{t['dim']}}}.c{{fill:{t['cyan']}}}.m{{fill:{t['mag']}}}.g{{fill:{t['green']}}}
.b{{font-weight:700}}
.static{{display:none}}
.scan{{animation:scan 7s linear infinite}}
.blink{{animation:blink 1.1s steps(1) infinite}}
.pulse{{animation:pulse 2.4s ease-in-out infinite}}
.rise{{animation:rise .7s ease-out both}}
.grow{{transform-box:fill-box;transform-origin:left center;animation:grow 1.4s cubic-bezier(.2,.8,.2,1) both}}
.growy{{transform-box:fill-box;transform-origin:center bottom;animation:growy 1.2s cubic-bezier(.2,.8,.2,1) both}}
.spin{{transform-box:fill-box;transform-origin:center;animation:spin 24s linear infinite}}
.spinr{{transform-box:fill-box;transform-origin:center;animation:spin 16s linear infinite reverse}}
.glc{{animation:glc 5.5s steps(1) infinite}}
.glm{{animation:glm 5.5s steps(1) infinite}}
.gls{{animation:gls 5.5s steps(1) infinite}}
@keyframes scan{{from{{transform:translateY(-24px)}}to{{transform:translateY({h}px)}}}}
@keyframes blink{{0%{{opacity:1}}50%{{opacity:0}}}}
@keyframes pulse{{0%,100%{{opacity:1}}50%{{opacity:.35}}}}
@keyframes rise{{from{{transform:translateY(10px)}}to{{transform:none}}}}
@keyframes grow{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
@keyframes growy{{from{{transform:scaleY(0)}}to{{transform:scaleY(1)}}}}
@keyframes spin{{to{{transform:rotate(360deg)}}}}
@keyframes glc{{0%,88%,100%{{opacity:0;transform:none}}89%{{opacity:.85;transform:translate(-5px,1px)}}91%{{opacity:.85;transform:translate(4px,-1px)}}93%{{opacity:.85;transform:translate(-2px,0)}}95%{{opacity:0}}}}
@keyframes glm{{0%,88%,100%{{opacity:0;transform:none}}89%{{opacity:.85;transform:translate(5px,-1px)}}91%{{opacity:.85;transform:translate(-4px,2px)}}93%{{opacity:.85;transform:translate(3px,0)}}95%{{opacity:0}}}}
@keyframes gls{{0%,90%,100%{{opacity:0;transform:none}}90.5%{{opacity:1;transform:translateX(14px)}}92%{{opacity:1;transform:translateX(-9px)}}93.5%{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{
*{{animation:none!important}}
.typed,.scanbar{{display:none}}
.static{{display:inline}}
}}
</style>"""


def defs(t, w, h, uid):
    return f"""<defs>
<pattern id="grid{uid}" width="24" height="24" patternUnits="userSpaceOnUse">
<path d="M24 0H0V24" fill="none" stroke="{t['grid']}" stroke-opacity="{t['grid_op']}" stroke-width="1"/>
</pattern>
<pattern id="lines{uid}" width="4" height="4" patternUnits="userSpaceOnUse">
<rect width="4" height="1" fill="{t['grid']}" fill-opacity="0.035"/>
</pattern>
<linearGradient id="scan{uid}" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="{t['cyan']}" stop-opacity="0"/>
<stop offset="1" stop-color="{t['cyan']}" stop-opacity="{t['scan_op']}"/>
</linearGradient>
<radialGradient id="vig{uid}" cx="50%" cy="45%" r="75%">
<stop offset="0.6" stop-color="{t['bg']}" stop-opacity="0"/>
<stop offset="1" stop-color="{t['bg']}" stop-opacity="0.65"/>
</radialGradient>
<filter id="glow{uid}" x="-20%" y="-40%" width="140%" height="180%">
<feGaussianBlur stdDeviation="3.2" result="b"/>
<feComponentTransfer in="b" result="bb"><feFuncA type="linear" slope="{t['glow']}"/></feComponentTransfer>
<feMerge><feMergeNode in="bb"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>
<clipPath id="frame{uid}"><rect x="1" y="1" width="{w-2}" height="{h-2}" rx="14"/></clipPath>
</defs>"""


def brackets(x, y, w, h, color, arm=22, sw=2.5, op=1):
    p = (
        f"M{x} {y+arm}V{y}H{x+arm}M{x+w-arm} {y}H{x+w}V{y+arm}"
        f"M{x+w} {y+h-arm}V{y+h}H{x+w-arm}M{x+arm} {y+h}H{x}V{y+h-arm}"
    )
    return f'<path d="{p}" fill="none" stroke="{color}" stroke-width="{sw}" stroke-opacity="{op}" stroke-linecap="square"/>'


def shell(t, w, h, uid, title, desc, body, scan=False):
    body = body.replace("glowU", f"glow{uid}")
    band = f'<rect class="scan scanbar" x="0" y="0" width="{w}" height="24" fill="url(#scan{uid})"/>' if scan else ""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="100%" role="img" aria-labelledby="ti{uid} de{uid}">
<title id="ti{uid}">{e(title)}</title>
<desc id="de{uid}">{e(desc)}</desc>
{style(t, h)}
{defs(t, w, h, uid)}
<g clip-path="url(#frame{uid})">
<rect width="{w}" height="{h}" fill="{t['bg']}"/>
<rect width="{w}" height="{h}" fill="url(#grid{uid})"/>
<rect width="{w}" height="{h}" fill="url(#lines{uid})"/>
{body}
<rect width="{w}" height="{h}" fill="url(#vig{uid})"/>
{band}
</g>
<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="14" fill="none" stroke="{t['cyan']}" stroke-opacity="0.28"/>
{brackets(10, 10, w-20, h-20, t['cyan'])}
</svg>
"""


def boot_lines(t, lines, x, x_end, y0, size, step, uid, begin=0.3):
    typed, static, clips = [], [], []
    b = begin
    width = x_end - x + 6
    cols = int((x_end - x) / (size * CW))
    for i, (body, status) in enumerate(lines):
        y = y0 + i * step
        dots = "." * max(2, cols - len(f"> {body} ") - len(status) - 1)
        sclass = "g" if status in ("[ok]", "green") else "m"
        row = (
            f'<text x="{x}" y="{y}" font-size="{size}"><tspan class="m b">&gt;</tspan> '
            f'<tspan class="t">{e(body)}</tspan> <tspan class="d">{dots}</tspan></text>'
            f'<text x="{x_end}" y="{y}" font-size="{size}" text-anchor="end" class="{sclass} b">{e(status)}</text>'
        )
        n = len(body) + 12
        dur = round(n * 0.03, 2)
        total = b + dur
        vals = ["0"] + [f"{(k / n) * width:.1f}" for k in range(n + 1)]
        keys = ["0"] + [f"{(b + dur * k / n) / total:.4f}" for k in range(n + 1)]
        clips.append(
            f'<clipPath id="tc{uid}{i}"><rect x="{x-4}" y="{y-size}" height="{size*1.5}" width="{width:.1f}">'
            f'<animate attributeName="width" values="{";".join(vals)}" keyTimes="{";".join(keys)}" '
            f'calcMode="discrete" begin="0s" dur="{total:.2f}s" fill="freeze"/></rect></clipPath>'
        )
        typed.append(f'<g clip-path="url(#tc{uid}{i})">{row}</g>')
        static.append(row)
        b += dur + 0.12
    last_y = y0 + (len(lines) - 1) * step
    cursor = (
        f'<rect class="blink" x="{x_end + size*0.4:.1f}" y="{last_y - size*0.8:.1f}" width="{size*0.55:.1f}" '
        f'height="{size*0.95:.1f}" fill="{t["cyan"]}"/>'
    )
    return (
        "<defs>" + "".join(clips) + "</defs>"
        + '<g class="typed">' + "".join(typed) + "</g>"
        + '<g class="static">' + "".join(static) + "</g>"
        + cursor
    )


def glitch_name(t, x, y, size, uid, spacing):
    name = "YASH VAIDYA"
    attrs = f'x="{x}" y="{y}" font-size="{size}" font-weight="800" letter-spacing="{spacing}"'
    return f"""<defs><clipPath id="band{uid}"><rect x="0" y="{y - size*0.45:.0f}" width="2000" height="{size*0.16:.0f}"/></clipPath></defs>
<text class="glc" {attrs} fill="{t['cyan']}">{name}</text>
<text class="glm" {attrs} fill="{t['mag']}">{name}</text>
<text {attrs} class="t" filter="url(#glow{uid})">{name}</text>
<g clip-path="url(#band{uid})"><text class="gls" {attrs} fill="{t['green']}">{name}</text></g>"""


def core(t, cx, cy, r, uid, labels):
    inner = r * 0.44
    centre = (
        f'<text x="{cx}" y="{cy + 2:.1f}" text-anchor="middle" font-size="34" class="g b" filter="url(#glow{uid})">10</text>'
        f'<text x="{cx}" y="{cy + 21:.1f}" text-anchor="middle" font-size="15" class="c b">CLIENTS</text>'
        if labels
        else f'<circle class="pulse" cx="{cx}" cy="{cy}" r="{r*0.14:.1f}" fill="{t["green"]}"/>'
    )
    ring = f"""<circle class="spin" cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{t['cyan']}" stroke-width="1.5" stroke-dasharray="3 9" stroke-opacity="0.8"/>
<circle class="spinr" cx="{cx}" cy="{cy}" r="{r*0.8:.1f}" fill="none" stroke="{t['mag']}" stroke-width="2" stroke-dasharray="40 14 6 14" stroke-opacity="0.75"/>
<circle class="spin" cx="{cx}" cy="{cy}" r="{r*0.6:.1f}" fill="none" stroke="{t['cyan']}" stroke-width="1" stroke-dasharray="90 30" stroke-opacity="0.6"/>
<circle cx="{cx}" cy="{cy}" r="{inner:.1f}" fill="{t['panel']}" fill-opacity="0.92" stroke="{t['cyan']}" stroke-opacity="0.5"/>
<circle class="pulse" cx="{cx}" cy="{cy}" r="{inner:.1f}" fill="none" stroke="{t['green']}" stroke-width="2" filter="url(#glow{uid})"/>
{centre}"""
    if not labels:
        return ring
    out = []
    for label, ang in [("browser-use", -150), ("evals", -30), ("llm infra", 35), ("azure aks", 145)]:
        a = math.radians(ang)
        px, py = cx + r * math.cos(a), cy + r * math.sin(a)
        lx, ly = cx + (r + 16) * math.cos(a), cy + (r + 16) * math.sin(a)
        anchor = "start" if math.cos(a) > 0.2 else "end"
        out.append(
            f'<circle cx="{px:.1f}" cy="{py:.1f}" r="4" fill="{t["mag"]}"/>'
            f'<text x="{lx:.1f}" y="{ly + 5:.1f}" text-anchor="{anchor}" font-size="15" class="d">{label}</text>'
        )
    return ring + "".join(out)


BOOT = [
    ("init yash.vaidya", "[ok]"),
    ("load agents: browser-use · real chrome", "[ok]"),
    ("attach llm infra: aks · terraform · helmfile", "[ok]"),
    ("shadow mode: decide like prod, never send", "[ok]"),
]
MOB_BOOT = [
    ("init yash.vaidya", "[ok]"),
    ("load agents: browser-use", "[ok]"),
    ("attach llm infra: aks", "[ok]"),
    ("shadow mode: never send", "[ok]"),
]
ROLE = "AGENTS · BROWSER AUTOMATION · EVALS · LLM INFRA"
HERO_DESC = (
    "Yash Vaidya, Founding AI Engineer at Sidecar, Bangalore: agents, browser automation, evals and LLM infra. "
    "In production since 2025 on a multi-tenant AI platform serving 10 clients on Azure AKS."
)
FOOT_LEFT = "LAT 12.97°N  LON 77.59°E"
FOOT_RIGHT = "LIVE TERMINAL ▸ yash-vaidya.vercel.app"


def hero(t, d, uid):
    w, h = 1200, 484
    boot = BOOT + [
        (f"sync github: {fmt(d['commits'])} commits · {fmt(d['merged_prs'])} merged prs", "[ok]"),
        ("run evals", "green"),
    ]
    body = f"""
<text x="56" y="52" font-size="15" class="c b" letter-spacing="2">SYS://HSAYVAIDYA23</text>
<text x="1144" y="52" font-size="15" text-anchor="end" class="d" letter-spacing="1">IN PROD SINCE <tspan class="g b">2025</tspan> <tspan class="m">//</tspan> FOUNDING ENGINEER</text>
<path d="M56 66H1144" stroke="{t['cyan']}" stroke-opacity="0.25"/>
{boot_lines(t, boot, 56, 740, 100, 18, 29, uid)}
{glitch_name(t, 52, 342, 88, uid, 4)}
<text x="56" y="386" font-size="18" class="b"><tspan class="c">FOUNDING AI ENGINEER @ SIDECAR</tspan><tspan class="m"> // </tspan><tspan class="t">{e(ROLE)}</tspan></text>
<text x="56" y="418" font-size="18"><tspan class="g b">◉ BANGALORE, IN</tspan><tspan class="d">  ·  production agents, and the infra that keeps them honest</tspan></text>
{core(t, 966, 190, 100, uid, True)}
<path d="M56 440H1144" stroke="{t['cyan']}" stroke-opacity="0.18"/>
<text x="56" y="464" font-size="15" class="d" letter-spacing="1">{e(FOOT_LEFT)}</text>
<text x="1144" y="464" font-size="15" text-anchor="end" class="c">{e(FOOT_RIGHT)}</text>
"""
    return shell(t, w, h, uid, "Yash Vaidya, Founding AI Engineer at Sidecar", HERO_DESC, body, scan=True)


def hero_mobile(t, d, uid):
    w, h = 600, 800
    boot = MOB_BOOT + [(f"sync: {fmt(d['commits'])} commits · {fmt(d['merged_prs'])} prs", "[ok]"), ("run evals", "green")]
    body = f"""
<text x="32" y="50" font-size="20" class="c b" letter-spacing="1">SYS://HSAYVAIDYA23</text>
<text x="568" y="50" font-size="20" text-anchor="end" class="g b">SINCE 2025</text>
<path d="M32 66H568" stroke="{t['cyan']}" stroke-opacity="0.25"/>
{boot_lines(t, boot, 32, 552, 106, 20, 34, uid)}
{glitch_name(t, 28, 384, 76, uid, 1)}
<text x="32" y="432" font-size="22" class="c b">FOUNDING AI ENGINEER</text>
<text x="32" y="462" font-size="22" class="b"><tspan class="c">@ SIDECAR</tspan><tspan class="m"> //</tspan></text>
<text x="32" y="494" font-size="20" class="t b">AGENTS · BROWSER AUTOMATION</text>
<text x="32" y="522" font-size="20" class="t b">EVALS · LLM INFRA</text>
<text x="32" y="558" font-size="20" class="g b">◉ BANGALORE, IN</text>
{core(t, 112, 660, 74, uid, False)}
<text x="222" y="628" font-size="20" class="t">IN PROD <tspan class="g b">SINCE 2025</tspan></text>
<text x="222" y="664" font-size="20" class="t">FOUNDING ENGINEER</text>
<text x="222" y="700" font-size="20" class="t"><tspan class="g b">10</tspan> CLIENTS</text>
<path d="M32 748H568" stroke="{t['cyan']}" stroke-opacity="0.18"/>
<text x="32" y="780" font-size="20" class="c">{e(FOOT_RIGHT)}</text>
"""
    return shell(t, w, h, uid, "Yash Vaidya, Founding AI Engineer at Sidecar", HERO_DESC, body, scan=True)


def tiles_of(d):
    return [
        ("COMMITS · 12 MO", fmt(d["commits"]), "cyan"),
        ("MERGED PRS", fmt(d["merged_prs"]), "mag"),
        ("ISSUES FILED", fmt(d["issues"]), "green"),
    ]


def tile(t, x, y, w, h, label, value, color, delay):
    return f"""<g class="rise" style="animation-delay:{delay}s">
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{t['panel']}" fill-opacity="0.85" stroke="{t['faint']}"/>
{brackets(x+6, y+6, w-12, h-12, t[color], arm=10, sw=1.5, op=0.9)}
<text x="{x+20}" y="{y+36}" font-size="15" class="d" letter-spacing="0.5">{e(label)}</text>
<text x="{x+20}" y="{y+h-26}" font-size="48" class="{color[0]} b" filter="url(#glowU)">{e(value)}</text>
</g>"""


def tile_row(t, x, y, w, h, label, value, color, delay):
    return f"""<g class="rise" style="animation-delay:{delay}s">
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{t['panel']}" fill-opacity="0.85" stroke="{t['faint']}"/>
{brackets(x+6, y+6, w-12, h-12, t[color], arm=10, sw=1.5, op=0.9)}
<text x="{x+22}" y="{y + h/2 + 7:.0f}" font-size="20" class="d">{e(label)}</text>
<text x="{x+w-22}" y="{y + h/2 + 15:.0f}" font-size="42" text-anchor="end" class="{color[0]} b" filter="url(#glowU)">{e(value)}</text>
</g>"""


def lang_rows(t, langs, x, y, w, step, fs):
    out = []
    name_w = fs * CW * 11 + 10
    pct_w = fs * CW * 6 + 10
    track = w - name_w - pct_w
    for i, (name, pct) in enumerate(langs):
        yy = y + i * step
        color = ["cyan", "mag", "green"][i % 3]
        out.append(
            f'<text x="{x}" y="{yy}" font-size="{fs}" class="t">{e(clip_text(name, 11))}</text>'
            f'<rect x="{x+name_w:.1f}" y="{yy - fs*0.62:.1f}" width="{track:.1f}" height="12" rx="2" fill="{t["track"]}"/>'
            f'<rect class="grow" style="animation-delay:{0.3 + i*0.12:.2f}s" x="{x+name_w:.1f}" y="{yy - fs*0.62:.1f}" '
            f'width="{max(3, track*pct):.1f}" height="12" rx="2" fill="{t[color]}" filter="url(#glowU)"/>'
            f'<text x="{x+w}" y="{yy}" font-size="{fs}" text-anchor="end" class="d">{pct*100:.1f}%</text>'
        )
    return "".join(out)


def meta_of(r):
    parts = [r["lang"]] if r["lang"] else []
    if r["stars"] > 0:
        parts.append(f"★ {r['stars']}")
    parts.append(f"last push {r['pushed']}")
    return " · ".join(parts)


def repo_cards(t, repos, x, y, w, fs, dfs, uid_glow=True):
    out, yy = [], y
    per_line = int((w - 44) / (dfs * CW))
    for i, r in enumerate(repos):
        lines = wrap(r["desc"], per_line)[:3]
        ch = 30 + fs * 1.2 + dfs * 1.5 * (len(lines) + 1) + 16
        color = ["cyan", "mag", "green"][i % 3]
        body = "".join(
            f'<text x="{x+22}" y="{yy + 30 + fs*1.2 + dfs*1.5*(j+1):.0f}" font-size="{dfs}" class="d">{e(ln)}</text>'
            for j, ln in enumerate(lines)
        )
        out.append(f"""<g class="rise" style="animation-delay:{0.3 + i*0.1:.2f}s">
<rect x="{x}" y="{yy}" width="{w}" height="{ch:.0f}" rx="8" fill="{t['panel']}" fill-opacity="0.85" stroke="{t['faint']}"/>
<rect x="{x}" y="{yy}" width="4" height="{ch:.0f}" rx="2" fill="{t[color]}"/>
{brackets(x+6, yy+6, w-12, ch-12, t[color], arm=10, sw=1.5, op=0.8)}
<text x="{x+22}" y="{yy + 24 + fs:.0f}" font-size="{fs}"><tspan class="m b">▸</tspan> <tspan class="t b">{e(clip_text(r["name"], 26))}</tspan></text>
{body}
<text x="{x+22}" y="{yy + 30 + fs*1.2 + dfs*1.5*(len(lines)+1):.0f}" font-size="{dfs}" class="c">{e(meta_of(r))}</text>
</g>""")
        yy += ch + 12
    return "".join(out), yy


def telemetry_desc(d):
    langs = ", ".join(f"{n} {p*100:.0f}%" for n, p in d["langs"])
    pins = ", ".join(f"{r['name']} ({meta_of(r)})" for r in d["pinned"])
    return (
        f"Last 12 months: {d['commits']} commits, {d['merged_prs']} merged pull requests, {d['issues']} issues filed. "
        f"Top languages: {langs}. {d['pinned_label'].title()}: {pins}. Synced {d['sync']}."
    )


def stats(t, d, uid):
    w = 1200
    tl = "".join(tile(t, 40 + i * 380, 78, 360, 124, *tv, 0.1 + i * 0.1) for i, tv in enumerate(tiles_of(d)))
    cards, end = repo_cards(t, d["pinned"], 620, 270, 540, 22, 18)
    h = max(530, int(end) + 20)
    body = f"""
<text x="40" y="52" font-size="18" class="c b" letter-spacing="2">◢ TELEMETRY <tspan class="m">//</tspan> <tspan class="t">@{e(USER)}</tspan></text>
<text x="1160" y="52" font-size="15" text-anchor="end" class="d" letter-spacing="1"><tspan class="g pulse">●</tspan> SYNC {e(d['sync'])}</text>
{tl}
<text x="40" y="250" font-size="15" class="d" letter-spacing="1">TOP LANGUAGES · BY BYTES · OWN REPOS</text>
{lang_rows(t, d['langs'], 40, 290, 540, 38, 18)}
<text x="620" y="250" font-size="15" class="d" letter-spacing="1">{e(d['pinned_label'])}</text>
{cards}
"""
    return shell(t, w, h, uid, "GitHub telemetry", telemetry_desc(d), body)


def stats_mobile(t, d, uid):
    w = 600
    tl = "".join(tile_row(t, 32, 78 + i * 98, 536, 86, *tv, 0.1 + i * 0.1) for i, tv in enumerate(tiles_of(d)))
    cards, end = repo_cards(t, d["pinned"], 32, 728, 536, 22, 20)
    h = int(end) + 70
    body = f"""
<text x="32" y="50" font-size="22" class="c b" letter-spacing="2">◢ TELEMETRY</text>
<text x="568" y="50" font-size="20" text-anchor="end" class="d">@{e(USER)}</text>
{tl}
<text x="32" y="412" font-size="20" class="d" letter-spacing="1">TOP LANGUAGES · BY BYTES</text>
{lang_rows(t, d['langs'], 32, 454, 536, 42, 20)}
<text x="32" y="712" font-size="20" class="d" letter-spacing="1">{e(d['pinned_label'])}</text>
{cards}
<text x="32" y="{h - 26}" font-size="20" class="d"><tspan class="g pulse">●</tspan> SYNC {e(d['sync'])}</text>
"""
    return shell(t, w, h, uid, "GitHub telemetry", telemetry_desc(d), body)


MISSIONS = [
    ("REAL-CHROME BROWSER AGENTS", "BROWSER-USE · AZURE LLMS",
     "Reliable on bot-protected portals",
     "~20 → 6–8 min", "manual workflow, end to end"),
    ("RPA INTO LIVE ERPS", "2FA/TOTP · WATCHDOGS",
     "Bots that write into live ERPs",
     "−52% latency", "event-driven waits instead of fixed sleeps"),
    ("INCIDENTS → ARCHITECTURE", "IDEMPOTENCY",
     "Idempotent writes to live systems",
     "0 duplicates", "240 of 240 runs with zero drift after the fix"),
    ("DETERMINISTIC CORE", "RESOLUTION ENGINE",
     "Deterministic first, LLM fallback",
     "420+ tests", "guarding the deterministic resolution engine"),
    ("SHADOW-FIRST AUTONOMY", "CONFIDENCE GATES",
     "Confidence gates and daily caps",
     "0 unsafe sends", "shadow mode decides like prod, by design it can't send"),
    ("MULTI-TENANT AI PLATFORM", "AZURE AKS · TERRAFORM",
     "LLM pipeline, bots, dashboard, K8s",
     "10 clients", "on one platform, built end to end as first engineer"),
]
ALSO = ["AI Podcast Clipper", "Farming Goat (5,000+ users)"]


def mission_card(t, i, m, x, y, w, h, uid, s):
    title, tag, body, value, caption = m
    color = ["cyan", "mag", "green"][i % 3]
    limit = int((w - 44) / (s["cap"] * CW))
    cap = wrap(caption, limit)
    if len(cap) == 2:
        cap = next(c for c in (wrap(caption, n) for n in range(len(caption) // 2, limit + 1)) if len(c) <= 2)
    capl = "".join(
        f'<text x="{x+22}" y="{y + s["cap_y"] + j*s["cap"]*1.3:.0f}" font-size="{s["cap"]}" class="d">{e(ln)}</text>'
        for j, ln in enumerate(cap)
    )
    return f"""<g class="rise" style="animation-delay:{0.15 + i*0.1:.2f}s">
<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="8" fill="{t['panel']}" fill-opacity="0.85" stroke="{t['faint']}"/>
<rect x="{x}" y="{y}" width="4" height="{h}" rx="2" fill="{t[color]}"/>
{brackets(x+6, y+6, w-12, h-12, t[color], arm=10, sw=1.5, op=0.7)}
<text x="{x+22}" y="{y+s['tag_y']}" font-size="{s['tag']}" class="m b" letter-spacing="1">M-{i+1:02d}</text>
<text x="{x+w-22}" y="{y+s['tag_y']}" font-size="{s['tag']}" text-anchor="end" class="g b">{e(tag)}</text>
<text x="{x+22}" y="{y+s['title_y']}" font-size="{s['title']}" class="t b">{e(title)}</text>
<text x="{x+22}" y="{y+s['body_y']}" font-size="{s['body']}" class="t" fill-opacity="0.85">{e(body)}</text>
<text x="{x+22}" y="{y+s['big_y']}" font-size="{s['big']}" class="{color[0]} b" filter="url(#glow{uid})">{e(value)}</text>
{capl}
</g>"""


DESK_CARD = {"tag": 15, "tag_y": 32, "title": 20, "title_y": 64, "body": 18, "body_y": 94,
             "big": 34, "big_y": 142, "cap": 15, "cap_y": 168}
MOB_CARD = {"tag": 20, "tag_y": 38, "title": 22, "title_y": 76, "body": 22, "body_y": 112,
            "big": 36, "big_y": 164, "cap": 20, "cap_y": 198}


def missions_desc():
    return " ".join(f"{m[0]}: {m[2]}. {m[3]}, {m[4]}." for m in MISSIONS) + " Also shipped: " + ", ".join(ALSO) + "."


def missions(t, uid):
    w, ch, gap = 1200, 208, 16
    cards = "".join(
        mission_card(t, i, m, 40 + (i % 2) * 568, 78 + (i // 2) * (ch + gap), 552, ch, uid, DESK_CARD)
        for i, m in enumerate(MISSIONS)
    )
    fy = 78 + 3 * (ch + gap)
    h = fy + 50 + 28
    body = f"""
<text x="40" y="52" font-size="18" class="c b" letter-spacing="2">◢ MISSION LOG <tspan class="m">//</tspan> <tspan class="t">SELECTED WORK</tspan></text>
<text x="1160" y="52" font-size="15" text-anchor="end" class="d" letter-spacing="1">IN PRODUCTION <tspan class="g b">2025 → NOW</tspan></text>
{cards}
<g class="rise" style="animation-delay:.8s">
<rect x="40" y="{fy}" width="1120" height="50" rx="6" fill="{t['panel']}" fill-opacity="0.85" stroke="{t['faint']}"/>
<text x="60" y="{fy+32}" font-size="18"><tspan class="g b">ALSO SHIPPED ▸</tspan> <tspan class="t">{e(' · '.join(ALSO))}</tspan></text>
</g>
"""
    return shell(t, w, h, uid, "Mission log: selected work", missions_desc(), body)


def missions_mobile(t, uid):
    ch, gap = 248, 16
    cards = "".join(
        mission_card(t, i, m, 32, 76 + i * (ch + gap), 536, ch, uid, MOB_CARD) for i, m in enumerate(MISSIONS)
    )
    fy = 76 + len(MISSIONS) * (ch + gap)
    items = "".join(f'<text x="52" y="{fy + 70 + j*30}" font-size="20" class="t">· {e(a)}</text>' for j, a in enumerate(ALSO))
    box_h = 52 + 30 * len(ALSO) + 8
    h = fy + box_h + 30
    body = f"""
<text x="32" y="50" font-size="22" class="c b" letter-spacing="2">◢ MISSION LOG</text>
<text x="568" y="50" font-size="20" text-anchor="end" class="g b">2025 → NOW</text>
{cards}
<g class="rise" style="animation-delay:.8s">
<rect x="32" y="{fy}" width="536" height="{box_h}" rx="6" fill="{t['panel']}" fill-opacity="0.85" stroke="{t['faint']}"/>
<text x="52" y="{fy+36}" font-size="20" class="g b">ALSO SHIPPED ▸</text>
{items}
</g>
"""
    return shell(t, 600, h, uid, "Mission log: selected work", missions_desc(), body)


STACK = [
    ("AI", ["LLMs", "RAG", "LangGraph", "LangChain", "browser-use", "structured outputs", "evals", "Langfuse", "OpenTelemetry", "pgvector"]),
    ("BACKEND", ["Python", "TypeScript", "FastAPI", "Flask", "Celery", "Redis", "PostgreSQL", "Playwright"]),
    ("INFRA", ["Azure AKS", "Kubernetes", "Terraform", "Helmfile", "Docker", "GitHub Actions", "Grafana", "Loki", "Prometheus", "Sentry"]),
    ("FRONTEND", ["React", "Next.js", "Tailwind", "tRPC"]),
]
MODULES = sum(len(v) for _, v in STACK)


def chip_row(t, items, x, y, max_w, fs, ch, color, delay):
    out, cx, cy = [], x, y
    for k, item in enumerate(items):
        cw = tw(item, fs) + 30
        if cx + cw > x + max_w:
            cx, cy = x, cy + ch + 10
        out.append(
            f'<g class="rise" style="animation-delay:{delay + k*0.03:.2f}s">'
            f'<rect x="{cx:.1f}" y="{cy}" width="{cw:.1f}" height="{ch}" rx="5" fill="{t["panel"]}" stroke="{t[color]}" stroke-opacity="0.55"/>'
            f'<text x="{cx + cw/2:.1f}" y="{cy + ch/2 + fs*0.36:.1f}" font-size="{fs}" text-anchor="middle" class="t">{e(item)}</text></g>'
        )
        cx += cw + 10
    return "".join(out), cy + ch


def stack_desc():
    return f"Stack, {MODULES} modules. " + " ".join(f"{k.title()}: {', '.join(v)}." for k, v in STACK)


def stack(t, uid):
    y, rows = 84, []
    for i, (label, items) in enumerate(STACK):
        color = ["cyan", "mag", "green", "cyan"][i]
        rows.append(f'<text x="40" y="{y + 26}" font-size="15" class="{color[0]} b" letter-spacing="2">{label}</text>')
        r, end = chip_row(t, items, 180, y, 980, 18, 40, color, 0.1 + i * 0.15)
        rows.append(r)
        y = end + 18
    body = f"""
<text x="40" y="52" font-size="18" class="c b" letter-spacing="2">◢ STACK</text>
<text x="1160" y="52" font-size="15" text-anchor="end" class="d" letter-spacing="1"><tspan class="g b">{MODULES}</tspan> MODULES LOADED</text>
{''.join(rows)}
"""
    return shell(t, 1200, y + 22, uid, "Stack", stack_desc(), body)


def stack_mobile(t, uid):
    y, rows = 80, []
    for i, (label, items) in enumerate(STACK):
        color = ["cyan", "mag", "green", "cyan"][i]
        rows.append(f'<text x="32" y="{y + 22}" font-size="20" class="{color[0]} b" letter-spacing="2">{label}</text>')
        r, end = chip_row(t, items, 32, y + 36, 536, 20, 44, color, 0.1 + i * 0.15)
        rows.append(r)
        y = end + 26
    body = f"""
<text x="32" y="50" font-size="22" class="c b" letter-spacing="2">◢ STACK</text>
<text x="568" y="50" font-size="20" text-anchor="end" class="d"><tspan class="g b">{MODULES}</tspan> MODULES</text>
{''.join(rows)}
"""
    return shell(t, 600, y + 16, uid, "Stack", stack_desc(), body)


CONTACTS = [
    ("site", "❯", "portfolio", "cyan"),
    ("email", "@", "email", "mag"),
    ("linkedin", "in", "linkedin", "cyan"),
    ("resume", "↓", "resume.pdf", "green"),
]


def chip(t, glyph, label, color):
    fs, h, gw = 18, 44, 44
    w = int(gw + 26 + tw(label, fs))
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{e(label)}">
<style>text{{font-family:{FONT};white-space:pre}}</style>
<rect x="1" y="1" width="{w-2}" height="{h-2}" rx="6" fill="{t['bg']}" stroke="{t[color]}" stroke-opacity="0.75"/>
<rect x="1" y="1" width="{gw}" height="{h-2}" rx="6" fill="{t[color]}" fill-opacity="0.16"/>
{brackets(5, 5, w-10, h-10, t[color], arm=6, sw=1.5, op=0.9)}
<text x="{gw/2 + 1:.1f}" y="{h/2 + fs*0.36:.1f}" font-size="{fs}" text-anchor="middle" font-weight="700" fill="{t[color]}">{e(glyph)}</text>
<text x="{gw + 13}" y="{h/2 + fs*0.36:.1f}" font-size="{fs}" fill="{t['text']}">{e(label)}</text>
</svg>
"""


def write(path, svg):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists() or path.read_text(encoding="utf-8") != svg:
        path.write_text(svg, encoding="utf-8")


def update_readme(sync):
    if not README.exists():
        return
    text = README.read_text(encoding="utf-8")
    new = re.sub(r"<!--sync-->.*?<!--/sync-->", f"<!--sync-->{sync}<!--/sync-->", text, flags=re.S)
    if new != text:
        README.write_text(new, encoding="utf-8")


def main():
    d = with_sync(fetch())
    for name, t in THEMES.items():
        u = name[0]
        write(ASSETS / f"hero-{name}.svg", hero(t, d, f"h{u}"))
        write(ASSETS / f"mobile-hero-{name}.svg", hero_mobile(t, d, f"hm{u}"))
        write(ASSETS / f"stats-{name}.svg", stats(t, d, f"s{u}"))
        write(ASSETS / f"mobile-stats-{name}.svg", stats_mobile(t, d, f"sm{u}"))
        write(ASSETS / f"missions-{name}.svg", missions(t, f"m{u}"))
        write(ASSETS / f"mobile-missions-{name}.svg", missions_mobile(t, f"mm{u}"))
        write(ASSETS / f"stack-{name}.svg", stack(t, f"k{u}"))
        write(ASSETS / f"mobile-stack-{name}.svg", stack_mobile(t, f"km{u}"))
        for key, glyph, label, color in CONTACTS:
            write(ASSETS / f"chip-{key}-{name}.svg", chip(t, glyph, label, color))
    update_readme(d["sync"])
    print(json.dumps({k: v for k, v in d.items() if k != "langs"}, indent=2))


if __name__ == "__main__":
    main()
