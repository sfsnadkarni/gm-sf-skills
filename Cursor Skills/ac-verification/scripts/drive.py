#!/usr/bin/env python3
"""Playwright CDP driver for AC verification.

Attaches over CDP to a Chrome you launched with --remote-debugging-port=9222,
so it reuses your already-logged-in Salesforce session. Each invocation
reconnects, performs one action against the live browser, prints the observed
state as JSON, and (for snapshots) saves a screenshot to disk.

Because the browser lives outside this process, state persists across calls —
the agent runs one command per step and reasons about the result between steps.

Usage:
    python3 drive.py list
    python3 drive.py snapshot [--match URLSUB] [--frame FRAMESUB] [--query REGEX] [--out PATH]
    python3 drive.py goto <url> [--match URLSUB]
    python3 drive.py click "<accessible name or text or selector>" [--match URLSUB] [--frame FRAMESUB]
    python3 drive.py type "<selector-or-label>" "<text>" [--match URLSUB] [--frame FRAMESUB]

Options:
    --match   operate on the first page whose URL contains this substring
              (default: the most recently opened page)
    --frame   operate inside the first child frame whose URL contains this
              substring (Lightning often renders launchers inside iframes)
    --query   regex filter for snapshot element names (case-insensitive)
    --out     screenshot output path (default: /tmp/ac-verification/shot.png)

Exit code is non-zero on failure so the caller can detect problems.
"""
import argparse
import json
import re
import sys
import time
from pathlib import Path

CDP_URL = "http://localhost:9222"

# Pierces shadow DOM so OneCRM/LWC components (e.g. Action Launcher) are visible.
INTERACTIVE_JS = r"""() => {
  const selstr = 'button, a[href], input, textarea, select, [role=button], [role=link], [role=menuitem], [role=option], [role=tab], [role=checkbox]';
  const out = [];
  function collect(root) {
    let els;
    try { els = root.querySelectorAll(selstr); } catch (e) { return; }
    for (const el of els) {
      const r = el.getBoundingClientRect ? el.getBoundingClientRect() : { width: 1, height: 1 };
      if (r.width === 0 && r.height === 0) continue;
      const name = ((el.getAttribute && el.getAttribute('aria-label')) || el.innerText || el.value || (el.getAttribute && el.getAttribute('title')) || (el.getAttribute && el.getAttribute('placeholder')) || '').trim().replace(/\s+/g, ' ').slice(0, 100);
      if (!name) continue;
      out.push({ tag: el.tagName.toLowerCase(), role: (el.getAttribute && el.getAttribute('role')) || '', name });
    }
    let all;
    try { all = root.querySelectorAll('*'); } catch (e) { return; }
    for (const el of all) { if (el.shadowRoot) collect(el.shadowRoot); }
  }
  collect(document);
  return out;
}"""


def _all_pages(browser):
    pages = []
    for ctx in browser.contexts:
        pages.extend(ctx.pages)
    return pages


def _pick_page(browser, match):
    pages = _all_pages(browser)
    if not pages:
        sys.exit("No open pages in the debugged Chrome. Open a tab there first.")
    if match:
        for pg in pages:
            if match in pg.url:
                return pg
        urls = "; ".join(p.url for p in pages)
        sys.exit(f"No page URL contains {match!r}. Open pages: {urls}")
    return pages[-1]


def _scope(page, frame_match):
    """Return the page or a matching child frame to act within."""
    if not frame_match:
        return page
    for fr in page.frames:
        if frame_match in (fr.url or ""):
            return fr
    frames = "; ".join(f.url for f in page.frames)
    sys.exit(f"No frame URL contains {frame_match!r}. Frames: {frames}")


def cmd_list(browser):
    out = []
    for i, pg in enumerate(_all_pages(browser)):
        try:
            out.append({"index": i, "url": pg.url, "title": pg.title()})
        except Exception:
            out.append({"index": i, "url": pg.url, "title": "?"})
    print(json.dumps(out, indent=2, ensure_ascii=False))


def cmd_goto(browser, url, match):
    pg = _pick_page(browser, match)
    pg.goto(url, wait_until="domcontentloaded")
    time.sleep(1.0)
    print(json.dumps({"goto": url, "url": pg.url, "title": pg.title()}, ensure_ascii=False))


def cmd_snapshot(browser, match, frame_match, query, out):
    pg = _pick_page(browser, match)
    try:
        pg.wait_for_load_state("domcontentloaded", timeout=15000)
    except Exception:
        pass
    time.sleep(1.0)
    scope = _scope(pg, frame_match)
    info = {"url": pg.url, "title": pg.title()}
    try:
        els = scope.evaluate(INTERACTIVE_JS)
    except Exception as e:
        els = []
        info["element_error"] = f"{type(e).__name__}: {e}"
    if query:
        rx = re.compile(query, re.I)
        els = [e for e in els if rx.search(e["name"])]
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    try:
        pg.screenshot(path=out)
        info["screenshot"] = out
    except Exception as e:
        info["screenshot_error"] = f"{type(e).__name__}: {e}"
    info["elements"] = els[:150]
    info["frames"] = [f.url for f in pg.frames if f.url and f is not pg.main_frame][:15]
    # visible toast / error text, which is what most ACs hinge on
    try:
        toast = scope.evaluate(
            "() => Array.from(document.querySelectorAll('[role=alert], .toastMessage, .slds-notify__content, .slds-theme_error, .slds-theme_success')).map(e => e.innerText.trim()).filter(Boolean).slice(0,10)"
        )
        if toast:
            info["alerts"] = toast
    except Exception:
        pass
    print(json.dumps(info, indent=2, ensure_ascii=False))


def cmd_click(browser, target, match, frame_match):
    pg = _pick_page(browser, match)
    scope = _scope(pg, frame_match)
    tried = []
    attempts = [
        ("role:button", lambda: scope.get_by_role("button", name=target)),
        ("role:link", lambda: scope.get_by_role("link", name=target)),
        ("role:menuitem", lambda: scope.get_by_role("menuitem", name=target)),
        ("label", lambda: scope.get_by_label(target)),
        ("text", lambda: scope.get_by_text(target)),
        ("selector", lambda: scope.locator(target)),
    ]
    for how, make in attempts:
        try:
            make().first.click(timeout=4000)
            time.sleep(0.8)
            print(json.dumps({"clicked": target, "via": how, "url": pg.url}, ensure_ascii=False))
            return
        except Exception as e:
            tried.append(f"{how}:{type(e).__name__}")
    sys.exit(f"Could not click {target!r}. Tried -> {', '.join(tried)}")


def _field_locator(scope, target):
    """Yield (how, locator) candidates for a text input."""
    yield "label", scope.get_by_label(target)
    yield "placeholder", scope.get_by_placeholder(target)
    yield "role:textbox", scope.get_by_role("textbox", name=target)
    yield "role:combobox", scope.get_by_role("combobox", name=target)
    yield "selector", scope.locator(target)


def cmd_type(browser, target, text, match, frame_match):
    pg = _pick_page(browser, match)
    scope = _scope(pg, frame_match)
    tried = []
    for how, loc in _field_locator(scope, target):
        try:
            loc.first.fill(text, timeout=4000)
            time.sleep(0.4)
            print(json.dumps({"typed": text, "into": target, "via": how}, ensure_ascii=False))
            return
        except Exception as e:
            tried.append(f"{how}:{type(e).__name__}")
    sys.exit(f"Could not type into {target!r}. Tried -> {', '.join(tried)}")


def cmd_pick(browser, field, text, option, match, frame_match, out):
    """Type into an autocomplete field and click a result — all in ONE process.

    Autocomplete dropdowns (e.g. the Action Launcher) close when focus is lost,
    so typing and clicking MUST happen in the same invocation. Uses
    press_sequentially to fire the keystroke handlers the dropdown listens for.
    """
    pg = _pick_page(browser, match)
    scope = _scope(pg, frame_match)
    field_loc = None
    for _how, loc in _field_locator(scope, field):
        try:
            loc.first.click(timeout=4000)
            field_loc = loc.first
            break
        except Exception:
            continue
    if field_loc is None:
        sys.exit(f"Could not focus field {field!r}")
    field_loc.fill("")
    field_loc.press_sequentially(text, delay=140)
    time.sleep(1.8)
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        try:
            pg.screenshot(path=out)
        except Exception:
            pass
    opt = scope.get_by_text(option)
    n = opt.count()
    if n == 0:
        sys.exit(f"Typed {text!r} but found no result matching {option!r}.")
    opt.first.click(timeout=5000)
    time.sleep(2.5)
    print(json.dumps({"picked": option, "after_typing": text, "matches": n, "url": pg.url}, ensure_ascii=False))


def cmd_scroll(browser, dy, times, match):
    pg = _pick_page(browser, match)
    pg.mouse.move(700, 400)
    for _ in range(times):
        pg.mouse.wheel(0, dy)
        time.sleep(0.35)
    time.sleep(0.8)
    print(json.dumps({"scrolled_dy": dy, "times": times, "url": pg.url}, ensure_ascii=False))


def cmd_find(browser, term, match, frame_match):
    """Report matches for a term using shadow-DOM-piercing Playwright locators."""
    pg = _pick_page(browser, match)
    scope = _scope(pg, frame_match)
    res = {"term": term}
    try:
        t = scope.get_by_text(term)
        res["text_count"] = t.count()
        res["text_visible"] = [t.nth(i).is_visible() for i in range(min(t.count(), 6))]
    except Exception as e:
        res["text_error"] = str(e)
    for role in ("button", "link", "option", "menuitem", "tab"):
        try:
            c = scope.get_by_role(role, name=term).count()
            if c:
                res[f"role_{role}"] = c
        except Exception:
            pass
    print(json.dumps(res, ensure_ascii=False))


def main():
    ap = argparse.ArgumentParser(description="Playwright CDP driver for AC verification")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list")

    p = sub.add_parser("goto")
    p.add_argument("url")
    p.add_argument("--match")

    p = sub.add_parser("snapshot")
    p.add_argument("--match")
    p.add_argument("--frame")
    p.add_argument("--query")
    p.add_argument("--out", default="/tmp/ac-verification/shot.png")

    p = sub.add_parser("click")
    p.add_argument("target")
    p.add_argument("--match")
    p.add_argument("--frame")

    p = sub.add_parser("type")
    p.add_argument("target")
    p.add_argument("text")
    p.add_argument("--match")
    p.add_argument("--frame")

    p = sub.add_parser("pick")
    p.add_argument("field", help="the autocomplete input (placeholder/label)")
    p.add_argument("text", help="text to type to trigger the dropdown")
    p.add_argument("option", help="visible text of the result to click")
    p.add_argument("--match")
    p.add_argument("--frame")
    p.add_argument("--out", default="/tmp/ac-verification/pick.png")

    p = sub.add_parser("scroll")
    p.add_argument("--dy", type=int, default=500)
    p.add_argument("--times", type=int, default=4)
    p.add_argument("--match")

    p = sub.add_parser("find")
    p.add_argument("term")
    p.add_argument("--match")
    p.add_argument("--frame")

    args = ap.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("playwright is required. Install with: python3 -m pip install playwright")

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(CDP_URL)
        except Exception as e:
            sys.exit(
                f"Could not connect to Chrome at {CDP_URL} ({type(e).__name__}). "
                "Launch Chrome with --remote-debugging-port=9222 and try again."
            )
        try:
            if args.cmd == "list":
                cmd_list(browser)
            elif args.cmd == "goto":
                cmd_goto(browser, args.url, args.match)
            elif args.cmd == "snapshot":
                cmd_snapshot(browser, args.match, args.frame, args.query, args.out)
            elif args.cmd == "click":
                cmd_click(browser, args.target, args.match, args.frame)
            elif args.cmd == "type":
                cmd_type(browser, args.target, args.text, args.match, args.frame)
            elif args.cmd == "pick":
                cmd_pick(browser, args.field, args.text, args.option, args.match, args.frame, args.out)
            elif args.cmd == "scroll":
                cmd_scroll(browser, args.dy, args.times, args.match)
            elif args.cmd == "find":
                cmd_find(browser, args.term, args.match, args.frame)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
