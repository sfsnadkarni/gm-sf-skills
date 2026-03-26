---
name: sf-translation
description: Generate Salesforce STF translation files (Spanish/Portuguese) for a given Salesforce object by comparing org field metadata against a master translation Excel sheet.
arguments: true
---

You are helping the user generate Salesforce STF translation files. The Salesforce object name is: **$ARGUMENTS**

If no object name was provided in $ARGUMENTS, immediately ask the user: "Which Salesforce object do you want to generate translations for? (e.g. Vehicle, Case, Account)"

Set OBJECT_NAME = $ARGUMENTS (trimmed).

---

## Step 0: Install Dependencies

Run the following silently:
```bash
pip3 install -r ~/.claude/skills/sf-translation/requirements.txt -q 2>&1 | tail -3
```

If it fails, tell the user to run `pip3 install pandas openpyxl` manually and continue.

---

## Step 1: Select Salesforce Org

Run:
```bash
python3 ~/.claude/skills/sf-translation/scripts/org_connect.py
```

Parse the JSON output and display a numbered list to the user:
```
Authenticated Salesforce orgs:
  1. alias=myorg  username=user@example.com  status=Connected
  2. alias=devorg username=dev@example.com   status=Connected
  0. Connect a new org
```

Ask: "Enter the number of the org to use:"

If the user picks 0 (new org), run:
```bash
sf org login web
```
Then re-run `org_connect.py` and show the updated list. Ask the user to select their newly connected org.

Store the selected org's **username** as SELECTED_ORG.

---

## Step 2: Collect File Paths

Ask the user for the following (ask all at once in a single message):

1. **Master Excel Sheet path** — the translation reference file (Column C = English label, Column D = Spanish, Column E = Portuguese)
2. **Output directory** — where to save generated files (default: `~/Desktop/sf-translation-output`)
3. **(Optional) Existing Spanish STF path** — a previously downloaded Bilingual STF for Spanish; keys already in the TRANSLATED section will be skipped. Press Enter to skip.
4. **(Optional) Existing Portuguese STF path** — a previously downloaded Bilingual STF for Portuguese; keys already in the TRANSLATED section will be skipped. Press Enter to skip.

If the user presses Enter for the output directory, use `~/Desktop/sf-translation-output` and create it.

Store as: MASTER_PATH, OUTPUT_DIR, EXISTING_ES (empty string if not provided), EXISTING_PT (empty string if not provided).

---

## Step 3: Extract Fields from Salesforce

Run:
```bash
python3 ~/.claude/skills/sf-translation/scripts/extract_fields.py \
  --org "SELECTED_ORG" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR"
```

This will:
- Run `sf sobject describe` against the selected org
- Extract all custom fields and their picklist values
- Generate `OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx` with two tabs:
  - **Custom_Fields**: Field Label, Field API Name
  - **Picklist_Values**: Field API Name, Picklist Value, Picklist Label

Report the printed summary to the user (field count, picklist value count).

If the command fails (non-zero exit), show the error output and stop. Common issues:
- Org not authorized: re-run Step 1
- Object not found: confirm the object API name with the user

---

## Step 4: Match Against Master Sheet

Run:
```bash
python3 ~/.claude/skills/sf-translation/scripts/compare_master.py \
  --intermediate "OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx" \
  --master "MASTER_PATH" \
  --output "OUTPUT_DIR/OBJECT_NAME_matches.json"
```

This compares labels in the intermediate Excel against Column C of the Master Sheet and writes a matches JSON file. Report the printed summary (matched count, unmatched count).

---

## Step 5: Generate STF Files

Build the command arguments for existing STF files:
- If EXISTING_ES is not empty: add `--existing-es "EXISTING_ES"`
- If EXISTING_PT is not empty: add `--existing-pt "EXISTING_PT"`

Run:
```bash
python3 ~/.claude/skills/sf-translation/scripts/generate_stf.py \
  --matches "OUTPUT_DIR/OBJECT_NAME_matches.json" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR" \
  [--existing-es "EXISTING_ES"] \
  [--existing-pt "EXISTING_PT"]
```

This generates:
- `OUTPUT_DIR/OBJECT_NAME_es.stf`
- `OUTPUT_DIR/OBJECT_NAME_pt_BR.stf`

Report the printed summary (written count, skipped count per language).

---

## Step 6: Generate Miss Report

Run:
```bash
python3 ~/.claude/skills/sf-translation/scripts/miss_report.py \
  --matches "OUTPUT_DIR/OBJECT_NAME_matches.json" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR"
```

This generates `OUTPUT_DIR/OBJECT_NAME_miss_report.csv`.

---

## Final Summary

Tell the user:
```
Translation files generated for [OBJECT_NAME]:

  OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx  — Field/picklist inventory
  OUTPUT_DIR/OBJECT_NAME_es.stf             — Spanish translations
  OUTPUT_DIR/OBJECT_NAME_pt_BR.stf          — Portuguese (Brazil) translations
  OUTPUT_DIR/OBJECT_NAME_miss_report.csv    — Fields with no translation found

[Print the match/skip/miss counts from each step]
```
