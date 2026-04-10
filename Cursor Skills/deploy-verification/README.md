# Deploy Verification Skill

Cursor AI skill for cross-referencing Jira signed-off stories against Copado promotion packages before a production deployment.

---

## What It Does

Given a Jira fix version and one or more Copado promotion names, this skill:

1. Fetches all signed-off **ART Features** from Jira for the release
2. Fetches all **child Stories, Bugs, and Defects** under those features
3. Queries **Copado promotion packages** via SOQL
4. Cross-references the two lists and generates a **7-tab Excel report** on your Desktop

### Report Tabs

| Tab | Description |
|-----|-------------|
| **Summary** | Overall deployment readiness score + action items |
| **Jira List** | All Jira stories/defects under signed-off features |
| **Copado List** | All stories in the promotion package |
| **Matched** | Stories correctly in both Jira and Copado (incl. NoCop + ExcludedFromCopado) |
| **Not in Release** | Stories in Copado but NOT under a signed-off feature — with fix version mismatch detection |
| **Not in Package** | Jira stories missing from Copado — with Team routing and Copado environment info |
| **NoCop Excluded** | Stories intentionally excluded from Copado via NoCop SSE tag |

---

## Prerequisites

### 1. Cursor IDE
This skill runs inside [Cursor](https://www.cursor.so). It uses the AI agent to orchestrate Python scripts and external API calls — no manual coding required.

### 2. Jira MCP (jira-cli)
The skill reads Jira credentials from `~/.cursor/mcp.json` under the `jira-cli` server entry:

```json
{
  "mcpServers": {
    "jira-cli": {
      "env": {
        "JIRA_BASE_URL": "https://your-domain.atlassian.net",
        "JIRA_USER": "your-email@company.com",
        "JIRA_API_TOKEN": "your-atlassian-api-token"
      }
    }
  }
}
```

Generate a Jira API token at: https://id.atlassian.com/manage-profile/security/api-tokens

> The skill calls the Jira v3 REST API directly via Python `urllib` (no pip install needed). The MCP entry is used only as a credentials store.

### 3. Salesforce MCP (Salesforce DX)
The skill uses the `user-Salesforce DX` MCP server to run SOQL queries against Copado. You need:

- **Salesforce CLI** (`sf`) installed and authenticated to your Copado org
- The **Salesforce DX MCP server** configured and enabled in Cursor

Authenticate your Copado org:
```bash
sf org login web --alias my-copado-org
```

The skill will list your authenticated orgs and ask you to pick the one containing Copado.

### 4. Copado Objects Required
Your Salesforce user must have read access to these Copado objects:

| Object | Purpose |
|--------|---------|
| `copado__Promoted_User_Story__c` | Stories in each promotion package |
| `copado__User_Story__c` | Story details incl. `Exclude_from_Copado__c` flag |
| `copado__Promotion__c` | Promotion records |
| `copado__Environment__c` | Environment names |

Key linking field: `copadoccmint__External_Id__c` — the Jira issue key stored on each Copado User Story.

### 5. Python 3 + openpyxl
Required for Excel report generation:
```bash
pip3 install openpyxl
```
On macOS with system Python 3.9+, `openpyxl` is often pre-installed.

---

## File Structure

```
Cursor Skills/
└── deploy-verification/
    ├── SKILL.md      <- AI agent instruction file (drop into your Cursor project)
    └── README.md     <- This file
```

---

## Installation

1. Copy `SKILL.md` into your Cursor project at:
   ```
   .cursor/skills/sf-deploy-verification/SKILL.md
   ```

2. Restart Cursor (or reload the window).

3. Trigger the skill in Cursor chat:
   > *"Run the deploy verification for fix version 4/21/26 OCRM Prod and promotions P82787, P82788"*

---

## Inputs

| Input | Example |
|-------|---------|
| Jira Fix Version | `4/21/26 OCRM Prod Deployment` |
| Copado Promotion Name(s) | `P82787, P82788, P83111` |
| Output Excel path | `~/Desktop/deploy-verification.xlsx` |

---

## Can Any Developer Run This?

**Yes** — as long as they have the five prerequisites above, the skill is fully self-contained in `SKILL.md`. No additional code, no separate config files, and no environment setup beyond what is listed.

---

## Project-Specific Notes (SDPOCC / GM OnStar)

These defaults are baked into `SKILL.md` and work out-of-the-box for this project:

| Setting | Value |
|---------|-------|
| Jira project | `SDPOCC` |
| Feature issue type | `ART Feature` (not `Feature`) |
| Bug issue type | `Defect` (not `Bug`) |
| NoCop tag field | `customfield_10938` (SSE Tags) |
| Auto-excluded titles | Starts with `QE - Manual Testing` |
| Auto-excluded statuses | `Cancelled` / `Canceled` |
| Salesforce Team indicator | Assignee name contains `(C)` |
