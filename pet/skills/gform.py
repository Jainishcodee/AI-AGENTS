"""Reading and filling Google Forms.

Everything here keys on the **question text**, never on a CSS selector. Google
obfuscates class names and re-renders the form regularly, so a recorded
selector rots within weeks; "What is your name?" does not. A recipe recorded
today should still work after Google redesigns the page.

Nothing in this module submits anything. Submitting is a separate, explicit
call the pet only makes after you've clicked approve.
"""
import difflib
from dataclasses import dataclass, field

# Google Forms' DOM is generated, but its ARIA roles are stable and are what
# screen readers rely on — which makes them the most durable handle available.
ITEM = 'div[role="listitem"]'
HEADING = 'div[role="heading"]'


@dataclass
class Question:
    title: str
    kind: str                       # text | paragraph | radio | checkbox | dropdown
    options: list[str] = field(default_factory=list)
    required: bool = False

    def __str__(self) -> str:
        star = " *" if self.required else ""
        opts = f"  [{', '.join(self.options)}]" if self.options else ""
        return f"{self.title}{star}  ({self.kind}){opts}"


def _labels(item, selector: str) -> list[str]:
    out = []
    loc = item.locator(selector)
    for i in range(loc.count()):
        lbl = loc.nth(i).get_attribute("aria-label") or ""
        if lbl:
            out.append(lbl.strip())
    return out


def _classify(item) -> tuple[str, list[str]]:
    if item.locator("textarea").count():
        return "paragraph", []
    if item.locator('div[role="radio"]').count():
        return "radio", _labels(item, 'div[role="radio"]')
    if item.locator('div[role="checkbox"]').count():
        return "checkbox", _labels(item, 'div[role="checkbox"]')
    if item.locator('div[role="listbox"]').count():
        opts = [o for o in _labels(item, 'div[role="option"]') if o]
        return "dropdown", opts
    if item.locator('input[type="text"]').count():
        return "text", []
    return "unknown", []


def read_questions(page) -> list[Question]:
    """Every question on the page, in order."""
    out: list[Question] = []
    items = page.locator(ITEM)
    for i in range(items.count()):
        item = items.nth(i)
        head = item.locator(HEADING)
        if not head.count():
            continue
        raw = head.first.inner_text().strip()
        if not raw:
            continue
        # Google appends a "*" line to required questions.
        required = raw.rstrip().endswith("*")
        title = raw.rstrip().rstrip("*").strip()
        kind, options = _classify(item)
        out.append(Question(title, kind, options, required))
    return out


def _find_item(page, title: str):
    """Locate a question by its text, tolerating small wording drift."""
    items = page.locator(ITEM)
    titles = []
    for i in range(items.count()):
        head = items.nth(i).locator(HEADING)
        t = head.first.inner_text().strip().rstrip("*").strip() if head.count() else ""
        titles.append(t)
        if t == title:
            return items.nth(i)

    # Exact match failed — the question was reworded slightly, or whitespace
    # shifted. Accept a close match, but never a vague one.
    match = difflib.get_close_matches(title, [t for t in titles if t], n=1, cutoff=0.85)
    if match:
        return items.nth(titles.index(match[0]))
    return None


def read_answers(page) -> dict[str, object]:
    """What's currently filled in, keyed by question text.

    This is how a recipe gets recorded: you fill the form yourself, then the
    pet reads back what you put.
    """
    answers: dict[str, object] = {}
    for q in read_questions(page):
        item = _find_item(page, q.title)
        if item is None:
            continue
        if q.kind == "paragraph":
            v = item.locator("textarea").first.input_value()
        elif q.kind == "text":
            v = item.locator('input[type="text"]').first.input_value()
        elif q.kind == "radio":
            v = _checked(item, 'div[role="radio"]')
            v = v[0] if v else ""
        elif q.kind == "checkbox":
            v = _checked(item, 'div[role="checkbox"]')
        elif q.kind == "dropdown":
            v = _checked(item, 'div[role="option"]')
            v = v[0] if v else ""
        else:
            continue
        if v not in ("", [], None):
            answers[q.title] = v
    return answers


def _checked(item, selector: str) -> list[str]:
    out = []
    loc = item.locator(selector)
    for i in range(loc.count()):
        el = loc.nth(i)
        if (el.get_attribute("aria-checked") == "true"
                or el.get_attribute("aria-selected") == "true"):
            lbl = el.get_attribute("aria-label")
            if lbl:
                out.append(lbl.strip())
    return out


def fill(page, answers: dict[str, object]) -> tuple[list[str], list[str]]:
    """Replay recorded answers. Returns (filled, skipped) question titles.

    Anything that can't be matched is *skipped and reported*, never guessed at.
    A silently half-filled form is worse than one that says what it couldn't do.
    """
    filled, skipped = [], []
    for title, value in answers.items():
        item = _find_item(page, title)
        if item is None:
            skipped.append(f"{title} — not on the form any more")
            continue
        kind, options = _classify(item)
        try:
            if kind == "paragraph":
                item.locator("textarea").first.fill(str(value))
            elif kind == "text":
                item.locator('input[type="text"]').first.fill(str(value))
            elif kind in ("radio", "checkbox", "dropdown"):
                wanted = value if isinstance(value, list) else [value]
                sel = {"radio": 'div[role="radio"]',
                       "checkbox": 'div[role="checkbox"]',
                       "dropdown": 'div[role="option"]'}[kind]
                missing = [w for w in wanted if w not in options]
                if missing:
                    skipped.append(f"{title} — no option {missing[0]!r} any more")
                    continue
                for w in wanted:
                    item.locator(f'{sel}[aria-label="{w}"]').first.click()
            else:
                skipped.append(f"{title} — don't know how to fill a {kind}")
                continue
            filled.append(title)
        except Exception as e:  # noqa: BLE001 - one bad field shouldn't abort the rest
            skipped.append(f"{title} — {type(e).__name__}")
    return filled, skipped


def submit(page) -> bool:
    """Only ever called after you've approved the filled form."""
    for name in ("Submit", "Send"):
        btn = page.locator(f'div[role="button"]:has-text("{name}")')
        if btn.count():
            btn.first.click()
            return True
    return False
