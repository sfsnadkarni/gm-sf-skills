---
name: sf-deploy-verification
description: Verify a Salesforce deployment by cross-referencing Jira signed-off stories against Copado promotions. Use when preparing for a production deployment, validating a release package, or checking if all Jira stories are in Copado and ready to promote.
---

# SF Deploy Verification

Cross-reference Jira signed-off features and child stories/defects against Copado promotion packages to identify missing, extra, or unready stories before a production deployment.

## When to Use
- Before every production deployment
- Validating a Copado release package
- Checking if all signed-off Jira stories are in Copado
- Identifying stories in Copado that should not be in the release

---

## Step 1: Collect Inputs

Ask the user for the following in one single message:

1. **Jira Fix Version** — exact text as it appears in Jira e.g. "4/21/26 OCRM Prod Deployment"
2. **Copado Promotion Name(s)** — comma separated e.g. "P82787, P82788, P83111"
3. **Output Excel file path** — where to save the report e.g. `~/Desktop/deploy-verification.xlsx`

> **Note:** Release Name is NOT required as a separate input — it defaults to the fix version value and is only used as a label in the report header.

Store as: FIX_VERSION, PROMOTION_NAMES (parse into a list), OUTPUT_PATH

---

## Step 2: Select Salesforce Org for Copado

Call Salesforce MCP tool `list_all_orgs` (directory: workspace root).

Parse the response and display a numbered list to the user. Ask:
> "Which org contains your Copado data? Enter the number:"

Store the selected org username as COPADO_ORG.
Tell the user: "Connected to COPADO_ORG — ready to query Copado."

---

## Step 3: Get Signed-Off Features from Jira

> **⚠️ Jira MCP Note:** The `user-jira` MCP uses the deprecated v2 API and returns "Not Found" or "Gone" (410) errors. Always use the **Direct API Fallback** below instead.

### Direct API — credentials
Read from `~/.cursor/mcp.json` → `jira-cli` server entry:
- `JIRA_BASE_URL` (e.g. `https://gm-sdv.atlassian.net`)
- `JIRA_USER` (email)
- `JIRA_API_TOKEN`

Use Python + `urllib` (stdlib, no pip needed). Always use the **v3** endpoint:
`POST {JIRA_BASE_URL}/rest/api/3/search/jql`

**Critical v3 API rules:**
- Do NOT include `startAt` in the payload — causes HTTP 400
- Paginate using `nextPageToken` from the response
- Max `maxResults` per page is 100

### Fix version discovery (run first)
Before querying features, verify the exact fix version name:
```
project = SDPOCC AND fixVersion = "FIX_VERSION" ORDER BY issuetype ASC
maxResults: 5
```
If zero results, call the versions endpoint to find the correct name:
`GET {JIRA_BASE_URL}/rest/api/3/project/SDPOCC/versions`
Pick the closest match and store as RESOLVED_FIX_VERSION.

### Fetch signed-off features
```
project = SDPOCC
AND issuetype in (Feature, "ART Feature")
AND status = "Ready to Release"
AND fixVersion = "RESOLVED_FIX_VERSION"
ORDER BY key ASC
```
fields: `key, summary, status, assignee`

> **Note:** In the SDPOCC project the feature issue type is `ART Feature` (not `Feature`). Always include both.

Store results as FEATURE_LIST. If no features found → stop and tell the user to verify the fix version name and status.

Tell the user:
```
✅ Found X signed-off features for RESOLVED_FIX_VERSION:
SDPOCC-XXXX: Feature Name
...
```

---

## Step 4: Get All Child Stories, Bugs & Defects from Jira

> **⚠️ Batching required:** Run in **batches of 10 feature keys** to avoid HTTP 400 errors. Paginate each batch using `nextPageToken`. Max 100 per page.

**Include `customfield_10938`** (SSE Tags) in fields — this is required for NoCop detection.

For each batch of 10 feature keys:
```
project = SDPOCC
AND issuetype in (Story, Bug, Defect)
AND parent in (KEY_1, KEY_2, ..., KEY_10)
ORDER BY key ASC
```
fields: `key, summary, status, issuetype, assignee, labels, parent, priority, customfield_10938`

> **Note:** The bug issue type in SDPOCC is `Defect` (not `Bug`). Always include `Story, Bug, Defect` in the issuetype clause.

After all batches complete, deduplicate by issue key (keep first occurrence).

### NoCop Detection
Check BOTH fields — a story is NoCop if EITHER condition is true:
1. `labels` field contains `"NoCop"` (exact match)
2. `customfield_10938` (SSE Tags array) contains `"nocop"` — **case-insensitive** match

Split results:
- **JIRA_NOCOP_LIST** — items where NoCop is detected → auto-matched (see Step 6)
- **JIRA_LIST** — all remaining items (no NoCop) → verified against Copado

Tell the user:
```
✅ Found X total child items across X features:
📋 X stories/defects for Copado verification (JIRA_LIST)
🏷️ X NoCop stories (auto-matched, not required in Copado)

By type: Stories: X | Defects: X
```

---

## Step 5: Get Copado Promotion Stories

Query ALL promotions in a single SOQL call using `IN`:
```sql
SELECT
  copado__User_Story__r.Name,
  copado__User_Story__r.copado__User_Story_Title__c,
  copado__User_Story__r.copadoccmint__External_Id__c,
  copado__User_Story__r.copado__Promote_Change__c,
  copado__User_Story__r.copado__Developer__r.Name,
  copado__Promotion__r.Name
FROM copado__Promoted_User_Story__c
WHERE copado__Promotion__r.Name IN ('P82787', 'P82788', 'P83111')
```

> **Important:** Always include `copado__Promotion__r.Name` in the SELECT so each story is correctly tagged with its promotion. If queried without it, run each promotion separately.

If a promotion returns no results → warn the user to verify the name.

Combine ALL results. Deduplicate by `copadoccmint__External_Id__c` (keep first occurrence).

Tell the user:
```
✅ Found X total stories across X promotion(s):
  Promotion P82787: X stories
  Promotion P82788: X stories
  (duplicates removed: X)
```

---

## Step 6: Cross-Reference

### Cross-Reference A — Extra in Copado (Not in Jira)
For each story in COPADO_LIST:
- Extract `copadoccmint__External_Id__c` (the Jira key)
- If NOT found in JIRA_LIST → add to **EXTRA_LIST**

### Cross-Reference B — Missing from Copado
For each story in JIRA_LIST (non-NoCop only):
- If NOT found in COPADO_LIST external IDs → add to **MISSING_LIST**
- NoCop stories are NEVER added to MISSING_LIST

### Cross-Reference C — Not Ready to Promote
For each story in COPADO_LIST:
- If `copado__Promote_Change__c` is false or null → add to **NOT_READY_LIST**

### Cross-Reference D — Matched (Regular)
For each story in JIRA_LIST found in COPADO_LIST → add to **MATCHED_LIST** with `note = ""`

### Cross-Reference E — Matched (NoCop auto-match)
For each story in JIRA_NOCOP_LIST → add to **NOCOP_MATCHED_LIST** with `note = "NoCop"`

> **⚠️ CRITICAL:** NoCop stories MUST appear in **TWO** places:
> 1. **Matched tab** — with Note = "NoCop" and green highlight (they are considered matched/accounted for)
> 2. **NoCop Excluded tab** — for reference/visibility
>
> Do NOT put NoCop stories only in the NoCop Excluded tab. They MUST also be in Matched.

### Cross-Reference F — Excluded From Copado (SF Team stories)
After building the initial MISSING_LIST (non-NoCop, non-QE, non-Cancelled):

1. Identify all stories where Team = "Salesforce Team; needs attention" (assignee contains `(C)`)
2. Query Copado for those stories in batches:
   ```sql
   SELECT Id, Name, Exclude_from_Copado__c, copado__Environment__r.Name,
          copado__Promote_Change__c, copadoccmint__External_Id__c
   FROM copado__User_Story__c
   WHERE copadoccmint__External_Id__c IN ('KEY1', 'KEY2', ...)
   ```
3. Build **COPADO_SF_LOOKUP** map: `external_id → list of {name, environment}` (one story may appear in multiple environments — comma-join them)
4. If `Exclude_from_Copado__c = true` → move story to **EXCLUDE_MATCHED_LIST** (remove from MISSING_LIST), `note = "ExcludedFromCopado"`
5. Stories NOT found in Copado at all → remain in MISSING_LIST with blank Copado US Name and Environment

Combined: **ALL_MATCHED = MATCHED_LIST + NOCOP_MATCHED_LIST + EXCLUDE_MATCHED_LIST**

---

## Step 7: Generate Excel Report

Write the Python script to `/tmp/gen_deploy_report.py`, then execute with `required_permissions: ["all"]`:
```bash
python3 /tmp/gen_deploy_report.py
```
This is required to write files outside the workspace (e.g. `~/Desktop/`). Use `openpyxl` (available on macOS system Python — no pip needed).

**Styling:**
- Font: Calibri 11pt data, 12pt bold headers
- Header row height: 30px, freeze top row, auto-filter on every tab
- Column widths: auto-fit (min 15, max 50)

**Tab colors:**
| Tab | Color | Text |
|-----|-------|------|
| Summary | #1976D2 | White |
| Jira List | #1565C0 | White |
| Copado List | #1565C0 | White |
| Matched | #2E7D32 | White |
| Not in Release | #C62828 | White |
| Not in Package | #E65100 | White |
| NoCop Excluded | #616161 | White |

**Row highlights:**
| Condition | Color |
|-----------|-------|
| Not Ready to Promote | #FFEBEE (light red) |
| Extra/Not-in-Release rows | #FFF3E0 (light orange) |
| Version mismatch rows (Not in Release) | #FFCCCC (red) |
| NoCop matched rows | #E8F5E9 (light green) |
| ExcludedFromCopado matched rows | #E3F2FD (light blue) |
| Salesforce Team rows (Not in Package) | #FFF9C4 (light yellow) |
| Alternating rows | #F5F5F5 / white |

---

### TAB 1: Summary

Header: `FIX_VERSION — Deploy Verification Report`
Sub-header: Generated date | Copado Org | Fix Version
Promotions queried: all promotion names joined by comma

Summary table:
| Check | Count | Status |
|-------|-------|--------|
| Jira Signed-Off Features | X | |
| Jira Stories/Defects for Verification | X | |
| Jira NoCop Stories (auto-matched) | X | ℹ️ Intentionally excluded from Copado |
| Copado Package Stories | X | |
| ✅ Matched (in Copado) | X | 🟢 Good |
| ✅ Matched (NoCop — not required in Copado) | X | 🟢 Good |
| ✅ Matched (Excluded from Copado flag) | X | 🟢 Good |
| 🔴 Extra in Copado (Not in Release) | X | 🔴 Action Required OR 🟢 Clean |
| ⚠️ Missing from Copado | X | 🔴 Action Required OR 🟢 Clean |
|   — of which Test Only Feature | X | ℹ️ Sub-count of above |
| ⚠️ Not Ready to Promote | X | 🔴 Action Required OR 🟢 Clean |

Deployment Readiness banner:
- All zeros → 🟢 READY TO DEPLOY (#E8F5E9)
- Any > 0 but all < 5 → 🟡 REVIEW REQUIRED (#FFF9C4)
- Any >= 5 → 🔴 NOT READY (#FFEBEE)

---

### TAB 2: Jira List

Columns: `Issue Key | Summary | Type | Status | Parent Feature | Parent Summary | Assignee | Priority | Labels`

Populate from JIRA_LIST (non-NoCop only).
Sort by: Parent Feature ASC, then Issue Key ASC.
Footer: `Total Stories/Defects = X`

---

### TAB 3: Copado List

Columns: `User Story # | Title | External ID (Jira Key) | Developer | Ready to Promote | Promotion Name`

Populate from COPADO_LIST.
Highlight entire row RED (#FFEBEE) where Ready to Promote = false.
Footer: `Total = X | Not Ready = X`

---

### TAB 4: Matched

Columns: `Jira Key | Jira Summary | Jira Status | User Story # | Copado Title | Ready to Promote | Developer | Promotion | Note`

Populate from ALL_MATCHED (regular + NoCop + ExcludedFromCopado).
- NoCop rows → Note = "NoCop", Copado columns = "N/A (NoCop)", highlight GREEN (#E8F5E9)
- ExcludedFromCopado rows → Note = "ExcludedFromCopado", highlight LIGHT BLUE (#E3F2FD)
- Not Ready to Promote rows → highlight ORANGE (#FFF3E0)
- Regular rows → alternating gray/white

Footer: `Total Matched = X  (Regular: X  |  NoCop: X  |  ExcludedFromCopado: X)`

---

### TAB 5: Not in Release

> **⚠️ CRITICAL — DO NOT SKIP:** This tab requires **two additional Jira queries** to populate `Story Fix Version` and `Parent Fix Version`. These columns are mandatory — do not omit them or substitute with other columns (e.g. "Parent Status" or "Reason"). Run both queries before generating the Excel script.

Columns (exactly in this order): `User Story # | Copado Title | External ID (Jira Key) | Developer | Promotion Name | Parent Feature | Story Fix Version | Parent Fix Version | Version Mismatch? | Note`

Populate from EXTRA_LIST. Note = "In Copado but NOT in signed-off Jira features for this release"

**Required Jira queries BEFORE writing the Excel script:**

**Query 1 — Story Fix Version** (fetch on all extra Jira keys in one batch):
```
issue in (SDPOCC-XXXX, SDPOCC-YYYY, ...) fields: key, fixVersions, parent
```
- Save `story_fix_versions` map: `key → comma-joined fixVersion names` (or `"None set"` if empty)
- Save `story_to_parent` map: `key → parent.key`

**Query 2 — Parent Fix Version** (fetch on all unique parent keys from Query 1):
```
issue in (PARENT_KEY_1, PARENT_KEY_2, ...) fields: key, fixVersions
```
- Save `parent_fix_versions` map: `parent_key → comma-joined fixVersion names` (or `"None set"` if empty)

**Version Mismatch column:**
- Look up `story_fix_ver` from `story_fix_versions[jira_key]`
- Look up `parent_fix_ver` from `parent_fix_versions[story_to_parent[jira_key]]`
- If `story_fix_ver.strip() != parent_fix_ver.strip()` → `"YES ⚠️"`, highlight entire row RED (#FFCCCC)
- If same → `"No"`, alternating gray/white

> **Why both?** The story's own fix version may have been updated (e.g., moved to 4/21) while the parent ART Feature is still on an older release (e.g., 3/17). Showing both columns immediately flags mismatches.

If empty → single centered row: "✅ Package is clean — no extra stories found"
Footer: `Total Extra = X`

---

### TAB 6: Not in Package

Columns: `Jira Key | Summary | Type | Status | Fix Version | Parent Feature | Parent Summary | Assignee | Priority | Team | Copado US Name | Environment`

Populate from MISSING_LIST (after ExcludedFromCopado stories have been split out in Step 6F).

**Pre-filter MISSING_LIST before rendering (silently exclude):**
1. Stories where `summary` starts with `"QE - Manual Testing"` — these are QE task tickets that will never be in a Copado package
2. Stories where `status.name` is `"Cancelled"` or `"Canceled"` (both spellings)

**Fix Version column:** Fetch `fixVersions` on all missing items in batches of 50:
```
issue in (batch_of_50_keys) fields: key, fixVersions
```
Show as comma-separated version names, or `"None set"` if empty.

**Team column logic (check in EXACTLY this order — do not reorder):**

> **⚠️ CRITICAL:** The exact Team label values are `"Test Only Feature"`, `"Salesforce Team; needs attention"`, and `"Autobots team"`. Do NOT use "Contractor", "SF Team", or any other label.

1. **FIRST** — If `summary` contains the text `"Test Only"` (case-sensitive) → Team = `"Test Only Feature"` (alternating row color, no yellow)
2. **SECOND** — If assignee `displayName` contains `" (C)"` (i.e. contractor marker) → Team = `"Salesforce Team; needs attention"` + highlight row YELLOW (#FFF9C4)
3. **OTHERWISE** → Team = `"Autobots team"`

Example:
- Summary = "SF - Test Only - Case Transfers" + assignee has `(C)` → Team = **"Test Only Feature"** (rule 1 wins)
- Summary = "SF - Translation Spanish" + assignee has `(C)` → Team = **"Salesforce Team; needs attention"** (rule 2)
- Summary = "SF - Some Story" + assignee has no `(C)` → Team = **"Autobots team"** (rule 3)

**Copado US Name column:** From COPADO_SF_LOOKUP — the `US-XXXXXXX` Copado record name(s) for SF Team stories. Comma-join if multiple. Blank if story not found in Copado or not a SF Team story.

**Environment column:** From COPADO_SF_LOOKUP — the `copado__Environment__r.Name` value(s). Comma-join if multiple. Blank if not found.

If empty → single centered row: "✅ All Jira stories are included in the Copado package"
Footer: `Total Missing = X  |  Salesforce Team: X  |  Autobots: X  |  Test Only Feature: X`

---

### TAB 7: NoCop Excluded

Columns: `Jira Key | Summary | Type | Status | Parent Feature | Assignee | Labels`

Populate from JIRA_NOCOP_LIST.
Top note: "These stories are intentionally excluded from Copado (NoCop label). They appear in the Matched tab with a NoCop note."

If empty → "No NoCop stories found for this release"
Footer: `Total Excluded = X`

---

## Step 8: Confirm Output

```
✅ Deploy Verification Complete!

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Release:    FIX_VERSION
Promotions: PROMOTION_NAMES
Report:     OUTPUT_PATH
Org:        COPADO_ORG
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Results:
✅ Matched (in Copado):           X stories
✅ Matched (NoCop):               X stories
🔴 Extra in Copado:               X stories
⚠️  Missing from Copado:          X stories
⚠️  Not Ready to Promote:         X stories

Deployment Readiness: 🟢 READY / 🟡 REVIEW REQUIRED / 🔴 NOT READY

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Action Items:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔴 Extra Stories (X):
→ Open "Not in Release" tab
→ Remove these from Copado promotions before deploying

⚠️ Missing Stories (X):
→ Open "Not in Package" tab
→ Salesforce Team items need SF team action; Autobots items need dev team action

⚠️ Not Ready to Promote (X):
→ Open "Copado List" tab — look for red rows
→ Check the Ready to Promote checkbox in Copado

Open the Excel file to review all details.
```

---

## 🚧 Future Enhancements (Not Yet Built)

### Prod Bug & Regression Bug Verification

Add two optional inputs to Step 1:
- **Prod Bug Fix Version** — Jira fix version for querying production bugs
- **Regression Bug Fix Version** — Jira fix version for querying regression bugs

**Query:** For each, fetch Defects where:
```
project = SDPOCC
AND issuetype = Defect
AND fixVersion = "BUG_FIX_VERSION"
AND status = Completed
AND "GM Defect State Reason" = "Ready to Deploy"
```

**Cross-reference logic:**
| Condition | Destination |
|-----------|-------------|
| Status = Completed + Ready to Deploy + **NoCop tag** | → **Matched** tab (note = "NoCop") |
| Status = Completed + Ready to Deploy + **found in Copado** | → **Matched** tab |
| Status = Completed + Ready to Deploy + **NOT in Copado** | → New tab: **Bugs Not in Package** |

**New tab: Bugs Not in Package**
- Separate from the existing "Not in Package" (ART Feature children)
- Columns: `Jira Key | Summary | Type | Fix Version | Assignee | Team | Copado US Name | Environment`
- Same Team routing logic as "Not in Package" tab
