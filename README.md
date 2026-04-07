# GM Salesforce Skills

Claude Code skills for Salesforce translation, verification, and implementation documentation.

---

## Prerequisites

Before installing, you need two things:

### 1. Claude Account
You need a [claude.ai](https://claude.ai) account (Pro or above — Claude Code is included).

### 2. Claude Code CLI
Install the Claude Code command-line tool:

```bash
npm install -g @anthropic-ai/claude-code
```

Then authenticate with your Claude account (**not an API key**):

```bash
claude
```

When prompted, choose **"Login with Claude.ai"** and log in via the browser with your claude.ai credentials. You only need to do this once per machine.

> If you see a prompt asking for an **API key** — ignore it. Choose the **"Login with Claude.ai"** option instead.

---

## Installation

Once Claude Code is set up, clone the repo anywhere on your machine — it does not need to be inside a Salesforce project. The installer puts everything in `~/.claude/skills/` which is global to your user account.

```bash
git clone https://github.com/sfsnadkarni/gm-sf-skills.git
cd gm-sf-skills
python3 install.py
```

> **Already inside another project?** That's fine. Run these commands from anywhere — even your Desktop. The skills are installed globally and work across all projects.

## Updating

```bash
cd gm-sf-skills
git pull
python3 install.py
```

---

## Skills

### `/sf-translation [Object]`

Connects to a Salesforce org, extracts all custom fields and picklist values for the given object, matches them against a master Excel translation sheet, and generates STF files ready to upload to Translation Workbench.

```
/sf-translation Vehicle
/sf-translation Case
/sf-translation Account
```

**What it asks for:**
- Which Salesforce org to use (shows authenticated orgs to pick from)
- Path to Master Excel Sheet
- Output directory (default: `~/Desktop/sf-translation-output`)
- Optional: existing Spanish bilingual STF (to skip already-translated entries)
- Optional: existing Portuguese bilingual STF (to skip already-translated entries)

**Output files:**

| File | Description |
|------|-------------|
| `[Object]_intermediate.xlsx` | Field/picklist inventory pulled from org |
| `[Object]_es.stf` | Spanish translations — upload to Translation Workbench |
| `[Object]_pt_BR.stf` | Portuguese (Brazil) translations — upload to Translation Workbench |
| `[Object]_miss_report.csv` | Fields not found in master sheet or with empty/multi-value translations |

---

### `/sf-translation-verify [Object]`

After uploading an STF to Salesforce, download the Bilingual STF from Translation Workbench and run this skill to verify the translations are correct. Compares what is in the org against the master Excel sheet and produces a color-coded Excel report.

```
/sf-translation-verify Vehicle
/sf-translation-verify Case
/sf-translation-verify Account
```

**What it asks for:**
- Path to Master Excel Sheet
- Output directory (default: `~/Desktop/sf-translation-output`)
- Optional: Spanish Bilingual STF downloaded from org
- Optional: Portuguese Bilingual STF downloaded from org

**Output file:**

| File | Description |
|------|-------------|
| `[Object]_verification.xlsx` | Color-coded comparison: Match / Mismatch / Not in Master |

**Color coding:**

| Color | Meaning |
|-------|---------|
| Green | ✓ Translation in org matches master sheet |
| Red | ✗ Translation in org differs from master sheet |
| Yellow | ⚠ Translated in org but label not found in master sheet |
| Grey | — In master sheet but not yet translated in org |

---

### `/sf-document [Component or Description]`

Generates implementation documentation from Salesforce metadata in a local repo or GitHub. Supports two modes:

**Mode 1 — Integration Flow** (give it a component name):
Traces how a specific component works end-to-end — OmniScript → Integration Procedures → Apex → external API → callback → Salesforce records. Includes a Mermaid diagram pasteable into Lucidchart.

```
/sf-document Lock Unlock Omniscript
/sf-document Care_CreateDraftDealerCase
```

**Mode 2 — Scope of Change** (paste Jira/TA notes):
Paste a Jira story or TA notes and the skill finds every Salesforce component impacted by the change — flows, validation rules, layouts, flexipages, permission sets. Generates a plain-English document explaining what was built and why, written for someone who was not in the design meetings.

```
/sf-document
> [paste your Jira story or TA notes]
```

**What it asks for:**
- Local repo path (e.g. `~/Documents/GM - Onstar Project/OCRM_219315_salesforce`) — or GitHub repo + token
- Branch (default: `tst`)
- Output directory (default: `~/Desktop/sf-translation-output`)

**Output file:**

| File | Description |
|------|-------------|
| `[Name]_documentation.md` | Implementation doc — ready to paste into SharePoint or Confluence |

---

## Other Prerequisites

- **Python 3** — standard on macOS/Linux
- **pandas + openpyxl** — auto-installed by `install.py`
- **Salesforce CLI** (`sf`) — used by the translation skills if available; falls back to stored credentials in `~/.sfdx/` automatically

## Master Excel Sheet format (sf-translation)

| Column | Content |
|--------|---------|
| A | Object Name |
| B | Field Type (`Custom Field`, `Picklist Value`, etc.) |
| **C** | **English label / picklist value — matched against** |
| **D** | **Spanish Translation** |
| **E** | **Portuguese (Brazil) Translation** |

Row 1 is a header. Data starts at row 2.
