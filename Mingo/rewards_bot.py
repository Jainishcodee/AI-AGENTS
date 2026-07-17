"""Drives Microsoft Edge through the Bing / Microsoft Rewards tasks on the
SPARE account: desktop searches, mobile-UA searches, and a best-effort pass
over the Daily Set / "More activities" cards. Then reads the points balance.

Notes / honesty:
  * Automating Microsoft Rewards breaks Microsoft's Terms of Service. Run this
    on a throwaway account; it can get suspended.
  * No CAPTCHA solving, no stealth fingerprint spoofing. If Bing challenges,
    Mingo stops and says so.
  * Bing's rewards page DOM changes frequently. The searches are stable; the
    activity-card clicking is best-effort and wrapped in try/except — if it
    stops finding cards, update the CSS selectors in _do_activities().
"""
import random
import re
import time
from dataclasses import dataclass
from urllib.parse import quote_plus

from playwright.sync_api import TimeoutError as PWTimeout
from playwright.sync_api import sync_playwright

import config

REWARDS_URL = "https://rewards.bing.com/"
BING_SEARCH = "https://www.bing.com/search?q={}&form=QBLH"
LOGIN_URL = "https://login.live.com/"

# We deliberately DON'T launch the installed Edge — Edge auto-signs in with the
# Windows account via WAM SSO, which leaks the user's main account into our
# sandbox profile. We use Playwright's bundled Chromium with an Edge user-agent
# instead: no SSO, but Bing/Rewards still sees an "Edge" client.
DESKTOP_EDGE_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36 Edg/122.0.0.0"
)
MOBILE_UA = (
    "Mozilla/5.0 (Linux; Android 13; Pixel 7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36 EdgA/122.0.0.0"
)


@dataclass
class Report:
    desktop_done: int = 0
    mobile_done: int = 0
    activities_done: int = 0
    points: str = "unknown"
    note: str = ""

    def spoken(self) -> str:
        msg = (
            f"All done. {self.desktop_done} desktop searches, "
            f"{self.mobile_done} mobile searches, and {self.activities_done} "
            f"activities. Balance is {self.points} points."
        )
        if self.note:
            msg += " " + self.note
        return msg


def _pause(a: float = 2.5, b: float = 6.5) -> None:
    time.sleep(random.uniform(a, b))


def _on_dashboard(page) -> bool:
    url = (page.url or "").lower()
    return "rewards" in url and "login" not in url and "live.com" not in url


# --------------------------------------------------------------------------- #
# sign-in
# --------------------------------------------------------------------------- #
def _ensure_signed_in(page) -> bool:
    page.goto(REWARDS_URL, wait_until="domcontentloaded")
    _pause(2, 4)
    if _on_dashboard(page):
        return True

    print(">> Spare account isn't signed in yet.")
    if config.MS_EMAIL and config.MS_PASSWORD:
        print(">> Attempting automatic sign-in...")
        try:
            page.goto(LOGIN_URL, wait_until="domcontentloaded")
            page.fill('input[type="email"]', config.MS_EMAIL, timeout=8000)
            page.click('#idSIButton9, input[type="submit"]')
            page.wait_for_timeout(2500)
            page.fill('input[type="password"]', config.MS_PASSWORD, timeout=8000)
            page.click('#idSIButton9, input[type="submit"]')
            page.wait_for_timeout(3500)
        except Exception as e:  # noqa: BLE001
            print(f">> Auto sign-in couldn't finish ({e}); do it by hand.")

    print(">> Finish signing in (and any 2FA / 'stay signed in?') in the Edge window.")
    print(">> Mingo will continue on its own once it sees the rewards dashboard...")
    for _ in range(60):  # ~5 minutes
        try:
            page.goto(REWARDS_URL, wait_until="domcontentloaded")
        except Exception:  # noqa: BLE001
            pass
        if _on_dashboard(page):
            print(">> Signed in. Continuing.")
            return True
        time.sleep(5)
    return False


# --------------------------------------------------------------------------- #
# searches
# --------------------------------------------------------------------------- #
def _do_searches(page, count: int, label: str) -> int:
    from search_terms import get_search_terms

    done = 0
    for i, term in enumerate(get_search_terms(count), 1):
        try:
            page.goto(BING_SEARCH.format(quote_plus(term)), wait_until="domcontentloaded")
            try:
                page.mouse.wheel(0, random.randint(200, 1400))
            except Exception:  # noqa: BLE001
                pass
            body = ""
            try:
                body = page.inner_text("body").lower()
            except Exception:  # noqa: BLE001
                pass
            if "verify you are a human" in body or "unusual traffic" in body or "captcha" in body:
                print(f"   [{label}] hit a CAPTCHA / challenge — stopping {label} searches.")
                break
            done += 1
            print(f"   [{label}] {i}/{count}: {term}")
            _pause(2.5, 7.0)
        except Exception as e:  # noqa: BLE001
            print(f"   [{label}] search failed ({term!r}): {e}")
            _pause(2, 4)
    return done


# --------------------------------------------------------------------------- #
# daily set / more activities  (best-effort)
# --------------------------------------------------------------------------- #
_CARD_SELECTORS = [
    "mee-card .actionLink a",
    "mee-card a.ds-card-sec",
    "mee-rewards-daily-set-item-content a",
    ".rewards-card-container a",
    "div[class*='rewardsCard'] a",
]
_QUIZ_OPTION_SELECTORS = [
    "#rqAnswerOption0", ".rqOption", ".wk_OptionClickClass",
    ".rqAnswerOption", ".btOptionCard", "a[id^='QuestionId']",
]


def _click_through_quiz(tab) -> None:
    for sel in _QUIZ_OPTION_SELECTORS:
        try:
            opts = tab.locator(sel)
            n = opts.count()
            if not n:
                continue
            for k in range(min(n, 10)):
                try:
                    opts.nth(k).click(timeout=2000)
                    tab.wait_for_timeout(1500)
                except Exception:  # noqa: BLE001
                    pass
            return
        except Exception:  # noqa: BLE001
            pass


def _do_activities(ctx) -> int:
    page = ctx.new_page()
    done = 0
    try:
        page.goto(REWARDS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(5000)

        links = []
        for sel in _CARD_SELECTORS:
            try:
                loc = page.locator(sel)
                for i in range(loc.count()):
                    links.append(loc.nth(i))
            except Exception:  # noqa: BLE001
                pass
        print(f"   found ~{len(links)} activity link(s)")

        for idx, link in enumerate(links, 1):
            try:
                with ctx.expect_page(timeout=8000) as new_tab_info:
                    link.click(timeout=5000)
                tab = new_tab_info.value
                tab.wait_for_timeout(4000)
                _click_through_quiz(tab)
                tab.wait_for_timeout(1500)
                tab.close()
                done += 1
                print(f"   activity {idx}/{len(links)} done")
                _pause(2, 5)
            except PWTimeout:
                _pause(1, 2)  # no new tab — likely already completed or inline
            except Exception as e:  # noqa: BLE001
                print(f"   activity {idx} skipped: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"   activities pass failed: {e}")
    finally:
        try:
            page.close()
        except Exception:  # noqa: BLE001
            pass
    return done


# --------------------------------------------------------------------------- #
# points readout
# --------------------------------------------------------------------------- #
def _read_points(page) -> str:
    try:
        page.goto(REWARDS_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        body = page.inner_text("body")
        m = re.search(r"Available points[^\d]{0,25}([\d,]{1,9})", body, re.IGNORECASE)
        if m:
            return m.group(1)
        m = re.search(r"([\d,]{2,9})\s*points\b", body, re.IGNORECASE)
        if m:
            return m.group(1)
    except Exception as e:  # noqa: BLE001
        print(f"   couldn't read points: {e}")
    return "unknown"


# --------------------------------------------------------------------------- #
# context helpers + entry point
# --------------------------------------------------------------------------- #
def _open_ctx(p, mobile: bool):
    kwargs = dict(
        user_data_dir=config.EDGE_PROFILE_DIR,
        headless=config.HEADLESS,
        # No `channel="msedge"` — bundled Chromium avoids Edge's Windows-account
        # SSO. We supply an Edge user-agent below so Rewards still sees Edge.
    )
    if mobile:
        kwargs.update(
            user_agent=MOBILE_UA,
            viewport={"width": 390, "height": 844},
            is_mobile=True,
            has_touch=True,
            device_scale_factor=3,
        )
    else:
        kwargs.update(
            user_agent=DESKTOP_EDGE_UA,
            no_viewport=True,
            args=["--start-maximized"],
        )
    return p.chromium.launch_persistent_context(**kwargs)


def run_rewards() -> Report:
    rep = Report()
    with sync_playwright() as p:
        # ---- desktop pass ----
        ctx = _open_ctx(p, mobile=False)
        try:
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            if not _ensure_signed_in(page):
                rep.note = "Could not confirm sign-in, so I stopped."
                return rep
            rep.desktop_done = _do_searches(page, config.DESKTOP_SEARCHES, "desktop")
            rep.activities_done = _do_activities(ctx)
            rep.points = _read_points(page)
        finally:
            ctx.close()
        time.sleep(2)

        # ---- mobile pass: reopen the same profile with a phone user-agent ----
        try:
            ctx = _open_ctx(p, mobile=True)
            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                page.goto(REWARDS_URL, wait_until="domcontentloaded")
                page.wait_for_timeout(3000)
                if _on_dashboard(page):
                    rep.mobile_done = _do_searches(page, config.MOBILE_SEARCHES, "mobile")
                    rep.points = _read_points(page)
                else:
                    rep.note = (rep.note + " Mobile pass: not signed in there.").strip()
            finally:
                ctx.close()
        except Exception as e:  # noqa: BLE001
            rep.note = (rep.note + f" Mobile pass failed: {e}").strip()
    return rep


if __name__ == "__main__":
    print(run_rewards().spoken())
