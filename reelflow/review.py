"""Stage 4: render the distilled sample as a review page.

The point is judging extraction fidelity, so every card is shown next to the
raw caption it came from -- you should be able to catch a hallucination without
opening Instagram.
"""
import html
import json
from pathlib import Path

from common import DATA, load_json

OUT = Path(r"C:\Users\Jainish\AppData\Local\Temp\claude\g--AI-AGENTS"
           r"\ba1abcd2-70f4-4aa9-8498-bac3d8a8ac51\scratchpad\reelflow-review.html")

ACCENT = {"task": "task", "fact": "fact"}
SKIP_LABEL = {
    "needs_video": "Needs video",
    "entertainment": "Entertainment",
    "promotional": "Promotional",
    "empty": "Empty",
}

CSS = """
:root{
  --ground:#FBF7F8; --surface:#FFFFFF; --sunk:#F3EDEF;
  --ink:#1A1013; --ink-2:#5B4B51; --ink-3:#8B7880;
  --line:#E7DDE1;
  --task:#C43535; --fact:#00806F; --wait:#9A6410; --dead:#8B7880;
  --task-wash:#FBEDED; --fact-wash:#E6F6F3; --wait-wash:#FBF2E3; --dead-wash:#F3EDEF;
}
@media (prefers-color-scheme:dark){
  :root{
    --ground:#0B0608; --surface:#18101A; --sunk:#120B14;
    --ink:#F6EEF1; --ink-2:#B6A3AC; --ink-3:#7E6A74;
    --line:#2A1E2E;
    --task:#E74848; --fact:#00E5C9; --wait:#E8A33D; --dead:#7E6A74;
    --task-wash:#2A1216; --fact-wash:#04241F; --wait-wash:#2A1F0E; --dead-wash:#1C1420;
  }
}
:root[data-theme="light"]{
  --ground:#FBF7F8; --surface:#FFFFFF; --sunk:#F3EDEF;
  --ink:#1A1013; --ink-2:#5B4B51; --ink-3:#8B7880;
  --line:#E7DDE1;
  --task:#C43535; --fact:#00806F; --wait:#9A6410; --dead:#8B7880;
  --task-wash:#FBEDED; --fact-wash:#E6F6F3; --wait-wash:#FBF2E3; --dead-wash:#F3EDEF;
}
:root[data-theme="dark"]{
  --ground:#0B0608; --surface:#18101A; --sunk:#120B14;
  --ink:#F6EEF1; --ink-2:#B6A3AC; --ink-3:#7E6A74;
  --line:#2A1E2E;
  --task:#E74848; --fact:#00E5C9; --wait:#E8A33D; --dead:#7E6A74;
  --task-wash:#2A1216; --fact-wash:#04241F; --wait-wash:#2A1F0E; --dead-wash:#1C1420;
}

*{box-sizing:border-box}
body{
  margin:0; background:var(--ground); color:var(--ink);
  font-family:"Segoe UI Variable Text","Segoe UI",system-ui,-apple-system,sans-serif;
  font-size:15px; line-height:1.55;
}
.mono{font-family:"Cascadia Code",ui-monospace,Consolas,"SF Mono",monospace}
.wrap{max-width:1180px; margin:0 auto; padding:40px 24px 96px}

header{display:flex; flex-direction:column; gap:10px; margin-bottom:34px}
.eyebrow{
  font-size:11px; letter-spacing:.16em; text-transform:uppercase;
  color:var(--ink-3); font-family:"Cascadia Code",ui-monospace,Consolas,monospace;
}
h1{
  margin:0; font-size:clamp(28px,4.2vw,42px); line-height:1.1;
  letter-spacing:-.025em; font-weight:700; text-wrap:balance;
}
.sub{margin:0; color:var(--ink-2); max-width:64ch}

.verdict{
  display:grid; grid-template-columns:repeat(auto-fit,minmax(168px,1fr));
  gap:1px; background:var(--line); border:1px solid var(--line);
  border-radius:12px; overflow:hidden; margin-bottom:14px;
}
.stat{background:var(--surface); padding:18px 20px; display:flex; flex-direction:column; gap:5px}
.stat b{
  font-size:30px; font-weight:700; letter-spacing:-.03em; line-height:1;
  font-variant-numeric:tabular-nums;
}
.stat span{font-size:12px; color:var(--ink-2); line-height:1.35}
.stat.t b{color:var(--task)} .stat.f b{color:var(--fact)}
.stat.w b{color:var(--wait)} .stat.d b{color:var(--dead)}

.note{
  background:var(--wait-wash); border:1px solid var(--line);
  border-left:3px solid var(--wait); border-radius:8px;
  padding:14px 18px; margin-bottom:30px; font-size:14px; color:var(--ink-2);
}
.note b{color:var(--ink)}

.filters{display:flex; flex-wrap:wrap; gap:8px; margin-bottom:22px}
.chip{
  font:inherit; font-size:13px; cursor:pointer;
  background:var(--surface); color:var(--ink-2);
  border:1px solid var(--line); border-radius:999px; padding:7px 15px;
}
.chip:hover{color:var(--ink); border-color:var(--ink-3)}
.chip[aria-pressed="true"]{background:var(--ink); color:var(--ground); border-color:var(--ink)}
.chip:focus-visible{outline:2px solid var(--task); outline-offset:2px}

.rows{display:flex; flex-direction:column; gap:14px}
.row{
  background:var(--surface); border:1px solid var(--line);
  border-radius:12px; border-left:3px solid var(--stripe,var(--dead));
  display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);
  overflow:hidden;
}
.row[data-kind="task"]{--stripe:var(--task)}
.row[data-kind="fact"]{--stripe:var(--fact)}
.row[data-skip="needs_video"]{--stripe:var(--wait)}
.row.hide{display:none}
@media (max-width:820px){ .row{grid-template-columns:minmax(0,1fr)} }

.side{padding:18px 20px; min-width:0}
.side.src{background:var(--sunk); border-right:1px solid var(--line)}
@media (max-width:820px){ .side.src{border-right:0; border-bottom:1px solid var(--line)} }

.meta{
  display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin-bottom:11px;
  font-size:11px; color:var(--ink-3);
  font-family:"Cascadia Code",ui-monospace,Consolas,monospace;
}
.meta a{color:var(--ink-3)}
.meta a:hover{color:var(--ink)}
.tag{
  font-size:10px; letter-spacing:.08em; text-transform:uppercase;
  padding:3px 8px; border-radius:5px; font-weight:600;
}
.tag.task{background:var(--task-wash); color:var(--task)}
.tag.fact{background:var(--fact-wash); color:var(--fact)}
.tag.wait{background:var(--wait-wash); color:var(--wait)}
.tag.dead{background:var(--dead-wash); color:var(--dead)}

.cap{
  font-size:13px; color:var(--ink-2); white-space:pre-wrap; overflow-wrap:anywhere;
  max-height:11.5em; overflow:hidden; position:relative;
}
.cap::after{
  content:""; position:absolute; inset:auto 0 0 0; height:2.6em;
  background:linear-gradient(transparent,var(--sunk));
}
h3{margin:0 0 7px; font-size:17px; line-height:1.28; letter-spacing:-.012em; text-wrap:balance}
.summary{margin:0 0 13px; font-size:14px; color:var(--ink-2)}
dl{margin:0 0 13px; display:grid; grid-template-columns:auto minmax(0,1fr); gap:5px 12px; font-size:13.5px}
dt{
  font-size:10px; letter-spacing:.09em; text-transform:uppercase; color:var(--ink-3);
  font-family:"Cascadia Code",ui-monospace,Consolas,monospace; padding-top:4px;
}
dd{margin:0; color:var(--ink-2)}
ol{margin:0 0 13px; padding-left:19px; font-size:13.5px; color:var(--ink-2)}
ol li{margin-bottom:4px}
.ev{
  border-left:2px solid var(--line); padding:6px 0 6px 12px;
  font-size:12px; color:var(--ink-3); overflow-wrap:anywhere;
}
.tags{display:flex; flex-wrap:wrap; gap:5px; margin-top:11px}
.tags span{font-size:11px; color:var(--ink-3); background:var(--sunk); border-radius:4px; padding:2px 7px}
.side .tags span{background:var(--ground)}
footer{margin-top:44px; padding-top:20px; border-top:1px solid var(--line); font-size:12.5px; color:var(--ink-3)}
@media (prefers-reduced-motion:reduce){ *{transition:none!important; animation:none!important} }
"""

JS = """
const chips=[...document.querySelectorAll('.chip')];
const rows=[...document.querySelectorAll('.row')];
chips.forEach(c=>c.addEventListener('click',()=>{
  chips.forEach(o=>o.setAttribute('aria-pressed',o===c));
  const f=c.dataset.filter;
  rows.forEach(r=>{
    const show = f==='all'
      || (f==='card' && (r.dataset.kind==='task'||r.dataset.kind==='fact'))
      || (f==='needs_video' && r.dataset.skip==='needs_video')
      || (f==='dead' && r.dataset.kind==='skip' && r.dataset.skip!=='needs_video');
    r.classList.toggle('hide',!show);
  });
}));
"""


def esc(s):
    return html.escape(str(s or ""))


def render_card(c):
    """Right-hand side: what the model produced."""
    k = c["kind"]
    if k == "skip":
        lab = SKIP_LABEL.get(c.get("skip_reason"), "Skipped")
        cls = "wait" if c.get("skip_reason") == "needs_video" else "dead"
        body = [f'<span class="tag {cls}">{esc(lab)}</span>']
        body.append(f"<h3>{esc(c['title']) or 'No card'}</h3>")
        body.append(f"<p class='summary'>{esc(c['summary'])}</p>")
        if c.get("skip_reason") == "needs_video":
            body.append('<div class="ev">Recoverable &mdash; the caption is a hook, '
                        'so the content lives in the audio. Queued for pass 2.</div>')
        return "\n".join(body)

    out = [f'<span class="tag {k}">{k}</span>',
           f"<h3>{esc(c['title'])}</h3>",
           f"<p class='summary'>{esc(c['summary'])}</p>"]
    rows = []
    if k == "task":
        rows.append(("Effort", f"{esc(c.get('effort'))} &rarr; "
                               f"<b>{esc(c.get('horizon'))}</b>"))
        rows.append(("Repeat", esc(c.get("recurrence"))))
    else:
        rows.append(("Claim", esc(c.get("claim"))))
        if c.get("why"):
            rows.append(("Why", esc(c.get("why"))))
        if c.get("applicability") and c["applicability"].lower() != "none":
            rows.append(("Use when", esc(c.get("applicability"))))
    out.append("<dl>" + "".join(f"<dt>{a}</dt><dd>{b}</dd>" for a, b in rows) + "</dl>")
    if c.get("steps"):
        out.append("<ol>" + "".join(f"<li>{esc(s)}</li>" for s in c["steps"]) + "</ol>")
    if c.get("evidence"):
        out.append(f'<div class="ev">Evidence: &ldquo;{esc(c["evidence"])}&rdquo;</div>')
    if c.get("tags"):
        out.append('<div class="tags">' +
                   "".join(f"<span>{esc(t)}</span>" for t in c["tags"]) + "</div>")
    return "\n".join(out)


def main():
    items = {i["id"]: i for i in load_json(DATA / "items.json")}
    cards = load_json(DATA / "distilled_sample.json")

    n_task = sum(1 for c in cards if c["kind"] == "task")
    n_fact = sum(1 for c in cards if c["kind"] == "fact")
    n_wait = sum(1 for c in cards if c.get("skip_reason") == "needs_video")
    n_dead = len(cards) - n_task - n_fact - n_wait
    missed = sum(1 for c in cards if c.get("skip_reason") == "needs_video"
                 and items[c["id"]]["caption_len"] >= 100)

    body = []
    for c in cards:
        it = items[c["id"]]
        body.append(f"""
<article class="row" data-kind="{esc(c['kind'])}" data-skip="{esc(c.get('skip_reason',''))}">
  <div class="side src">
    <div class="meta">
      <span>@{esc(it['owner_user'])}</span><span>&middot;</span>
      <span>caption {it['caption_len']} chars</span><span>&middot;</span>
      <a href="{esc(it['url'])}" target="_blank" rel="noopener">open reel &nearr;</a>
    </div>
    <div class="cap">{esc(it['caption'][:620]) or '(empty caption)'}</div>
  </div>
  <div class="side">{render_card(c)}</div>
</article>""")

    doc = f"""<title>Reel &rarr; card extraction review</title>
<style>{CSS}</style>
<div class="wrap">
<header>
  <div class="eyebrow">Reelflow &middot; phase 1 proof &middot; 20 of 154 from &ldquo;Kjc&rdquo;</div>
  <h1>Does a saved reel survive the trip to a usable card?</h1>
  <p class="sub">Each row shows the raw Instagram caption on the left and what the model
  made of it on the right, so a wrong card is visible without opening the reel.
  Every card carries the quote that justifies it.</p>
</header>

<section class="verdict">
  <div class="stat t"><b>{n_task}</b><span>tasks extracted<br>from caption alone</span></div>
  <div class="stat f"><b>{n_fact}</b><span>facts extracted<br>from caption alone</span></div>
  <div class="stat w"><b>{n_wait}</b><span>recoverable once<br>the audio is transcribed</span></div>
  <div class="stat d"><b>{n_dead}</b><span>correctly dead<br>memes, ads, clips</span></div>
  <div class="stat"><b>{(n_task + n_fact + n_wait) * 100 // len(cards)}%</b>
    <span>projected yield<br>once pass 2 runs</span></div>
</section>

<div class="note"><b>Why caption length was the wrong filter.</b>
{missed} of the {n_wait} reels that need audio have captions longer than 100 characters &mdash;
a 494-character caption can still be pure hook. Pass 1 now decides what to transcribe
by reading the caption and reporting whether the substance is missing, which costs
nothing extra and catches the cases a length cutoff misses.</div>

<div class="filters">
  <button class="chip" data-filter="all" aria-pressed="true">All {len(cards)}</button>
  <button class="chip" data-filter="card" aria-pressed="false">Cards {n_task + n_fact}</button>
  <button class="chip" data-filter="needs_video" aria-pressed="false">Needs audio {n_wait}</button>
  <button class="chip" data-filter="dead" aria-pressed="false">Dead {n_dead}</button>
</div>

<div class="rows">{''.join(body)}</div>

<footer>Distilled with gemini-2.5-flash &middot; source collection &ldquo;Kjc&rdquo;
(154 items) standing in until the fresh export with &ldquo;Karle bhai&rdquo; and
&ldquo;True&rdquo; arrives.</footer>
</div>
<script>{JS}</script>"""

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(doc, encoding="utf-8")
    print(f"task={n_task} fact={n_fact} needs_video={n_wait} dead={n_dead} "
          f"heuristic_misses={missed}")
    print(f"-> {OUT}")


if __name__ == "__main__":
    main()
