# GM Salesforce Skills

Claude Code skills for generating and verifying Salesforce STF translation files.

## Installation

```bash
git clone https://github.com/sfsnadkarni/gm-sf-skills.git
cd gm-sf-skills
python3 install.py
```

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

## Prerequisites

- **Python 3** — standard on macOS/Linux
- **pandas + openpyxl** — auto-installed by `install.py`
- **Salesforce CLI** (`sf`) — used if available; falls back to stored credentials in `~/.sfdx/` automatically

## Master Excel Sheet format

| Column | Content |
|--------|---------|
| A | Object Name |
| B | Field Type (`Custom Field`, `Picklist Value`, etc.) |
| **C** | **English label / picklist value — matched against** |
| **D** | **Spanish Translation** |
| **E** | **Portuguese (Brazil) Translation** |

Row 1 is a header. Data starts at row 2.

## STF key formats

```
CustomField.[Object].[FieldAPINameWithout__c].FieldLabel    <TAB>  translation
PicklistValue.[Object].[FieldAPINameWithout__c].[value]     <TAB>  translation
```

## Phase 1 scope

- Custom field labels
- Picklist values

Future phases: LRP, buttons, related lists, custom labels.
