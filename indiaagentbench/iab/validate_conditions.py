"""Quality gates on the generated conditions, plus a review sheet for humans.

Machine translation is a draft. These checks catch the failures that can be
caught mechanically, so a native-speaker reviewer spends their attention on the
one thing only they can judge -- whether the sentence sounds like a real person.

The hard gates, any of which invalidates a task:

- **Digits preserved.** A mangled PNR or a spelled-out amount makes the task
  unsolvable, which would show up as a language effect when it is really a
  broken prompt. This is the single most dangerous silent failure in the whole
  pipeline, because it produces exactly the result the hypothesis predicts.
- **Script purity.** C2 must be Devanagari with no Tamil, C4 the reverse, and
  C3/C5 must be Latin-only. No word may splice two scripts.
- **Not an echo.** A model that returned the English unchanged has produced a
  duplicate of C1, not a condition.

Soft flags go to the reviewer rather than failing the build.

    python -m iab.validate_conditions
    python -m iab.validate_conditions --sheet review.html
"""
import argparse

from .common import TASKS, load_json
from .script_utils import digits_in, mixed_script_words, scripts_in
from .translate import CONDITIONS

# Rough English-token lexicon for estimating code-mix density in C3/C5. This is
# a proxy, not language identification -- reported as an indication, never as a
# measurement, and the paper should say so.
ENGLISH = set("""
a about all also am an and any are as at back be because been before but by can
cancel cancelled cancellation check could day days did do does done for from get
give go got has have he her him his how i if in into is it its just know like me
month more much my need no not now of on one only or other our out over please
refund same scheme see she should so some student such take tell than that the
their them then there these they this time to today told too total two up us use
very want was we were what when where which who why will with would you your
account amount apply application bank booking card certificate class document
documents eligible eligibility family form government help income insurance
land money name number office passenger pension people rupees salary scholarship
seat status submit ticket train travel year years
""".split())


def english_ratio(text):
    words = [w.strip(".,;:!?()\"'").lower() for w in text.split()]
    words = [w for w in words if w and not w.isdigit()]
    if not words:
        return 0.0
    return sum(1 for w in words if w in ENGLISH) / len(words)


def check(task):
    """Return (hard_failures, soft_flags) for one translated task."""
    cond = CONDITIONS[task["condition"]]
    src, out = task["user_goal_en"], task["user_goal"]
    hard, soft = [], []

    want, got = digits_in(src), digits_in(out)
    if want != got:
        hard.append(f"digits changed: {want} -> {got}")

    found = scripts_in(out)
    if cond["mixed"]:
        indic = found - {"Latn"}
        if indic:
            hard.append(f"expected Latin only, found {sorted(indic)}")
    else:
        if cond["script"] not in found:
            hard.append(f"no {cond['script']} text found")
        foreign = found - {cond["script"], "Latn"}
        if foreign:
            hard.append(f"foreign script present: {sorted(foreign)}")

    for word, scr in mixed_script_words(out):
        hard.append(f"script-mixed word {word!r} {scr}")

    if out.strip().lower() == src.strip().lower():
        hard.append("identical to the English source (model echoed the input)")
    if not out.strip():
        hard.append("empty")

    ratio = len(out) / max(len(src), 1)
    if not 0.4 <= ratio <= 3.0:
        soft.append(f"length {ratio:.2f}x the source")

    if cond["mixed"]:
        er = english_ratio(out)
        if not 0.15 <= er <= 0.75:
            soft.append(f"code-mix density looks off (~{er:.0%} English tokens)")

    if task["source"] != "human":
        soft.append("unvalidated machine-translation draft")

    return hard, soft


def load_all():
    rows = []
    for domain in ("rail", "schemes"):
        for cond in sorted(CONDITIONS):
            try:
                rows.extend(load_json(TASKS / f"{domain}_{cond}.json"))
            except FileNotFoundError:
                continue
    return rows


def sheet(rows, path):
    """Editable HTML review sheet that emits the override files directly.

    The reviewer edits in place and clicks one button per condition; the browser
    downloads a JSON file that drops straight into tasks/overrides/. No manual
    JSON authoring, which is the difference between validation happening and
    validation being permanently deferred.
    """
    def esc(s):
        return (str(s).replace("&", "&amp;").replace("<", "&lt;")
                .replace(">", "&gt;").replace('"', "&quot;"))

    parts = ["""<!doctype html><meta charset="utf-8">
<title>IndiaAgentBench - condition review</title>
<style>
 body{font:15px/1.6 system-ui,sans-serif;margin:2rem auto;max-width:1200px;color:#111}
 h1{font-size:1.4rem} h2{font-size:1.05rem;margin-top:2.4rem;color:#444}
 table{border-collapse:collapse;width:100%} td,th{border:1px solid #ddd;padding:.6rem;
 vertical-align:top;text-align:left} th{background:#f6f6f6;font-weight:600}
 .en{color:#666;width:32%} .ck{width:16%;font-size:.85rem}
 textarea{width:100%;min-height:5.2rem;font:inherit;font-size:1.02rem;border:1px solid #ccc;
 border-radius:4px;padding:.45rem;resize:vertical}
 textarea.edited{border-color:#0a7c2f;background:#f4fbf6}
 .hard{color:#b00020;font-weight:600} .soft{color:#946200} .ok{color:#0a7c2f}
 code{background:#f2f2f2;padding:.1rem .3rem;border-radius:3px}
 .ask{background:#fffbe6;border:1px solid #f0d98c;padding:.85rem 1.1rem;border-radius:6px}
 button{font:inherit;padding:.5rem .9rem;border-radius:5px;border:1px solid #888;
 background:#fff;cursor:pointer;margin:.6rem 0} button:hover{background:#f0f0f0}
 .bar{position:sticky;top:0;background:#fff;padding:.5rem 0;border-bottom:1px solid #eee;z-index:9}
</style>
<h1>IndiaAgentBench &mdash; condition review</h1>
<div class="ask"><b>What we need from you:</b> for each row, does the message on
the right sound like a real person phoning a helpline? Edit it in place if not.
Three things matter more than elegance:
<ul style="margin:.4rem 0">
<li>every number must be unchanged &mdash; digits stay digits, and numbers written
    out in words stay in words</li>
<li>the request must mean exactly what the English means, with nothing added or dropped</li>
<li>for the romanized rows, it should read the way people actually type &mdash;
    mixing English words in, not word-for-word transliteration</li>
</ul>
Edited rows turn green. When you finish a section, click its button to download
the override file and drop it into <code>tasks/overrides/</code>.</div>
<div class="bar"><span id="count"></span></div>"""]

    by = {}
    for r in rows:
        by.setdefault((r["condition"], r["domain"]), []).append(r)

    for (cond, domain), items in sorted(by.items()):
        key = f"{domain}_{cond}"
        parts.append(f"<h2>{cond} &middot; {domain} &middot; {CONDITIONS[cond]['label']}</h2>")
        parts.append(f"<button onclick=\"save('{key}')\">Download "
                     f"<code>{key}.json</code></button>")
        parts.append(f"<table data-sec='{key}'><tr><th>id</th><th class='en'>English (C1)</th>"
                     "<th>translated &mdash; edit here</th><th class='ck'>checks</th></tr>")
        for t in items:
            hard, soft = check(t)
            notes = "".join(f"<div class='hard'>{esc(h)}</div>" for h in hard) \
                    + "".join(f"<div class='soft'>{esc(s)}</div>" for s in soft)
            if not hard and not soft:
                notes = "<div class='ok'>ok</div>"
            parts.append(
                f"<tr><td><code>{esc(t['task_id'])}</code></td>"
                f"<td class='en'>{esc(t['user_goal_en'])}</td>"
                f"<td><textarea data-id='{esc(t['task_id'])}' "
                f"data-orig=\"{esc(t['user_goal'])}\">{esc(t['user_goal'])}</textarea></td>"
                f"<td class='ck'>{notes}</td></tr>")
        parts.append("</table>")

    parts.append("""
<script>
const areas = () => [...document.querySelectorAll('textarea')];
function mark(t){ t.classList.toggle('edited', t.value.trim() !== t.dataset.orig.trim()); tally(); }
function tally(){
  const n = areas().filter(t => t.classList.contains('edited')).length;
  document.getElementById('count').textContent =
    n + ' of ' + areas().length + ' rows edited';
}
areas().forEach(t => t.addEventListener('input', () => mark(t)));
tally();
function save(sec){
  const tbl = document.querySelector(`table[data-sec="${sec}"]`);
  const out = {};
  // Every row is exported, not just edited ones: appearing in the override file
  // is what marks a turn as human-approved rather than an unvalidated draft.
  tbl.querySelectorAll('textarea').forEach(t => { out[t.dataset.id] = t.value.trim(); });
  const blob = new Blob([JSON.stringify(out, null, 2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = sec + '.json'; a.click();
}
</script>""")

    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", help="write an HTML review sheet to this path")
    args = ap.parse_args()

    rows = load_all()
    if not rows:
        raise SystemExit("no translated conditions found -- run python -m iab.translate --all")

    bad = drafts = 0
    for t in rows:
        hard, soft = check(t)
        if hard:
            bad += 1
            print(f"  FAIL {t['condition']} {t['task_id']}")
            for h in hard:
                print(f"       {h}")
        if t["source"] != "human":
            drafts += 1

    print(f"\n{len(rows)} translated tasks: {bad} hard failures, "
          f"{drafts} still unvalidated drafts")
    if drafts:
        print("Drafts are not publishable. Native-speaker sign-off writes into "
              "tasks/overrides/<domain>_<condition>.json and survives regeneration.")

    if args.sheet:
        from pathlib import Path
        p = sheet(rows, Path(args.sheet))
        print(f"review sheet -> {p}")

    raise SystemExit(1 if bad else 0)


if __name__ == "__main__":
    main()
