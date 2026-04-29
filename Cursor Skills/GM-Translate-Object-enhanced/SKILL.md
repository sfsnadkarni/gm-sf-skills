# GM-Translate-Object-enhanced

Generate combined Salesforce STF translation files (Spanish + Portuguese) for a given Salesforce object **AND** an upsert-ready CSV for the custom `GM_Translation__c` object.

This is an enhanced version of `GM-Translate-Object`. It performs every step of the original skill (extract custom fields, picklists, and LRP custom labels; match against the master sheet; generate STFs; produce a miss report; verify/generate new custom labels) and then adds a final step that **builds a CSV to upsert every translation that ended up in the STF files into the `GM_Translation__c` custom object** so the translations are also available to runtime components that read from `GM_Translation__c`.

The Salesforce object name is: **$ARGUMENTS**

If no object name was provided, immediately ask:
> "Which Salesforce object do you want to generate translations for? (e.g. Vehicle, Case, Account)"

Set `OBJECT_NAME = $ARGUMENTS` (trimmed).

---

## Setup: Copy skill files from GitHub

This skill requires **two files** in the same folder. Before running, make sure both exist at `.cursor/skills/GM-Translate-Object-enhanced/`:

```
SKILL.md           ← this file
generate_stf.py    ← the STF generator script (reused from GM-Translate-Object)
```

If `generate_stf.py` is missing, download it now:

```bash
curl -o "/path/to/.cursor/skills/GM-Translate-Object-enhanced/generate_stf.py" \
  "https://raw.githubusercontent.com/sfsnadkarni/gm-sf-skills/main/Cursor%20Skills/GM-Translate-Object/generate_stf.py"
```

Or copy it manually from: https://github.com/sfsnadkarni/gm-sf-skills/tree/main/Cursor%20Skills/GM-Translate-Object

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
3. **Bilingual STF for Spanish (Colombia)** — download from Translation Workbench and provide path. This is the **source of truth** for which keys are valid and which are already translated. Strongly recommended; warn if skipped.
4. **Bilingual STF for Portuguese (Brazil)** — same as above for pt_BR. Strongly recommended; warn if skipped.
5. **(Optional) Bilingual STF for Spanish (es)** — only needed if generating a separate `es` STF. Press Enter to skip.
Store as: `MASTER_PATH`, `OUTPUT_DIR`, `EXISTING_ES_CO`, `EXISTING_PT`, `EXISTING_ES`.

> **Why bilingual files are required:** The bilingual STF exported from Translation Workbench is the definitive list of keys the org accepts for this object. Keys not in the bilingual cause Salesforce import errors ("key's translation type must match"). The bilingual also tells us which keys are already translated so we don't overwrite them.

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

  **Step B — Retrieve flexipage metadata as JSON.** Do NOT use `sf org retrieve metadata` or `sf project retrieve start` — both require a valid SFDX project directory and will fail in non-SFDX workspaces. Instead, use **curl** for each flexipage (more reliable than Python urllib for large payloads):
  ```bash
  curl -s -o /tmp/<DeveloperName>_meta.json \
    -H "Authorization: Bearer <access_token>" \
    "<instanceUrl>/services/data/v<apiVersion>/tooling/query?q=$(python3 -c "import urllib.parse; print(urllib.parse.quote(\"SELECT Id,DeveloperName,Metadata FROM FlexiPage WHERE DeveloperName='<name>'\"))")"
  ```
  Then extract the `Metadata` field from the curl response using Python and save it to `/tmp/<DeveloperName>_meta.json`.

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

## Step 6: Generate STF Files

**Do NOT write Python code for this step.** Use the committed script `generate_stf.py` from this repository. This ensures consistent, deterministic output every time.

### 6a: Download the script

The script lives alongside this SKILL.md in the repo. It should already be present in the same folder as this file. If not, download it:

```bash
curl -o /tmp/generate_stf.py \
  "https://raw.githubusercontent.com/sfsnadkarni/gm-sf-skills/main/Cursor%20Skills/GM-Translate-Object/generate_stf.py"
```

### 6b: Run the script

```bash
python3 /path/to/generate_stf.py \
    --object OBJECT_NAME \
    --master "MASTER_PATH" \
    --bilingual-es-co "EXISTING_ES_CO" \
    --bilingual-pt-br "EXISTING_PT" \
    --output-dir "OUTPUT_DIR"
```

- Omit `--bilingual-es-co` or `--bilingual-pt-br` if not provided by the user.
- Add `--bilingual-es "EXISTING_ES"` if the user provided a Spanish (es) bilingual.
- Add `--lrp-labels "Label1,Label2"` if LRP custom label API names were identified in Step 7.

### 6c: What the script does (do not reimplement)

- Parses the bilingual UNTRANSLATED section as the source of truth for keys
- Strictly filters to `OBJECT_NAME` keys only (+ GVS picklists) — **`PicklistValue.Standard.*` keys are NOT covered by this filter; they are handled in Step 6d**
- Accepted key types: `CustomField`, `PicklistValue`, `LayoutSection`, `RecordType`, `QuickAction`, `CustomLabel`, `ButtonOrLink`
- Skips keys already in the TRANSLATED section (already done in org)
- Looks up each source label in the master sheet
- Skips: not in master, empty, multi-value (comma), or >40 characters
- **Does NOT skip when translation == source label** (brand names, acronyms are valid)
- Writes 4-column bilingual format: `KEY\tSOURCE\tTRANSLATION\t-`
- Generates `<object>_over40_report.txt` for entries that were too long

Report the written/skipped counts shown by the script output.

### 6d: Append Standard Picklist Values (PicklistValue.Standard.*)

`generate_stf.py` strictly filters to keys whose object segment matches `OBJECT_NAME`. Standard picklist fields (e.g. `Case.Status`, `Case.Priority`, `Case.Type`) are exported by Translation Workbench under the key prefix `PicklistValue.Standard.<fieldNameCamelCase>.*` — they are **never** matched by the object-name filter and will be silently skipped unless handled here.

> **Important — the bilingual STF is a full-org export.** It contains `PicklistValue.Standard.*` keys for every standard object in the org (e.g. `leadStatus`, `accountType`, `opportunityStage`). You must **not** blindly include all of them when the input object is `Case` — that would pollute the Case STF files with translations for unrelated objects. An explicit allowlist of key prefixes derived from the input object's own standard picklist fields is required.

#### 6d-i: Derive the allowlist of Standard.* key prefixes for OBJECT_NAME

Translation Workbench uses the camelCase convention `<objectNameLower><FieldNamePascal>` as the field segment in the key. For example:
- `Case` + `Status`   → `PicklistValue.Standard.caseStatus.*`
- `Case` + `Priority` → `PicklistValue.Standard.casePriority.*`
- `Lead` + `Status`   → `PicklistValue.Standard.leadStatus.*`  *(excluded when object is Case)*

Use the `sf sobject describe` output already retrieved in Step 4 to find every **standard** (non-`__c`) picklist field on `OBJECT_NAME`:

```python
def derive_standard_picklist_prefixes(describe_fields, object_name):
    """Return a set of PicklistValue.Standard.<prefix> strings for every
    standard picklist field on the object, using Salesforce's camelCase convention."""
    obj_lower = object_name[0].lower() + object_name[1:]   # e.g. "Case" → "case"
    prefixes = set()
    for f in describe_fields:
        if f['name'].endswith('__c'):
            continue   # custom field — handled by generate_stf.py
        if f.get('type') not in ('picklist', 'multipicklist'):
            continue
        if not f.get('picklistValues'):
            continue
        field_name = f['name']                                          # e.g. "Status"
        # Salesforce STF key convention: objectLower + FieldPascal
        stf_segment = obj_lower + field_name[0].upper() + field_name[1:]  # e.g. "caseStatus"
        prefixes.add(f"PicklistValue.Standard.{stf_segment}.")
    return prefixes
```

#### 6d-ii: Filter and append

```python
def get_standard_picklist_untranslated(bilingual_path, allowed_prefixes):
    """Return (key, source_label) pairs from the UNTRANSLATED section
    whose key starts with one of the allowed_prefixes."""
    entries = []
    section = None
    with open(bilingual_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if '-' * 5 in line and 'TRANSLATED' in line:
                section = 'untranslated' if ('OUTDATED' in line or 'UNTRANSLATED' in line) else 'translated'
                continue
            if not line or line.startswith('#') or line.startswith('Language') or line.startswith('Type'):
                continue
            parts = line.split('\t')
            key = parts[0].strip()
            if section == 'untranslated' and any(key.startswith(p) for p in allowed_prefixes):
                source = parts[1].strip() if len(parts) > 1 else ''
                entries.append((key, source))
    return entries

def match_and_append_standard_picklists(bilingual_es, bilingual_pt, allowed_prefixes,
                                         master_lookup, out_dir, object_name):
    es_entries = get_standard_picklist_untranslated(bilingual_es, allowed_prefixes) if bilingual_es else []
    pt_entries = get_standard_picklist_untranslated(bilingual_pt, allowed_prefixes) if bilingual_pt else []

    def load_existing_keys(stf_path):
        keys = set()
        try:
            with open(stf_path, 'r', encoding='utf-8') as f:
                for line in f:
                    parts = line.rstrip().split('\t')
                    if parts and parts[0] and '.' in parts[0]:
                        keys.add(parts[0].strip())
        except FileNotFoundError:
            pass
        return keys

    es_stf = str(Path(out_dir) / f"{object_name}_es_CO.stf")
    pt_stf = str(Path(out_dir) / f"{object_name}_pt_BR.stf")
    existing_es = load_existing_keys(es_stf)
    existing_pt = load_existing_keys(pt_stf)

    def process(entries, lang_key, stf_path, existing_keys):
        written, misses = [], []
        with open(stf_path, 'a', encoding='utf-8') as f:
            for key, source in entries:
                if key in existing_keys:
                    continue  # already written by generate_stf.py
                master = master_lookup.get(source.lower())
                if not master:
                    misses.append((key, source, 'Not found in master sheet'))
                    continue
                trans = master.get(lang_key, '')
                if not trans:
                    misses.append((key, source, 'Empty in master sheet'))
                    continue
                if ',' in trans:
                    misses.append((key, source, 'Multi-value in master sheet'))
                    continue
                if len(trans) > 40:
                    misses.append((key, source, f'Translation exceeds 40 characters ({len(trans)})'))
                    continue
                f.write(f"{key}\t{source}\t{trans}\t-\n")
                written.append((key, source, trans))
        return written, misses

    es_written, es_miss = process(es_entries, 'spanish',    es_stf, existing_es)
    pt_written, pt_miss = process(pt_entries, 'portuguese', pt_stf, existing_pt)

    print(f"[Standard picklists] Allowed prefixes: {sorted(allowed_prefixes)}")
    print(f"[Standard picklists] es_CO: {len(es_written)} written, {len(es_miss)} missed")
    print(f"[Standard picklists] pt_BR: {len(pt_written)} written, {len(pt_miss)} missed")
    return es_written, pt_written, es_miss, pt_miss
```

Call these immediately after `generate_stf.py` completes, passing `allowed_prefixes` derived from the Step 4 describe fields:

```python
allowed_prefixes = derive_standard_picklist_prefixes(describe_fields, OBJECT_NAME)
match_and_append_standard_picklists(
    EXISTING_ES_CO, EXISTING_PT, allowed_prefixes,
    master_lookup, OUTPUT_DIR, OBJECT_NAME
)
```

**Add misses from this step to the `Field_Picklist` tab of the miss report** (Type = `"Standard Picklist Value"`). Include key, source label, and reason for each miss.

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

**CRITICAL — Check plain_text labels against org first.** Before classifying any plain_text component as needing a new custom label, query the org to check if a label already exists for it. Many plain-text tab/related list titles are already custom labels in the org but the flexipage is not yet referencing them with `{!$Label...}` syntax.

For every `plain_text` component, derive candidate API names and query `ExternalString`:
- Derive: `underscore_name` (spaces → underscores, strip special chars), `no_space_name` (remove spaces), and `raw_title` as-is.
- Query: `SELECT Name, Value FROM ExternalString WHERE Name IN (<all_candidates>)`
- If a match is found → treat this component as **already_existing** (not a new label). Store the actual org `Name` as the label API name to use. Do NOT add it to the new-labels list.
- If no match → it is truly a new label candidate.

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
2. `SELECT ExternalStringId, Language, Value FROM ExternalStringLocalization WHERE ExternalStringId IN (<ids>) AND Language IN ('es', 'es_CO', 'pt_BR')` → build `{label_name: {lang: value}}`.

Do this for **all** labels — both `custom_label` components and `already_existing` plain_text components.

**Translation fallback rule:** When a label has an existing org translation but is not found in the master sheet — use the org translation as a fallback rather than flagging as a miss. Only flag as a miss if both master sheet AND org translation are empty.

**Load existing label keys from STF files** (if provided): same parsing logic as Step 6, but only collect keys starting with `CustomLabel.`.

### Step 7c: Classify and match labels

**For `custom_label` components AND `already_existing` plain_text components (same logic):**
- Check if already translated: `already_es = bool(org_es) or (stf_key in existing_es_label_keys)`. Same for ES_CO, PT.
- If already translated for a language: do NOT write that language, do NOT flag as a miss.
- Otherwise: look up the English value from the org query. If not found in org: add to "not in org" miss list.
- If English value found: look it up (lowercased) in the master sheet.
  - If found in master: use master translation. Set `write_es`/`write_pt` flags (skip if empty or multi-value).
  - If not in master but org has a translation: use the **org translation as fallback** (`final_es = org_es`, `final_pt = org_pt`). Set write flags accordingly.
  - If not in master AND no org translation: set `write_es=False`, `write_pt=False`, add to miss list.

**For truly new `plain_text` components** (no matching org label found in Step 7b):
- Look up `raw_title` (lowercased) in master sheet.
- If found AND the translation is different from the English (not a brand name kept as-is): mark as `plain_new_matched`. Set `write_es`/`write_pt`/`miss_es`/`miss_pt` flags.
- If found but both ES and PT are identical to the English label: skip (brand name).
- If not found: add to plain_unmatched miss list.

### Step 7d: Append custom label translations to the combined STF files

Regenerate (overwrite) the STF files completely rather than appending, so that LRP entries are cleanly included alongside the field/picklist entries. The `es_CO` file gets the same custom label translations as the `es` file (same Spanish source column).

For each language, write `CustomLabel.<api_name>\t<translation>\n` for:
1. `custom_label` components where `write_es`/`write_pt` is True — key = `CustomLabel.<label_api_name>`.
2. `already_existing` plain_text components where `write_es`/`write_pt` is True — key = `CustomLabel.<actual_org_label_name>`.
3. `plain_new_matched` components where `write_es`/`write_pt` is True — key = `CustomLabel.<derived_api_name>`.

Deduplicate keys before writing.

### Step 7e: Generate the custom labels review Excel (always generate this file)

Always generate `OUTPUT_DIR/OBJECT_NAME_new_custom_labels_review.xlsx` with **two tabs**:

**Tab 1 — New_Labels_Required**

Columns: `Full Name (API) | Short Description | English Value | Component Type | LRP Page(s) | Action Required | Notes`

Only include entries for `plain_new_matched` components — i.e. plain-text labels with **no matching org label found** in Step 7b. One row per new label (deduplicated; list all LRP pages in the LRP Page(s) column, comma-separated).

If there are no truly new labels, include a single informational row stating: *"All LRP components already have existing Custom Labels in this org. No new labels need to be created. See Tab 2 for the label syntax to use in each LRP page."*

**Tab 2 — Label_Reference** *(developer copy-paste reference)*

Columns: `Current Plain Text | Label API Name | Label Syntax (copy this) | Component Type | LRP Page | Currently Plain Text? | ES Translation | ES_CO Translation | PT_BR Translation`

Include **every** LRP component (one row per component × LRP page combination) across all three categories:
- `custom_label` components — already using `{!$Label...}`, mark "Currently Plain Text?" = `No — already uses {!$Label...} syntax` (green)
- `already_existing` plain_text components — mark "Currently Plain Text?" = `YES — needs updating to label syntax` (orange)
- `plain_new_matched` / `plain_unmatched` components — mark as `YES — needs updating to label syntax` (orange)

The **Label Syntax** column should contain the copy-paste ready `{!$Label.<ApiName>}` string, styled in a distinct font/color for easy identification.

Populate ES, ES_CO, PT_BR translation columns from `trans_map` (existing org translations). Show `"(not yet translated)"` if empty.

**If any `plain_new_matched` entries exist**, also generate:

For each `plain_new_matched` entry, build the `categories` value using this naming convention:
`OnStar:<OBJECT_NAME>:<TypeOfComponent>:<raw_title>`
Where `TypeOfComponent` = `Tabs` if `component_type` is `Tab`, or `RelatedList` if `component_type` is `RelatedList`.

- `OUTPUT_DIR/OBJECT_NAME_new_custom_labels.labels-meta.xml`:
  ```xml
  <?xml version="1.0" encoding="UTF-8"?>
  <CustomLabels xmlns="http://soap.sforce.com/2006/04/metadata">
      <labels>
          <fullName><derived_api_name></fullName>
          <categories>OnStar:OBJECT_NAME:Tabs_or_RelatedList:raw_title</categories>
          <language>en_US</language>
          <protected>false</protected>
          <shortDescription><raw_title (XML-escaped)></shortDescription>
          <value><raw_title (XML-escaped)></value>
      </labels>
      ...
  </CustomLabels>
  ```

Tell the user:
> **Action required before importing the STF:**
> 1. Review `OBJECT_NAME_new_custom_labels_review.xlsx` — Tab 1 shows any new labels to create; Tab 2 shows the label syntax for every LRP component so developers can update the flexipages.
> 2. If Tab 1 has new labels: deploy `OBJECT_NAME_new_custom_labels.labels-meta.xml` to the org:
>    `sf project deploy start --source-dir path/to/customLabels/`
> 3. Update each LRP flexipage to reference `{!$Label.ApiName}` instead of plain-text titles (use Tab 2 as the reference).
> 4. Then import the STF files into Translation Workbench.

Report ES/PT entries written, miss count, and new custom label count.

---

## Step 8: Generate Miss Report

Build `OUTPUT_DIR/OBJECT_NAME_miss_report.xlsx` with the following tabs:

**Field_Picklist tab** — columns: `Type | English Label | Field API Name | Reason`

From `unmatched_fields`: Type = "Custom Field", Reason = "Not found in master sheet".

From `matched_fields` with issues: Type = "Custom Field". Check each:
- If `multi_value_es`: Reason includes "Spanish: multiple values in cell (needs manual review)".
- Else if `spanish` exceeds 40 characters: Reason includes "Spanish: translation exceeds 40 characters".
- Else if `spanish` is empty: Reason includes "Spanish: empty".
- If `multi_value_pt`: Reason includes "Portuguese: multiple values in cell (needs manual review)".
- Else if `portuguese` exceeds 40 characters: Reason includes "Portuguese: translation exceeds 40 characters".
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

## Step 9: Generate GM_Translation__c Import CSV (Upsert-Ready)

In addition to the STF files (used for Translation Workbench import), generate a CSV
file that can be used to **upsert records into the `GM_Translation__c` custom object**
for every translation that ended up in the STF files (custom fields, picklist values,
and LRP custom labels — including the LRP labels that point at already-existing org
labels).

The CSV uses `TranslationsKey__c` as the external ID, so:

- **New rows** are inserted when no existing record matches the key (e.g. a new
  Custom Label was created, or a new picklist value is being introduced).
- **Existing rows** are updated when the key already exists — **only the language
  columns that are present in the CSV are updated**; other language translations
  already on the record are preserved (e.g. when a record already has `Es_MX_Text__c`
  populated and we are now adding `Pt_BR_Text__c`).

### 9a — GM_Translation__c schema (target-org-independent)

Fields used on the CSV (confirmed from DevStg reference records):

| Column                | Field API                 | Notes                                                                       |
| --------------------- | ------------------------- | --------------------------------------------------------------------------- |
| `TranslationsKey__c`  | External Id, Unique (255) | Upsert key. Same string that appears in the STF files (see 9b)              |
| `ComponentType__c`    | Picklist (restricted)     | Derived from the prefix of `TranslationsKey__c` (CustomField / PicklistValue / CustomLabel / LayoutSection / RecordType / QuickAction / ButtonOrLink) |
| `Description__c`      | Text(255)                 | Human-readable location of the label, derived from the key                  |
| `En_US_Text__c`       | Long Text(1000)           | English source (column 2 of the STF row)                                    |
| `Es_MX_Text__c`       | Long Text(1000)           | Spanish (Mexico)   — same Spanish translation column as the master sheet    |
| `Es_CO_Text__c`       | Long Text(1000)           | Spanish (Colombia) — same Spanish translation column as the master sheet    |
| `Pt_BR_Text__c`       | Long Text(1000)           | Portuguese (Brazil)                                                         |

> **Note** — the master Excel for this skill only has a single Spanish column. Both
> `Es_MX_Text__c` and `Es_CO_Text__c` are populated from that single Spanish value
> (mirroring how Step 6/7 generate identical content for `<object>_es_CO.stf`).

### 9b — TranslationsKey__c key formats (re-using the STF keys)

The STF files written by Step 6/7 already use the exact keys Salesforce expects.
We re-use them verbatim. The `ComponentType__c` value is taken from the prefix:

| Key prefix in the STF                  | Example                                             | ComponentType__c |
| -------------------------------------- | --------------------------------------------------- | ---------------- |
| `CustomField.<Object>.<Field>.<Attr>`  | `CustomField.Vehicle__c.VIN__c.FieldLabel`          | `CustomField`    |
| `PicklistValue.<Object>.<Field>.<Val>` | `PicklistValue.Vehicle__c.Status__c.Active`         | `PicklistValue`  |
| `CustomLabel.<ApiName>`                | `CustomLabel.OnStar_Vehicle_History`                | `CustomLabel`    |
| `LayoutSection.<Object>...`            | `LayoutSection.Vehicle__c.Information`              | `LayoutSection`  |
| `RecordType.<Object>.<RT>`             | `RecordType.Vehicle__c.Standard`                    | `RecordType`    |
| `QuickAction.<Object>.<Action>`        | `QuickAction.Vehicle__c.Update_VIN`                 | `QuickAction`    |
| `ButtonOrLink.<Object>.<Btn>`          | `ButtonOrLink.Vehicle__c.View_History`              | `ButtonOrLink`   |

`Description__c` is derived from the key as a human-readable path (Object > Field > Value
or `Custom Label: <ApiName>` for custom labels).

### 9c — Generate the upsert CSV

Write the following Python script to `OUTPUT_DIR/scripts/generate_gm_translation_csv.py`
and run it. (Create `OUTPUT_DIR/scripts/` if it does not exist.)

```python
#!/usr/bin/env python3
"""
Generate a CSV for upserting GM_Translation__c records from the STF files produced
by GM-Translate-Object-enhanced (Step 6/7).

Inputs:
  --object         OBJECT_NAME   (used to locate the STF files and as a default token)
  --output-dir     OUTPUT_DIR    (where the STF files live; CSV/preview written here)
  --target-org     SELECTED_ORG  (queried so we can show insert vs. update per row)
  --stf-es         OPTIONAL path to <object>_es.stf      (Spanish — single Es column)
  --stf-es-co      OPTIONAL path to <object>_es_CO.stf   (Spanish Colombia)
  --stf-pt-br      OPTIONAL path to <object>_pt_BR.stf   (Portuguese Brazil)

If any --stf-* argument is omitted, the script auto-discovers the file in
OUTPUT_DIR using the <object>_<lang>.stf naming convention.

Output:
  <object>_GM_Translations_Import.csv    — upsert-ready on TranslationsKey__c
  <object>_GM_Translations_Preview.xlsx  — coloured preview (green=insert, yellow=update, grey=unchanged)
"""
import argparse, csv, json, re, subprocess, sys
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


# ── STF parsing ──────────────────────────────────────────────────────────────
def parse_stf(path):
    """
    Parse a 4-column bilingual STF row: KEY\tSOURCE\tTRANSLATION\t-
    Skip header/comment lines and empty lines.
    Return list of (key, source, translation).
    """
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n').rstrip('\r')
            if not line or line.startswith('#') or line.startswith('-'):
                continue
            if line.startswith('Language:') or line.startswith('Type:'):
                continue
            parts = line.split('\t')
            if len(parts) < 3:
                continue
            key   = parts[0].strip()
            src   = parts[1].strip()
            trans = parts[2].strip()
            if not key or '.' not in key:
                continue
            if not trans:
                continue
            rows.append((key, src, trans))
    return rows


# ── Key → ComponentType + Description helpers ────────────────────────────────
def component_type_from_key(key):
    prefix = key.split('.', 1)[0] if '.' in key else key
    allowed = {'CustomField', 'PicklistValue', 'CustomLabel',
               'LayoutSection', 'RecordType', 'QuickAction', 'ButtonOrLink'}
    return prefix if prefix in allowed else 'Other'


def description_from_key(key):
    """Build a human-readable Description__c from the STF key."""
    if key.startswith('CustomLabel.'):
        return f"Custom Label: {key[len('CustomLabel.'):]}"
    if key.startswith('PicklistValue.'):
        body = key[len('PicklistValue.'):]
        bits = body.split('.')
        if len(bits) >= 3:
            return f"{bits[0]} > {bits[1]} > {'.'.join(bits[2:])}"
        return body.replace('.', ' > ')
    if key.startswith('CustomField.'):
        body = key[len('CustomField.'):]
        bits = body.split('.')
        if len(bits) >= 3:
            return f"{bits[0]} > {bits[1]} ({bits[2]})"
        if len(bits) == 2:
            return f"{bits[0]} > {bits[1]}"
        return body
    if key.startswith('RecordType.'):
        return f"Record Type: {key[len('RecordType.'):].replace('.', ' > ')}"
    if key.startswith('QuickAction.'):
        return f"Quick Action: {key[len('QuickAction.'):].replace('.', ' > ')}"
    if key.startswith('ButtonOrLink.'):
        return f"Button/Link: {key[len('ButtonOrLink.'):].replace('.', ' > ')}"
    if key.startswith('LayoutSection.'):
        return f"Layout Section: {key[len('LayoutSection.'):].replace('.', ' > ')}"
    return key.replace('.', ' > ')


# ── Existing-row lookup ──────────────────────────────────────────────────────
def query_existing_gm_translations(target_org, keys):
    """
    Query GM_Translation__c for the given keys and return:
      { key_lower: {En_US_Text__c, Es_MX_Text__c, Es_CO_Text__c, Pt_BR_Text__c, Description__c, ComponentType__c} }
    Paged in batches of 200 keys to stay under SOQL limits.
    """
    existing = {}
    keys = list(keys)
    for i in range(0, len(keys), 200):
        batch = keys[i:i+200]
        escaped = [k.replace("'", "\\'") for k in batch]
        in_list = ",".join(f"'{k}'" for k in escaped)
        soql = (f"SELECT TranslationsKey__c, ComponentType__c, Description__c, "
                f"En_US_Text__c, Es_MX_Text__c, Es_CO_Text__c, Pt_BR_Text__c "
                f"FROM GM_Translation__c WHERE TranslationsKey__c IN ({in_list})")
        try:
            cmd = ["sf", "data", "query", "--query", soql,
                   "--target-org", target_org, "--json"]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            raw = res.stdout or ""
            brace = raw.find('{')
            data  = json.loads(raw[brace:] if brace >= 0 else raw or "{}")
            for rec in (data.get("result", {}) or {}).get("records", []):
                k = (rec.get("TranslationsKey__c") or "").strip()
                if k:
                    existing[k.lower()] = {
                        "ComponentType__c": rec.get("ComponentType__c", "") or "",
                        "Description__c":   rec.get("Description__c", "") or "",
                        "En_US_Text__c":    rec.get("En_US_Text__c", "") or "",
                        "Es_MX_Text__c":    rec.get("Es_MX_Text__c", "") or "",
                        "Es_CO_Text__c":    rec.get("Es_CO_Text__c", "") or "",
                        "Pt_BR_Text__c":    rec.get("Pt_BR_Text__c", "") or "",
                    }
        except Exception as e:
            print(f"  WARN: query batch {i}-{i+len(batch)} failed: {e}", file=sys.stderr)
    print(f"  Existing GM_Translation__c rows matched: {len(existing)} / {len(keys)}")
    return existing


# ── Main ─────────────────────────────────────────────────────────────────────
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--object',     required=True)
    p.add_argument('--output-dir', required=True)
    p.add_argument('--target-org', required=True)
    p.add_argument('--stf-es',     default=None)
    p.add_argument('--stf-es-co',  default=None)
    p.add_argument('--stf-pt-br',  default=None)
    args = p.parse_args()

    out_dir = Path(args.output_dir)
    obj     = args.object
    stf_es    = args.stf_es    or str(out_dir / f"{obj}_es.stf")
    stf_es_co = args.stf_es_co or str(out_dir / f"{obj}_es_CO.stf")
    stf_pt_br = args.stf_pt_br or str(out_dir / f"{obj}_pt_BR.stf")

    es_rows    = parse_stf(stf_es)     if Path(stf_es).exists()    else []
    es_co_rows = parse_stf(stf_es_co)  if Path(stf_es_co).exists() else []
    pt_rows    = parse_stf(stf_pt_br)  if Path(stf_pt_br).exists() else []

    print(f"Loaded STF rows: es={len(es_rows)} es_CO={len(es_co_rows)} pt_BR={len(pt_rows)}")

    # Combine into per-key rows. Source = first non-empty source seen.
    combined = {}
    def merge(rows, col):
        for key, src, trans in rows:
            r = combined.setdefault(key, {
                'TranslationsKey__c': key,
                'ComponentType__c':   component_type_from_key(key),
                'Description__c':     description_from_key(key)[:255],
                'En_US_Text__c':      src,
                'Es_MX_Text__c':      '',
                'Es_CO_Text__c':      '',
                'Pt_BR_Text__c':      '',
            })
            if not r['En_US_Text__c'] and src:
                r['En_US_Text__c'] = src
            r[col] = trans

    # Spanish (single column from master) → populates BOTH Es_MX and Es_CO.
    # Files <object>_es.stf and <object>_es_CO.stf carry the same Spanish strings.
    merge(es_rows,    'Es_MX_Text__c')
    merge(es_co_rows, 'Es_CO_Text__c')
    # If we only have one of (es / es_CO), mirror to the other so both columns are filled.
    for r in combined.values():
        if r['Es_MX_Text__c'] and not r['Es_CO_Text__c']:
            r['Es_CO_Text__c'] = r['Es_MX_Text__c']
        elif r['Es_CO_Text__c'] and not r['Es_MX_Text__c']:
            r['Es_MX_Text__c'] = r['Es_CO_Text__c']
    merge(pt_rows, 'Pt_BR_Text__c')

    rows = list(combined.values())
    if not rows:
        print("No translatable rows found in any STF file. Nothing to write.")
        sys.exit(0)

    # Cross-reference with existing org records
    print(f"Preloading existing GM_Translation__c records for {len(rows)} keys...")
    existing = query_existing_gm_translations(args.target_org,
                                              [r['TranslationsKey__c'] for r in rows])

    insert_count = update_count = unchanged_count = 0
    for r in rows:
        ex = existing.get(r['TranslationsKey__c'].lower())
        if ex is None:
            r['_status'] = 'INSERT (new record)'
            insert_count += 1
            continue
        changes = []
        for lang, new_val in (('En_US_Text__c', r['En_US_Text__c']),
                              ('Es_MX_Text__c', r['Es_MX_Text__c']),
                              ('Es_CO_Text__c', r['Es_CO_Text__c']),
                              ('Pt_BR_Text__c', r['Pt_BR_Text__c'])):
            if not new_val:
                continue
            old_val = ex.get(lang, '') or ''
            if old_val.strip() != new_val.strip():
                changes.append(f"{lang}: '{old_val}' → '{new_val}'")
        if changes:
            r['_status'] = 'UPDATE (' + '; '.join(changes)[:200] + ')'
            update_count += 1
        else:
            r['_status'] = 'UNCHANGED (all fields already match)'
            unchanged_count += 1

    # ── Write CSV (upsert-ready) ─────────────────────────────────────────────
    csv_path = out_dir / f"{obj}_GM_Translations_Import.csv"
    CSV_COLS = ['TranslationsKey__c', 'ComponentType__c', 'Description__c',
                'En_US_Text__c', 'Es_MX_Text__c', 'Es_CO_Text__c', 'Pt_BR_Text__c']
    with csv_path.open('w', newline='', encoding='utf-8-sig') as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, '') for k in CSV_COLS})

    # ── Write preview Excel ──────────────────────────────────────────────────
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "GM_Translation Preview"
    headers = CSV_COLS + ['Status']

    HDR_FILL  = PatternFill("solid", fgColor="1F3864")
    HDR_FONT  = Font(bold=True, color="FFFFFF")
    NEW_FILL  = PatternFill("solid", fgColor="C6EFCE")   # green
    UPD_FILL  = PatternFill("solid", fgColor="FFEB9C")   # yellow
    NOOP_FILL = PatternFill("solid", fgColor="D9D9D9")   # grey

    for j, h in enumerate(headers, 1):
        c = ws.cell(1, j, h); c.fill = HDR_FILL; c.font = HDR_FONT

    for i, r in enumerate(rows, 2):
        status = r.get('_status', '')
        if status.startswith('INSERT'):    fill = NEW_FILL
        elif status.startswith('UPDATE'):  fill = UPD_FILL
        else:                              fill = NOOP_FILL
        row = [r.get(k, '') for k in CSV_COLS] + [status]
        for j, v in enumerate(row, 1):
            ws.cell(i, j, v).fill = fill

    for j, w in enumerate([60, 16, 50, 45, 45, 45, 45, 70], 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"

    preview_path = out_dir / f"{obj}_GM_Translations_Preview.xlsx"
    wb.save(preview_path)

    print(f"\nGM_Translation__c Upsert Preview:")
    print(f"  INSERT (new)      : {insert_count}")
    print(f"  UPDATE (changed)  : {update_count}")
    print(f"  UNCHANGED         : {unchanged_count}")
    print(f"  CSV     : {csv_path}")
    print(f"  Preview : {preview_path}")
    print()
    print("To upsert into the org, run:")
    print(f'  sf data upsert \\\n'
          f'    --sobject    GM_Translation__c \\\n'
          f'    --file       "{csv_path}" \\\n'
          f'    --external-id TranslationsKey__c \\\n'
          f'    --target-org "{args.target_org}"')
```

### 9d — Run the script

```bash
mkdir -p "OUTPUT_DIR/scripts"
# (write the script above to OUTPUT_DIR/scripts/generate_gm_translation_csv.py)

python3 "OUTPUT_DIR/scripts/generate_gm_translation_csv.py" \
  --object     "OBJECT_NAME" \
  --output-dir "OUTPUT_DIR" \
  --target-org "SELECTED_ORG"
```

The script auto-discovers `OUTPUT_DIR/OBJECT_NAME_es.stf`,
`OUTPUT_DIR/OBJECT_NAME_es_CO.stf`, and `OUTPUT_DIR/OBJECT_NAME_pt_BR.stf`.
Pass explicit `--stf-es` / `--stf-es-co` / `--stf-pt-br` if any STF lives elsewhere.

### 9e — Report to the user and offer to execute the upsert

Show the user the printed summary (INSERT / UPDATE / UNCHANGED counts) and tell them:

> **Review the preview first:** `OUTPUT_DIR/OBJECT_NAME_GM_Translations_Preview.xlsx`
> - **Green rows** — new records to be inserted (no key match in the target org)
> - **Yellow rows** — existing records to be updated (shows the old → new diff per language)
> - **Grey rows**   — already in sync; included in the CSV but nothing will change
>
> The yellow-row Status column only lists language values that will actually change —
> existing language values not present in the CSV are preserved because we are
> upserting on `TranslationsKey__c` and only sending the columns we care about.

Then ask:
> "Would you like me to run the upsert now against **SELECTED_ORG**? (yes / no)"

If yes, run:
```bash
sf data upsert \
  --sobject    GM_Translation__c \
  --file       "OUTPUT_DIR/OBJECT_NAME_GM_Translations_Import.csv" \
  --external-id TranslationsKey__c \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```

Report the `totalSuccesses`, `totalFailures`, and the path to the failed-rows CSV if any
records failed. **Do not run the upsert without explicit user confirmation.**

---

## Final Summary

Tell the user:

```
Translation files generated for [OBJECT_NAME]:

  Combined STF Files (import into Translation Workbench):
    OUTPUT_DIR/OBJECT_NAME_es.stf       — Spanish (fields, picklists[, custom labels])
    OUTPUT_DIR/OBJECT_NAME_es_CO.stf    — Spanish Colombia (fields, picklists[, custom labels])
    OUTPUT_DIR/OBJECT_NAME_pt_BR.stf    — Portuguese (fields, picklists[, custom labels])

  Miss Report:
    OUTPUT_DIR/OBJECT_NAME_miss_report.xlsx  — Field_Picklist tab[, LRP_Labels tab]

  [If LRP was processed:]
    OUTPUT_DIR/OBJECT_NAME_new_custom_labels_review.xlsx      — Tab 1: new labels to create (if any); Tab 2: label syntax reference for all LRP components
    [If truly new labels are needed:]
    OUTPUT_DIR/OBJECT_NAME_new_custom_labels.labels-meta.xml  — deploy before importing STF

  GM_Translation__c Import:
    OUTPUT_DIR/OBJECT_NAME_GM_Translations_Import.csv    — Upsert on TranslationsKey__c (N rows: N insert, N update, N unchanged)
    OUTPUT_DIR/OBJECT_NAME_GM_Translations_Preview.xlsx  — Colour-coded preview (green=insert, yellow=update, grey=unchanged)

[Print match/skip/miss counts from each step, plus GM_Translation__c insert/update/unchanged counts]

To import translations into Salesforce:
  1. [If new custom labels XML was generated] Deploy custom labels first:
     sf project deploy start --source-dir path/to/customLabels/
  2. Log in to Setup → Translation Workbench → Import
  3. Import all three .stf files (es, es_CO, pt_BR)
  4. Upsert GM_Translation__c records (after reviewing the preview Excel):
     sf data upsert --sobject GM_Translation__c \
       --file OUTPUT_DIR/OBJECT_NAME_GM_Translations_Import.csv \
       --external-id TranslationsKey__c \
       --target-org SELECTED_ORG
```
