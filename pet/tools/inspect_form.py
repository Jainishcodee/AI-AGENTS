"""Point this at a real Google Form and see what the pet sees.

    python tools/inspect_form.py "https://docs.google.com/forms/d/e/.../viewform"

Read-only — it never fills or submits anything. This is the first thing to run
when a form misbehaves, because it separates two very different failures:
"the page didn't load the way we expected" from "we loaded it but our
selectors don't match".

Reports the raw ARIA role counts alongside what gform.read_questions() made of
them. If the roles are present but the questions list is empty, the bug is in
gform.py. If the roles are missing too, the page didn't render (sign-in wall,
lazy loading, or a multi-page form).
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config                                    # noqa: E402
from skills import gform                         # noqa: E402

ROLES = ["listitem", "heading", "radio", "checkbox", "listbox", "option",
         "radiogroup", "button", "textbox"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--headed", action="store_true", help="show the window")
    ap.add_argument("--wait", type=int, default=4000, help="ms to settle")
    ap.add_argument("--dump", help="write the rendered HTML here")
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=config.BROWSER_PROFILE,
            executable_path=config.BROWSER_PATH,
            headless=not args.headed,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        try:
            page.goto(args.url, wait_until="domcontentloaded", timeout=45_000)
            page.wait_for_timeout(args.wait)

            print(f"title : {page.title()}")
            print(f"url   : {page.url[:100]}")
            low = page.url.lower()
            if "accounts.google.com" in low or "signin" in low:
                print("\nBounced to sign-in. This form needs an account:")
                print("  python tools/check_browser.py --login")
                return 1

            print("\nraw ARIA roles on the page")
            for r in ROLES:
                n = page.locator(f'[role="{r}"]').count()
                if n:
                    print(f"  {r:<12} {n}")

            print("\nwhat the pet reads")
            qs = gform.read_questions(page)
            if not qs:
                print("  nothing — see the role counts above for why")
            for q in qs:
                print(f"  {q}")

            print("\ncurrent answers (should be empty on a fresh form)")
            print(f"  {gform.read_answers(page) or 'none'}")

            # Google paginates long forms; a recipe recorded on page 1 will
            # quietly miss everything after it.
            nxt = page.locator('div[role="button"]:has-text("Next")').count()
            sub = page.locator('div[role="button"]:has-text("Submit")').count()
            print(f"\npaging: Next={nxt}  Submit={sub}")
            if nxt and not sub:
                print("  MULTI-PAGE — the pet only handles single-page forms today.")

            if args.dump:
                Path(args.dump).write_text(page.content(), encoding="utf-8")
                print(f"\nhtml -> {args.dump}")
        finally:
            ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
