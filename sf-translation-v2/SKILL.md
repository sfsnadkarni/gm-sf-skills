---
name: sf-translation-v2
description: Generate Salesforce STF translation files (Spanish/Portuguese) for a given Salesforce object. Covers custom fields, picklist values, AND Lightning Record Page (LRP) tabs and related list labels via custom label STF entries.
arguments: true
---

You are helping the user generate Salesforce STF translation files (v2). The Salesforce object name is: **$ARGUMENTS**

If no object name was provided in $ARGUMENTS, immediately ask the user: "Which Salesforce object do you want to generate translations for? (e.g. Vehicle, Case, Account)"

Set OBJECT_NAME = $ARGUMENTS (trimmed).

---

## Step 0: Install Dependencies

Run the following silently:
```bash
pip3 install -r ~/.claude/skills/sf-translation-v2/requirements.txt -q 2>&1 | tail -3
```

If it fails, tell the user to run `pip3 install pandas openpyxl` manually and continue.

---

## Step 1: Select Salesforce Org

Run:
```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/org_connect.py
```

Parse the JSON output and display a numbered list to the user:
```
Authenticated Salesforce orgs:
  1. alias=myorg  username=user@example.com  status=Connected
  2. alias=devorg username=dev@example.com   status=Connected
  0. Connect a new org
```

Ask: "Enter the number of the org to use:"

If the user picks 0, run:
```bash
sf org login web
```
Then re-run `org_connect.py`, show the updated list, and ask the user to select the newly connected org.

Store the selected org's **username** as SELECTED_ORG.

---

## Step 2: Collect File Paths

Ask the user for the following in a single message:

1. **Master Excel Sheet path** — translation reference (Col C = English, Col D = Spanish, Col E = Portuguese)
2. **Output directory** — where to save all generated files (default: `~/Desktop/sf-translation-output`)
3. **(Optional) Existing Spanish STF** — a previously downloaded Bilingual STF for Spanish; already-translated keys are skipped. Press Enter to skip.
4. **(Optional) Existing Portuguese STF** — a previously downloaded Bilingual STF for Portuguese; already-translated keys are skipped. Press Enter to skip.
5. **(Optional) Local Salesforce repo path** — needed to find the Lightning Record Page (LRP) flexipage XML for tab/related list label translations. Press Enter to skip LRP support.

Store as: MASTER_PATH, OUTPUT_DIR, EXISTING_ES, EXISTING_PT, REPO_PATH (empty if skipped).

If the user skips the output directory, use `~/Desktop/sf-translation-output` and create it.

---

## Step 3: Extract Fields from Salesforce

Run:
```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/extract_fields.py \
  --org "SELECTED_ORG" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR"
```

This generates `OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx` with two tabs:
- **Custom_Fields**: Field Label, Field API Name
- **Picklist_Values**: Field API Name, Picklist Value, Picklist Label

Report the printed summary (field count, picklist value count).

If the command fails, show the error and stop. Common issues:
- Org not authorized: re-run Step 1
- Object not found: confirm the object API name with the user

---

## Step 4: Match Fields Against Master Sheet

Run:
```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/compare_master.py \
  --intermediate "OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx" \
  --master "MASTER_PATH" \
  --output "OUTPUT_DIR/OBJECT_NAME_matches.json"
```

Report the printed summary (matched count, unmatched count).

---

## Step 5: Generate Field/Picklist STF Files

Build the command — include `--existing-es` and `--existing-pt` only if the user provided them:

```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/generate_stf.py \
  --matches "OUTPUT_DIR/OBJECT_NAME_matches.json" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR" \
  [--existing-es "EXISTING_ES"] \
  [--existing-pt "EXISTING_PT"]
```

This generates:
- `OUTPUT_DIR/OBJECT_NAME_es.stf`
- `OUTPUT_DIR/OBJECT_NAME_pt_BR.stf`

Report the printed summary.

---

## Step 6: Generate Field/Picklist Miss Report

Run:
```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/miss_report.py \
  --matches "OUTPUT_DIR/OBJECT_NAME_matches.json" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR"
```

This generates `OUTPUT_DIR/OBJECT_NAME_miss_report.csv`.

---

## Step 7: LRP — Find Flexipage (skip if REPO_PATH is empty)

If REPO_PATH is provided, search for the flexipage XML:

```bash
find "REPO_PATH" -name "*.flexipage-meta.xml" | grep -i "OBJECT_NAME"
```

Show the results and ask the user to confirm which file to use. Store as FLEXIPAGE_PATH.

If no matching flexipage is found, tell the user and ask if they want to provide the full path manually.

---

## Step 8: LRP — Extract Label Data

Run:
```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/extract_lrp.py \
  --flexipage "FLEXIPAGE_PATH" \
  --org "SELECTED_ORG" \
  --master "MASTER_PATH" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR" \
  [--existing-es "EXISTING_ES"] \
  [--existing-pt "EXISTING_PT"]
```

This queries the org for existing custom label translations and matches them against the master sheet.

Report the printed summary (tabs found, ES/PT entries to write, new custom labels to create).

---

## Step 9: LRP — Generate Custom Label STF Files

Run:
```bash
python3 ~/.claude/skills/sf-translation-v2/scripts/generate_labels_stf.py \
  --lrp-matches "OUTPUT_DIR/OBJECT_NAME_lrp_matches.json" \
  --object "OBJECT_NAME" \
  --output "OUTPUT_DIR"
```

This generates:
- `OUTPUT_DIR/OBJECT_NAME_labels_es.stf` — ES custom label translations
- `OUTPUT_DIR/OBJECT_NAME_labels_pt_BR.stf` — PT custom label translations
- `OUTPUT_DIR/OBJECT_NAME_lrp_miss_report.csv` — items with no translation found
- `OUTPUT_DIR/OBJECT_NAME_new_custom_labels.labels-meta.xml` — (only if new custom labels are needed)

If the `new_custom_labels.labels-meta.xml` file was generated, tell the user:
> **Action required before importing the label STF:**
> 1. Deploy `OBJECT_NAME_new_custom_labels.labels-meta.xml` to the org:
>    `sf project deploy start --source-dir path/to/customLabels/`
> 2. Update the LRP flexipage to reference `{!$Label.ApiName}` instead of the plain-text tab title.
> 3. Then import the STF files into Translation Workbench.

---

## Final Summary

Tell the user:

```
Translation files generated for [OBJECT_NAME]:

  Custom Fields & Picklists:
    OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx  — Field/picklist inventory
    OUTPUT_DIR/OBJECT_NAME_es.stf             — Spanish field/picklist translations
    OUTPUT_DIR/OBJECT_NAME_pt_BR.stf          — Portuguese field/picklist translations
    OUTPUT_DIR/OBJECT_NAME_miss_report.csv    — Fields with no translation found

  Lightning Record Page Labels:
    OUTPUT_DIR/OBJECT_NAME_labels_es.stf           — Spanish custom label translations
    OUTPUT_DIR/OBJECT_NAME_labels_pt_BR.stf        — Portuguese custom label translations
    OUTPUT_DIR/OBJECT_NAME_lrp_miss_report.csv     — LRP labels with no translation found
    OUTPUT_DIR/OBJECT_NAME_new_custom_labels.labels-meta.xml  — (if applicable)

[Print the match/skip/miss counts from each step]
```
