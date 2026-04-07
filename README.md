# GM Salesforce Skills

Python tools for Salesforce translation, verification, and implementation documentation.

---

## Prerequisites

- **Python 3** — standard on macOS/Linux
- **Salesforce CLI** (`sf`) — [install here](https://developer.salesforce.com/tools/salesforcecli)
- **openpyxl** — auto-installed on first run

---

## Quick Start

Clone the repo anywhere on your machine — it does not need to be inside a Salesforce project:

```bash
git clone https://github.com/sfsnadkarni/gm-sf-skills.git
cd gm-sf-skills
python3 run.py --list
```

No Claude account required. No API keys. Just Python and the Salesforce CLI.

---

## Usage

```bash
python3 run.py sf-translation Vehicle
python3 run.py sf-translation-v2 Vehicle
python3 run.py sf-translation-verify Vehicle
python3 run.py sf-org-assessment
```

The tool will prompt you for everything it needs — org, file paths, output directory.

---

## Skills

### `sf-translation <Object>`

Connects to a Salesforce org, extracts all custom fields and picklist values for the given object, matches them against a master Excel translation sheet, and generates STF files ready to upload to Translation Workbench.

```bash
python3 run.py sf-translation Vehicle
python3 run.py sf-translation Case
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

### `sf-translation-v2 <Object>`

Everything in `sf-translation` plus Lightning Record Page (LRP) support — translates tab labels and related list labels via custom label STF entries.

```bash
python3 run.py sf-translation-v2 Vehicle
```

**Additional inputs (v2):**
- Optional: local Salesforce repo path — used to find the LRP flexipage XML

**Additional output files (v2):**

| File | Description |
|------|-------------|
| `[Object]_labels_es.stf` | Spanish custom label translations |
| `[Object]_labels_pt_BR.stf` | Portuguese custom label translations |
| `[Object]_lrp_miss_report.csv` | LRP labels with no translation found |
| `[Object]_new_custom_labels.labels-meta.xml` | New custom labels to deploy (only if tabs use plain text instead of `{!$Label.X}`) |

---

### `sf-translation-verify <Object>`

After uploading an STF to Salesforce, download the Bilingual STF from Translation Workbench and run this to verify translations are correct. Compares what is in the org against the master Excel sheet and produces a color-coded Excel report.

```bash
python3 run.py sf-translation-verify Vehicle
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

### `sf-org-assessment`

Runs a full health assessment on a Salesforce org and generates an HTML report with a score and breakdown of users, flows, automation, Apex, OmniStudio components, security settings, and API limits.

```bash
python3 run.py sf-org-assessment
```

---

## Updating

```bash
cd gm-sf-skills
git pull
```

No reinstall needed — `run.py` always reads scripts from the repo directly.

---

## Master Excel Sheet format

| Column | Content |
|--------|---------|
| A | Object Name |
| B | Field Type |
| **C** | **English label — matched against** |
| **D** | **Spanish Translation** |
| **E** | **Portuguese (Brazil) Translation** |

Row 1 is a header. Data starts at row 2.

---

## Claude Code users

If you use Claude Code, run `python3 install.py` to install the skills as slash commands:

```bash
python3 install.py
# then use as:
# /sf-translation Vehicle
# /sf-translation-v2 Vehicle
```
