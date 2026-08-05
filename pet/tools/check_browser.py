"""Is the pet's Brave profile usable, and are you signed into Google in it?

    python tools/check_browser.py            # headed, opens a real window
    python tools/check_browser.py --headless

The pet drives Brave from its own profile directory so it never locks or
borrows the window you're working in. That means it has its OWN Google
session — being signed in normally doesn't help. Any form that requires
sign-in will fail until you log in once, here.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true")
    ap.add_argument("--login", action="store_true",
                    help="open Google sign-in and wait for you to finish")
    args = ap.parse_args()

    print(f"browser : {config.BROWSER_PATH}")
    print(f"profile : {config.BROWSER_PROFILE}")
    exists = Path(config.BROWSER_PROFILE).is_dir()
    print(f"          {'existing profile' if exists else 'will be created now'}")
    if not config.BROWSER_PATH:
        print("\nNo browser found. Set BROWSER_PATH in .env")
        return 1

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            user_data_dir=config.BROWSER_PROFILE,
            executable_path=config.BROWSER_PATH,
            headless=args.headless,
            args=["--no-first-run", "--no-default-browser-check"],
        )
        page = ctx.pages[0] if ctx.pages else ctx.new_page()
        page.goto("https://myaccount.google.com/", wait_until="domcontentloaded",
                  timeout=45_000)
        page.wait_for_timeout(2500)

        # Not by URL: signed-out visitors get bounced to the marketing page at
        # google.com/account/about, which contains neither "signin" nor
        # "accounts.google.com" and so reads as signed in. The session cookie
        # is the thing that actually decides it.
        names = {c["name"] for c in ctx.cookies()
                 if "google.com" in c.get("domain", "")}
        signed_in = bool(names & {"SID", "__Secure-1PSID", "__Secure-3PSID"})

        print(f"\nlanded on: {page.url[:90]}")
        print(f"signed in: {'YES' if signed_in else 'NO'}")
        if not signed_in:
            print(f"           (no session cookie; {len(names)} google cookies present)")

        if args.login and not signed_in:
            print("\nSign in in the window that's open. Waiting up to 4 minutes…")
            try:
                page.wait_for_url(lambda u: "myaccount.google.com" in u
                                  and "signin" not in u, timeout=240_000)
                print("signed in — the profile will remember this.")
            except Exception:  # noqa: BLE001
                print("timed out; run again with --login when you're ready.")

        ctx.close()

    if not signed_in and not args.login:
        print("\nNot signed in. Forms that need a Google account will fail.")
        print("Fix once with:  python tools/check_browser.py --login")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
