# GM-Translate-Object

Generate combined Salesforce STF translation files (Spanish + Portuguese) for a given Salesforce object.
Covers custom fields, picklist values, and Lightning Record Page (LRP) custom label translations in a single STF per language.

The Salesforce object name is: **$ARGUMENTS**

If no object name was provided, immediately ask:
> "Which Salesforce object do you want to generate translations for? (e.g. Vehicle, Case, Account)"

Set `OBJECT_NAME = $ARGUMENTS` (trimmed).

---

## Step 1: Install Dependencies

Run silently:
```bash
pip3 install pandas openpyxl -q 2>&1 | tail -3
```

If it fails, tell the user to run `pip3 install pandas openpyxl` manually and continue.

---

## Step 2: Collect All Inputs

Ask the user for the following **in a single message**:

1. **Master Excel Sheet path** — translation reference. The correct sheet is **Sheet1** with columns: `Object Name | Field Type | Field Name | Spanish Translation | Portuguese Translation`. Col C (index 2) = English, Col D (index 3) = Spanish, Col E (index 4) = Portuguese. Always load with `sheet_name='Sheet1'` — do not rely on the default first tab (it is often a pivot/summary).
2. **Output directory** — where to save all generated files. Default: `~/Desktop/sf-translation-output`. Press Enter to use default.
3. **(Optional) Existing Spanish STF** — a previously downloaded Bilingual STF for Spanish; already-translated keys are skipped. Press Enter to skip.
4. **(Optional) Existing Portuguese STF** — a previously downloaded Bilingual STF for Portuguese; already-translated keys are skipped. Press Enter to skip.
Store as: `MASTER_PATH`, `OUTPUT_DIR`, `EXISTING_ES`, `EXISTING_PT`.

If the user skips output directory, use `~/Desktop/sf-translation-output`.

Create the output directory if it does not exist.

Then ask separately:

> For LRP (Lightning Record Page) custom label translations, would you like to:
> 1. Connect to a Salesforce org to retrieve the flexipage
> 2. Provide the path to a local `.flexipage-meta.xml` file
> 3. Skip LRP

- If **1**: proceed to Step 3 (org selection). After the org is selected:

  **Step A — Discover available flexipages.** Query via the Tooling API (standard `sf data query` does NOT support `FlexiPage` — always use `--use-tooling-api`):
  ```bash
  sf data query -q "SELECT Id, DeveloperName FROM FlexiPage WHERE DeveloperName LIKE '%OBJECT_NAME%'" --target-org SELECTED_ORG --use-tooling-api --json
  ```
  Show all results and let the user **select one or more** flexipages to process.

  **Step B — Retrieve flexipage metadata as JSON.** Do NOT use `sf org retrieve metadata` or `sf project retrieve start` — both require a valid SFDX project directory and will fail in non-SFDX workspaces. Instead, use the **Tooling API REST endpoint directly** (Python `urllib.request`):
  ```
  GET <instanceUrl>/services/data/v<apiVersion>/tooling/query
      ?q=SELECT+Id,DeveloperName,Metadata+FROM+FlexiPage+WHERE+DeveloperName='<name>'
  Authorization: Bearer <access_token>
  ```
  **Important:** The access token stored in `~/.sfdx/<username>.json` is often stale and returns 401. Always use the **fresh access token from `sf org list --json`** output — it is in `result.nonScratchOrgs[].accessToken` (or `result.sandboxes[].accessToken`). Find the entry matching `SELECTED_ORG` username.

  The Tooling API returns flexipage metadata as a **JSON object** (not XML). Save each flexipage's `Metadata` field to `/tmp/<DeveloperName>_meta.json`. Set `FLEXIPAGE_JSON_FILES` = list of those file paths.

- If **2**: ask for the path to a local `.flexipage-meta.xml` file. Read it from disk. The local file IS XML — parse it as XML. Convert to the same JSON-like dict structure used in Step 7a, or handle both formats in Step 7a.
- If **3**: set `FLEXIPAGE_JSON_FILES` to empty and skip all LRP steps.

---

## Step 3: Select Salesforce Org

List authenticated Salesforce orgs using this logic:

**Try `sf org list --json` first.** Parse the JSON output — collect from both `nonScratchOrgs` and `scratchOrgs` arrays. For each org, extract: `alias`, `username`, `instanceUrl`, `connectedStatus`.

**Fallback if sf CLI fails or returns no orgs:** Read `~/.sfdx/` directory directly. For each `<username>.json` file (skip `alias.json` and `sfdx-config.json`), load the file and extract `username`, `instanceUrl`. Load `~/.sfdx/alias.json` to resolve aliases (`orgs` key maps alias → username). Set `connectedStatus` to `"Connected"`.

Display a numbered list:
```
Authenticated Salesforce orgs:
  1. alias=myorg  username=user@example.com  status=Connected
  2. alias=devorg username=dev@example.com   status=Connected
  0. Connect a new org
```

Ask: "Enter the number of the org to use:"

If the user picks 0, run `sf org login web`, then re-list and ask again.

Store the selected org's **username** as `SELECTED_ORG`.

---

## Step 4: Extract Fields from Salesforce

Describe the `OBJECT_NAME` object in the selected org using this logic:

**Try `sf sobject describe --sobject OBJECT_NAME --target-org SELECTED_ORG --json` first.** Parse `result.fields`.

**Fallback if sf CLI fails (e.g. node not found):** Use the Salesforce REST API directly:
- Load auth from `~/.sfdx/<SELECTED_ORG>.json` (resolve alias via `~/.sfdx/alias.json` if needed).
- Call `GET <instanceUrl>/services/data/v<instanceApiVersion>/sobjects/<OBJECT_NAME>/describe/` with `Authorization: Bearer <accessToken>`.
- If 401, POST to `<loginUrl>/services/oauth2/token` with `grant_type=refresh_token`, `client_id=<clientId>`, `refresh_token=<refreshToken>` to get a new access token. Persist it back to the auth file, then retry.

From the fields array, **only process custom fields** (API name ends with `__c`):
- For each custom field: extract `label` (→ Field Label), `name` (→ Field API Name), and derive STF field name by stripping `__c` suffix.
- For each custom field's `picklistValues`: collect only active entries (`active: true`). Extract `value` (→ Picklist Value) and `label` (→ Picklist Label).

Write an intermediate Excel file `OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx` with two tabs:
- **Custom_Fields**: headers `Field Label | Field API Name` — one row per custom field.
- **Picklist_Values**: headers `Field API Name | Picklist Value | Picklist Label` — one row per active picklist value (use STF field name in the first column, i.e. without `__c`).

Report field count and picklist value count. If the command fails, show the error and stop.

---

## Step 5: Match Fields Against Master Sheet

Load the master Excel sheet (`MASTER_PATH`, **`sheet_name='Sheet1'`**). Row 1 is the header. Column layout: index 2 = `Field Name` (English), index 3 = `Spanish Translation`, index 4 = `Portuguese Translation`. Build a lookup dict keyed by **lowercased** English label. Keep the first occurrence if duplicates exist. Skip rows where the English value is empty or `'nan'`.

A translation cell is "multi-value" if it contains **any comma** — flag these for manual review, do not write them to the STF. The master sheet uses commas to separate multiple translation alternatives in a single cell (e.g., `"Activado,Habilitado"`). Even a single comma must be treated as multi-value. Do NOT use `count(',') > 1` — use `',' in str(value)`.

Load the intermediate Excel (`OUTPUT_DIR/OBJECT_NAME_intermediate.xlsx`):
- **Custom_Fields** tab: row 1 is header; each data row = (Field Label, Field API Name). Derive STF field name by stripping `__c`.
- **Picklist_Values** tab: row 1 is header; each data row = (Field API Name without `__c`, Picklist Value, Picklist Label).

Match each field label and each picklist label (lowercased) against the master lookup dict.

Build a matches JSON structure:
```json
{
  "matched_fields":    [{ "field_label", "stf_field_name", "field_api_name", "spanish", "portuguese", "multi_value_es", "multi_value_pt" }],
  "unmatched_fields":  [{ "field_label", "stf_field_name", "field_api_name" }],
  "matched_picklists": [{ "stf_field_name", "picklist_value", "picklist_label", "spanish", "portuguese", "multi_value_es", "multi_value_pt" }],
  "unmatched_picklists": [{ "stf_field_name", "picklist_value", "picklist_label" }],
  "stats": { "fields_total", "fields_matched", "fields_unmatched", "picklists_total", "picklists_matched", "picklists_unmatched" }
}
```

Save to `OUTPUT_DIR/OBJECT_NAME_matches.json`. Report matched/unmatched counts.

---

## Step 6: Generate Field/Picklist STF Files

**Parse existing STF files** (if provided) to collect already-translated keys:
- Read the STF file line by line.
- Detect file type from the `Type:` header line.
- For a **Bilingual** file: only collect keys from the TRANSLATED section; stop collecting when the OUTDATED/UNTRANSLATED section begins.
  - **Important:** The section delimiters use many dashes, e.g. `------------------TRANSLATED-------------------` and `OUT OF DATE AND UNTRANSLATED`. Do NOT match `--- TRANSLATED ---` literally. Instead, strip all `-` characters from the line, `.strip().upper()`, and check if the result equals `"TRANSLATED"` to enter the translated section. To exit, check if `"OUTDATED"` and `"UNTRANSLATED"` are both in the uppercased stripped line.
- For any other type (Translation, Source): collect all data line keys.
- A data line has a tab character; the key is everything before the first tab.

**Build STF content** for Spanish (`es`) and Portuguese (`pt_BR`):

STF header format:
```
# Use the Source file to translate labels for the first time.
# - Change the language code in the header from the organization's default language to the translation language.
# - Replace the untranslated values in the LABEL column with translated values.

# Notes:
# Don't add columns to or remove columns from this file.
# Tabs (\t), new lines (\n) and carriage returns (\r) are represented by special characters in this file.
# Lines that begin with the # symbol are ignored during import.
# Salesforce translation files are exported in the UTF-8 encoding.

# Language: Spanish
Language code: es
Type: Source
Translation type: Metadata

# KEY	LABEL

```

(Use `pt_BR` / `Portuguese (Brazil)` for the Portuguese file.)

**STF key formats:**
- Field label: `CustomField.<OBJECT_NAME>.<stf_field_name>.FieldLabel`
- Picklist value: `PicklistValue.<OBJECT_NAME>.<stf_field_name>.<picklist_value>`

**Rules:**
- Skip if translation is empty.
- Skip if translation is multi-value (more than one comma).
- Skip if the key already exists in the existing STF (already translated).
- Write as `<key>\t<translation>\n` (tab-separated, UTF-8).

Generate:
- `OUTPUT_DIR/OBJECT_NAME_es.stf`
- `OUTPUT_DIR/OBJECT_NAME_pt_BR.stf`

Report written/skipped counts per language.

---

## Step 7: LRP — Custom Label Translations (skip entirely if FLEXIPAGE_JSON_FILES is empty)

### Step 7a: Parse the flexipage JSON

The Tooling API returns flexipage metadata as a **JSON object** (not XML). Each `/tmp/<DeveloperName>_meta.json` file contains the `Metadata` dict with a `flexiPageRegions` key.

Process all files in `FLEXIPAGE_JSON_FILES`. Tag each component with the source `flexipage` name.

**Traversal logic (JSON):**
```
for region in fp_json.get('flexiPageRegions', []):
    for item in region.get('itemInstances', []):   # may be dict or list
        comp = item.get('componentInstance', {})
        cname = comp.get('componentName', '')
        props = comp.get('componentInstanceProperties', [])  # may be dict or list
        # ... classify component
        # Recurse into: comp.get('componentInstances', []) for nested regions
```
Always normalize `itemInstances` and `componentInstanceProperties` to lists (they may arrive as a single dict when there is only one entry).

**Tabs** (`flexipage:tab`): Read the `title` property (match `name` = `"title"`, read `value`).

**Related lists** (any component name containing `dynamicRelatedList`, `relatedList`, or `relatedListContainer`): Try property names `relatedListLabel`, `title`, `label` in that order — use first non-null value found.

Classify each raw title value:
- Matches `{!$Label.<ApiName>}` → `label_type = "custom_label"`, store `label_api_name`.
- Starts with `Standard.Tab.` or `Standard.` → `label_type = "standard_tab"` (skip).
- Any other non-empty string → `label_type = "plain_text"`.
- Empty/null → `label_type = "empty"` (skip).

For `plain_text` labels, derive a Custom Label API name: strip non-alphanumeric/non-underscore/non-space chars, replace spaces with underscores, truncate to 40 chars. Store as `derived_api_name`.

**Deduplicate** by `label_api_name` (for custom_label) and `raw_title` (for plain_text) across all processed flexipages before proceeding.

### Step 7b: Query the org for custom label data

Collect all unique `label_api_name` values from `custom_label` components.

**Use the Tooling API REST endpoint directly** (same approach as Step 2 — use fresh access token from `sf org list` output, not from the auth file):
```python
def tooling_query(soql, instance_url, access_token, api_version):
    import urllib.request, urllib.parse, json
    encoded = urllib.parse.quote(soql)
    url = f"{instance_url}/services/data/v{api_version}/tooling/query?q={encoded}"
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {access_token}'})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get('records', [])
```

**Query English values:** `SELECT Name, Value FROM ExternalString WHERE Name IN (<names>)`. Build `{api_name: english_value}`.

**Query existing translations:** Two steps:
1. `SELECT Id, Name FROM ExternalString WHERE Name IN (<names>)` → map `Id → Name`.
2. `SELECT ExternalStringId, Language, Value FROM ExternalStringLocalization WHERE ExternalStringId IN (<ids>) AND Language IN ('es', 'pt_BR')` → build `{label_name: {lang: value}}`.

**Translation fallback rule:** When a custom label has an existing org translation but is not found in the master sheet — use the org translation as a fallback rather than flagging as a miss. Only flag as a miss if both master sheet AND org translation are empty.

**Load existing label keys from STF files** (if provided): same parsing logic as Step 6, but only collect keys starting with `customLabel.`.

### Step 7c: Classify and match labels

**For `custom_label` components:**
- Check if already translated: `already_es = bool(org_es) or (stf_key in existing_es_label_keys)`. Same for PT.
- If already translated for a language: do NOT write that language, do NOT flag as a miss.
- Otherwise: look up the English value from the org query. If not found in org: add to "not in org" miss list.
- If English value found: look it up (lowercased) in the master sheet.
  - If found in master: use master translation. Set `write_es`/`write_pt` flags (skip if empty or multi-value).
  - If not in master but org has a translation: use the **org translation as fallback** (`final_es = org_es`, `final_pt = org_pt`). Set write flags accordingly.
  - If not in master AND no org translation: set `write_es=False`, `write_pt=False`, add to miss list.

**For `plain_text` components:**
- Look up `raw_title` (lowercased) in master sheet.
- If found AND the translation is different from the English (not a brand name kept as-is): mark as `plain_matched`. Set `write_es`/`write_pt`/`miss_es`/`miss_pt` flags.
- If found but both ES and PT are identical to the English label: skip (brand name).
- If not found: add to plain_unmatched miss list.

### Step 7d: Append custom label translations to the combined STF files

Append to the **existing** `OBJECT_NAME_es.stf` and `OBJECT_NAME_pt_BR.stf` files (created in Step 6) — do not overwrite them:

For each language, write `customLabel.<api_name>\t<translation>\n` for:
1. `custom_label` components where `write_es`/`write_pt` is True — key = `customLabel.<label_api_name>`.
2. `plain_matched` components where `write_es`/`write_pt` is True — key = `customLabel.<derived_api_name>`.

Deduplicate keys before writing.

**If any `plain_matched` entries exist**, also generate:

For each `plain_matched` entry, build the `categories` value using this naming convention:
`OnStar:<OBJECT_NAME>:<TypeOfComponent>:<raw_title>`
Where `TypeOfComponent` = `Tabs` if `component_type` is `Tab`, or `Flexcard` if `component_type` is `RelatedList`.

- `OUTPUT_DIR/OBJECT_NAME_new_custom_labels.labels-meta.xml`:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <CustomLabels xmlns="http://soap.sforce.com/2006/04/metadata">
      <labels>
          <fullName><derived_api_name></fullName>
          <categories>OnStar:OBJECT_NAME:TypeOfComponent:raw_title</categories>
          <language>en_US</language>
          <protected>false</protected>
          <shortDescription><raw_title (XML-escaped)></shortDescription>
          <value><raw_title (XML-escaped)></value>
      </labels>
      ...
  </CustomLabels>
  ```
- `OUTPUT_DIR/OBJECT_NAME_new_custom_labels_review.xlsx` — columns: `fullName | categories | language | protected | shortDescription | value`. Populate `categories` with `OnStar:<OBJECT_NAME>:<TypeOfComponent>:<raw_title>` for each row.

If the review Excel and XML were generated, tell the user:
> **Action required before importing the STF:**
> 1. Review `OBJECT_NAME_new_custom_labels_review.xlsx` — verify the new custom label definitions look correct.
> 2. Deploy `OBJECT_NAME_new_custom_labels.labels-meta.xml` to the org:
>    `sf project deploy start --source-dir path/to/customLabels/`
> 3. Update the LRP flexipage to reference `{!$Label.ApiName}` instead of plain-text tab titles.
> 4. Then import the STF files into Translation Workbench.

Report ES/PT entries written, miss count, and new custom label count.

---

## Step 8: Generate Miss Report

Build `OUTPUT_DIR/OBJECT_NAME_miss_report.xlsx` with the following tabs:

**Field_Picklist tab** — columns: `Type | English Label | Field API Name | Reason`

From `unmatched_fields`: Type = "Custom Field", Reason = "Not found in master sheet".

From `matched_fields` with issues: Type = "Custom Field". Check each:
- If `multi_value_es`: Reason includes "Spanish: multiple values in cell (needs manual review)".
- Else if `spanish` is empty: Reason includes "Spanish: empty".
- If `multi_value_pt`: Reason includes "Portuguese: multiple values in cell (needs manual review)".
- Else if `portuguese` is empty: Reason includes "Portuguese: empty".
- Only add a row if there are issues. Join multiple issues with "; ".

From `unmatched_picklists`: Type = "Picklist Value", Reason = "Not found in master sheet".

From `matched_picklists` with issues: same logic as fields above, Type = "Picklist Value".

**LRP_Labels tab** (only if `FLEXIPAGE_JSON_FILES` was provided and non-empty) — columns: `Type | Label API Name | English Value | Language | Reason`

From `custom_label` items not in master: Language = "es + pt_BR", Reason = "Not found in master sheet".
From `custom_label` items in master with miss flags: per-language rows, Reason = "Empty in master sheet" or "Multi-value in master sheet".
From `label_not_in_org`: Language = "es + pt_BR", Reason = "Custom label does not exist in org".
From `plain_unmatched`: Label API Name = raw_title, English Value = raw_title, Language = "es + pt_BR", Reason = "Plain text label not found in master sheet".
From `plain_matched` with miss flags: per-language rows.

Report miss count per tab.

---

## Final Summary

Tell the user:

```
Translation files generated for [OBJECT_NAME]:

  Combined STF Files (import into Translation Workbench):
    OUTPUT_DIR/OBJECT_NAME_es.stf       — Spanish (fields, picklists[, custom labels])
    OUTPUT_DIR/OBJECT_NAME_pt_BR.stf    — Portuguese (fields, picklists[, custom labels])

  Miss Report:
    OUTPUT_DIR/OBJECT_NAME_miss_report.xlsx  — Field_Picklist tab[, LRP_Labels tab]

  [If LRP was processed and new custom labels were needed:]
    OUTPUT_DIR/OBJECT_NAME_new_custom_labels.labels-meta.xml  — deploy before importing STF
    OUTPUT_DIR/OBJECT_NAME_new_custom_labels_review.xlsx      — review before deploying

[Print match/skip/miss counts from each step]
```
