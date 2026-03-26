---
name: sf-translation-verify
description: Verifies Salesforce translations by comparing what is currently in the org (via bilingual STF) against the master translation Excel sheet. Outputs a verification Excel showing matches, mismatches, and missing translations.
arguments: true
---

You are verifying Salesforce translations for the object: **$ARGUMENTS**

If no object name was provided, ask: "Which Salesforce object do you want to verify translations for? (e.g. Vehicle, Case, Account)"

Set OBJECT_NAME = $ARGUMENTS (trimmed).

---

## Step 0: Install Dependencies

```bash
pip3 install -r ~/.claude/skills/sf-translation-verify/requirements.txt -q 2>&1 | tail -2
```

---

## Step 1: Collect File Paths

Ask the user for the following all at once:

1. **Master Excel Sheet path** — the translation reference file (Column C = English label, Column D = Spanish, Column E = Portuguese)
2. **Output directory** — where to save the verification Excel (default: `~/Desktop/sf-translation-output`)
3. **(Optional) Spanish Bilingual STF path** — downloaded from org after import (e.g. `Bilingual_es_YYYY-MM-DD.stf`). Press Enter to skip.
4. **(Optional) Portuguese Bilingual STF path** — downloaded from org after import (e.g. `Bilingual_pt_BR_YYYY-MM-DD.stf`). Press Enter to skip.

At least one bilingual STF must be provided. If neither is provided, tell the user to download a Bilingual STF from Salesforce Translation Workbench first.

If the user presses Enter for output directory, use `~/Desktop/sf-translation-output`.

---

## Step 2: Run Verification

Build the command with whichever bilingual files were provided:

```bash
python3 ~/.claude/skills/sf-translation-verify/scripts/verify_translations.py \
  --object "OBJECT_NAME" \
  --master "MASTER_PATH" \
  --output "OUTPUT_DIR" \
  [--bilingual-es "BILINGUAL_ES_PATH"] \
  [--bilingual-pt "BILINGUAL_PT_PATH"]
```

Only include `--bilingual-es` and `--bilingual-pt` flags if those paths were provided.

---

## Step 3: Report Results

Show the user the printed summary, then tell them:

```
Verification Excel written to:
  OUTPUT_DIR/OBJECT_NAME_verification.xlsx

Open it and filter the "Match" column:
  ✓  Match       — translation in org matches master sheet
  ✗  Mismatch    — translation in org differs from master sheet
  ⚠  Not in Master — translated in org but not found in master sheet
  —  Missing     — in master sheet but not yet translated in org
```
