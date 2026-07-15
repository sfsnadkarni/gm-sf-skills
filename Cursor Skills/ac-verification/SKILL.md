---
name: ac-verification
description: Automated acceptance-criteria (UAT) verification for Salesforce stories. Interviews the developer for the org, Jira story, and the target persona's user record, pulls acceptance criteria from Jira, then drives the browser (reusing the dev's Chrome session and clicking "Login As" the persona) to verify each AC, and produces a PDF report split into Passed / Failed / Inconclusive. Runs in two phases — a short interactive setup, then autonomous execution that can be launched as a background subagent so the developer keeps coding while it runs. Use when a developer wants to verify a Jira story's acceptance criteria in an org, run automated UAT, or generate an AC verification report.
disable-model-invocation: true
---

# AC Verification

Drive a live Salesforce org as a target persona to verify a Jira story's acceptance criteria, then emit a PDF report.

## Tools this skill relies on

- **Jira MCP**: `get_issue` (pull the story + acceptance criteria).
- **Playwright CDP driver**: `scripts/drive.py` — attaches over CDP to a Chrome the dev launched with `--remote-debugging-port=9222`, reusing the dev's logged-in session. Run it via the Shell. Commands: `list`, `goto`, `snapshot` (shadow-DOM aware, lists frames, saves PNG), `click`, `type`, `pick` (type + click a result in one call, for autocompletes), `scroll`, `find` (shadow-DOM-piercing match check).
- **Chrome launcher**: `scripts/launch_chrome.sh` — starts (or detects) the dedicated debugged Chrome so the dev doesn't have to.
- **Report script**: `scripts/build_report.py` (turns a results JSON into a PDF, embedding on-disk screenshots).

Reuse the developer's already-logged-in Chrome session — do **not** log in with credentials.

### Why Playwright (not the app's Browser builtin)

The AI Expert Suite "Browser" builtin is only callable by the app's own agent, not from a Cursor session (it isn't an MCP server and is blocked in the Python sandbox). Playwright over CDP works from anywhere via the Shell and saves screenshots to disk for the report.

---

## Prerequisites — the debugged Chrome

Phase B drives a **dedicated Chrome** (separate profile, so the dev's normal browsing is untouched) launched with remote debugging on port 9222. **The skill launches it automatically in A4** via `scripts/launch_chrome.sh` — the dev doesn't run anything by hand. The dev only completes SSO login (once) and the "Login As" click (B1).

Install deps if needed: `python3 -m pip install playwright reportlab`.

To instead reuse the dev's **already-logged-in default profile**, fully quit Chrome first, then launch `launch_chrome.sh` with the default `--user-data-dir`. The dedicated profile is preferred for isolation.

---

## Background execution model

This skill runs in two phases so the developer can keep coding during the run:

- **Phase A — Setup (foreground, ~2 min):** interview the dev, pull/confirm ACs, collect nav hints, confirm the debugged Chrome is reachable, and save a **run config** JSON. Requires the dev.
- **Phase B — Execution (background, autonomous):** log in as the persona, verify every AC via `drive.py`, build the PDF. **Launch this as a background subagent** (Task tool, `run_in_background: true`) passing the run-config path, then tell the dev they can keep working — the subagent notifies when the PDF is ready.

**Dedicated Chrome (why the dev isn't interrupted):** the driver attaches to the separate debugged Chrome profile, not the dev's everyday browser. The dev keeps coding and browsing normally; only the dedicated window is off-limits during the run.

**Run config path:** `~/.cursor/ac-verification/<story_key>.run.json`.

---

## Autonomy & approvals

The point of this skill is **hands-off** testing. Once Phase A is confirmed, run Phase B end-to-end **without pausing between steps or ACs, and without asking the dev to approve each command.** Do not ask "should I run this?" for read-only navigation, snapshots, clicks, or typing — just proceed and report at the end.

- **One-time decisions in Phase A, never mid-run:** get the destructive-action policy up front (see A1) and honor it silently during Phase B.
- **Destructive/mutating actions** (anything that submits or changes data — e.g. clicking the final **NAD Reset** submit): follow the `mutations` policy from the config:
  - `execute` → perform them, capture the result as evidence.
  - `dryrun` → stop just before the final submit, capture the pre-submit screen, and mark that AC **INCONCLUSIVE** with a note ("dry-run: not submitted").
- **Reduce Cursor approval prompts:** so the dev isn't clicking *Run* for every command, recommend they allowlist / enable auto-run for `python3 …/ac-verification/scripts/drive.py` (and `build_report.py`) in Cursor's command settings. Batch multiple browser actions into a single `drive.py` invocation where practical (e.g. `pick` already does type+click in one call) to minimize the number of commands.

---

## PHASE A — Setup (foreground)

Copy this checklist and track progress:

```
- [ ] A1: Interview (env, Jira key, persona link, output path, mutations, languages)
- [ ] A2: Pull ACs from Jira, confirm/edit with dev
- [ ] A3: Collect a light nav hint per AC
- [ ] A4: Ensure the debugged Chrome is running (auto-launch)
- [ ] A5: Write run config, then launch Phase B in the background
```

### A1 — Interview

Ask the developer, in one message:

1. **Environment / org**: which sandbox or org (name or URL).
2. **Jira story or feature key** (e.g. `OCRM-1234`).
3. **Persona user-record link**: the full URL to the Salesforce **User record** of the persona to test as (this is where the "Login As" button lives).
4. **Output path**: where to save the PDF (full path or folder).
5. **Mutation policy**: may the run perform data-changing actions (submit forms, send commands like NAD reset)? `execute` or `dryrun` (stop before the final submit). This is asked **once** and applied silently for the whole run.
6. **Language(s) to verify**: which UI language(s) should the ACs be checked in — `English`, `Spanish (SSA)`, `Portuguese (BR)`, or several? **The dev must tell the skill** — do not assume. If any AC is about translation/localization (e.g. "labels are translated"), the dev should list the language(s) to test; the skill will set the persona to each language and verify. If the dev says English only, translation ACs are marked INCONCLUSIVE with a note.

### A2 — Pull and confirm acceptance criteria

Call `get_issue` with the story key. Extract the acceptance criteria (check the description and any `Acceptance Criteria` field; also read child stories if a feature key was given).

Present them as a numbered list and ask: **"Here are the acceptance criteria I pulled. Are these correct? Edit or confirm."**

- If Jira returns none, ask the dev to paste them.
- Wait for explicit confirmation before proceeding.

### A3 — Light navigation hint per AC

For each AC, ask for a **starting point only** (app, tab, or a record link) — not click-by-click. Example: *"AC2 — start from the Cases tab."* Infer the rest during execution.

### A4 — Ensure the debugged Chrome is running (auto-launch)

Don't make the dev launch Chrome by hand. The skill checks the debug port and starts Chrome itself if needed:

```bash
bash scripts/launch_chrome.sh 9222 "$HOME/.ac-verification-chrome" "https://<org>.my.salesforce.com"
```

- Prints `ALREADY_UP` (reuse it), `LAUNCHED` (started fresh, on the org login page), or `FAILED_TO_START`.
- Launching a GUI app may require running this command **outside the sandbox** (`required_permissions: ["all"]`). If that's blocked, fall back to asking the dev to run the one-liner in their Terminal.

Then confirm the tab is reachable with `python3 scripts/drive.py list`. If the profile is freshly launched (or the session expired), ask the dev to **complete SSO login** as admin. The dev leaves this Chrome window alone during the run.

### A5 — Write run config and launch Phase B

Write the run config to `~/.cursor/ac-verification/<story_key>.run.json`:

```json
{
  "story_key": "OCRM-1234",
  "story_title": "Address normalization on save",
  "environment": "UAT (acme--uat.sandbox.my.salesforce.com)",
  "persona_link": "https://acme--uat.sandbox.my.salesforce-setup.com/lightning/setup/ManageUsers/page?address=%2F005...",
  "login_button_label": "Login",
  "url_match": "onecrm",
  "mutations": "dryrun",
  "languages": ["English"],
  "output_pdf": "/Users/dev/Desktop/OCRM-1234_ac_report.pdf",
  "acceptance_criteria": [
    { "id": "AC1", "text": "...", "nav_hint": "Contacts tab" }
  ]
}
```

`languages` is the dev-specified list to verify (from A1). For each language, set the persona to it (see B2) and run the ACs; localization ACs are only PASS/FAIL when their language was actually tested.

`url_match` is the substring passed to `drive.py --match` to target the org tab. Then **launch Phase B as a background subagent** (Task tool, `run_in_background: true`) whose prompt is: "Follow the ac-verification skill Phase B using run config at `<path>`." Tell the dev: *"Setup done — verification is running in the background. Keep coding in your other windows; I'll let you know when the PDF is ready. Don't touch the dedicated Chrome window."*

---

## PHASE B — Execution (background)

Read the run config, then work through the checklist:

```
- [ ] B1: Dev logs in as the persona ("Login As")
- [ ] B2: Verify each AC (navigate -> act -> observe -> verdict)
- [ ] B3: Build the PDF, notify
```

All browser actions use `scripts/drive.py` over the Shell. Pass `--match <url_match>` (from the config) so it drives the org tab. `snapshot` pierces shadow DOM (so LWC components like the Action Launcher are visible) and lists child `frames`; if content is inside an iframe, pass `--frame <urlsub>`.

### B1 — Dev logs in as the persona (manual)

**Do not automate "Login As."** The Setup user page buries the Login button in deeply nested iframes; automating it is unreliable and wastes time. Instead:

1. Confirm the dev has opened the persona's User record in the dedicated Chrome (the `persona_link`) and clicked **Login** / **Login As** themselves.
2. Verify the session with `python3 scripts/drive.py list` — the tab title/URL should reflect the persona (and the top banner reads "Logged in as …"). The UI language also confirms the persona's locale.
3. Only proceed once impersonation is confirmed.

### B2 — Verify each AC

For each AC, run **navigate → act → observe → verdict** using the driver:

1. **Navigate** to the AC's starting point (`goto` a record URL and/or `click` through nav; `snapshot` to see what's available).
2. **Act**: perform the interaction the AC describes (`click`, `type`).
3. **Observe**: `snapshot --out /tmp/ac-verification/<story>_<AC>.png` — the JSON reports the page's interactive elements and any `alerts` (toasts / error / success banners), and saves a screenshot to disk for the report.
4. **Verdict** — infer status from the AC text and the observed evidence:

| Status | Rule |
|---|---|
| **PASS** | Concrete **positive** evidence that the AC is satisfied. |
| **FAIL** | Concrete **negative** evidence (error, missing element, wrong value). |
| **INCONCLUSIVE** | No decisive evidence either way. |

**Strict rule — no PASS without positive evidence.** Absence of an error is *not* a pass. When in doubt, mark **INCONCLUSIVE**.

Record for each AC: `status`, the `steps` you took, and a one-line `evidence` string stating exactly what you observed (quote on-screen text where possible).

#### Playbook: OneCRM Action Launcher (NAD Reset and similar)

The Action Launcher lives in the **right rail** of a Case/Vehicle record. Reliable sequence:

1. `goto` the record, then `scroll --times 4` — the right rail (and its Action Launcher) only renders when the window is wide enough and after scrolling; if the rail is missing, ask the dev to widen the dedicated Chrome window.
2. The launcher has a search box (`Search actions…`, localized e.g. `Buscar acciones…`) and a set of action buttons.
3. **Use `pick`, not separate type/click.** The results dropdown is a live autocomplete that **closes the moment focus is lost**, so a separate screenshot/snapshot call will make it vanish. `pick` types and clicks the result in one process:

```bash
python3 scripts/drive.py pick "Search actions" "NAD" "NAD Reset" --match onecrm --out /tmp/ac-verification/<story>_launch.png
```

   Type a **partial** term (e.g. `NAD`) — the dropdown filters as you type. If `pick` reports no match, the action genuinely isn't offered for this record type/persona (a real finding), not a tooling issue.
4. Clicking a result opens an **OmniStudio screen in a subtab** (URL contains `vlocityLWCOmniWrapper`). Wait ~5s, then `snapshot`/`find` to verify the launched screen's fields (e.g. NAD Reset shows Vehicle Info: VIN, Country, STID, and a submit button).

#### Localization (AC2/AC3) — driven by the dev-specified `languages`

Only test the language(s) the dev listed in A1/`languages`. For each language:

1. **Set the persona's language** (no logout needed) by navigating to personal settings and changing Language & Time Zone:
   `goto "https://<org>.lightning.force.com/lightning/settings/personal/LanguageAndTimeZone/home"`, set the language, save. (Verified working.) Reload the record afterward.
2. Re-run the relevant ACs and capture the **translated** strings as evidence (e.g. launcher `Iniciador de acciones` / `Buscar acciones…`, screen labels, headers, picklists, button).
3. A localization AC is **PASS** only if its language was actually tested and strings are translated; **FAIL** if a string is left untranslated; **INCONCLUSIVE** only if that language wasn't tested.

If the dev listed only English, mark AC2/AC3 **INCONCLUSIVE** with a note that no translation language was requested.

### B3 — Build the PDF, notify

1. Write a results JSON (schema below) to `~/.cursor/ac-verification/<story_key>.results.json`, setting each AC's `screenshot` to the PNG saved during B2 so it embeds in the PDF. (Leaving the persona session as-is is fine; the dev can "Log out as" when they return.)
2. Run (use the `output_pdf` path from the run config):

```bash
python3 scripts/build_report.py <results.json> <output_pdf>
```

If `reportlab` is missing, install it: `python3 -m pip install reportlab`.

3. Report back so the dev is notified: *"Report saved to `<output_pdf>` — X passed, Y failed, Z inconclusive."*

### Results JSON schema

```json
{
  "story_key": "OCRM-1234",
  "story_title": "Address normalization on save",
  "environment": "UAT (acme--uat.sandbox.my.salesforce.com)",
  "persona": "Service Agent — /lightning/r/User/005.../view",
  "run_timestamp": "2026-07-07 10:47 CDT",
  "acceptance_criteria": [
    {
      "id": "AC1",
      "text": "User can save a record and the address is normalized.",
      "status": "PASS",
      "nav_hint": "Contacts tab",
      "steps": ["Opened Contacts", "Edited a contact", "Clicked Save"],
      "evidence": "Green toast 'Contact saved'; Mailing Address reformatted to USPS standard.",
      "screenshot": ""
    }
  ]
}
```

`status` must be one of `PASS`, `FAIL`, `INCONCLUSIVE`. `screenshot` is optional (path to a PNG on disk); leave empty if none.

---

## Guardrails

- Reuse the existing Chrome session only (attach over CDP); never enter credentials. The dev performs "Login As" manually (B1) — never try to automate it.
- Phase B drives only the debugged Chrome via `--match`; never assume a tab. If the target page has been navigated away or logged out, stop and report instead of guessing.
- Run autonomously: don't pause between ACs or ask to approve individual read-only commands. The only pre-approved gate is the Phase A `mutations` policy.
- Data-changing actions follow the `mutations` policy silently: `execute` performs them; `dryrun` stops before the final submit and marks that AC INCONCLUSIVE.
- Prefer honesty over optimism: a false PASS is worse than an INCONCLUSIVE. If `pick` finds no matching action, that's a genuine FAIL/finding, not a tooling gap.
