---
name: sf-org-assessment
description: Triggers whenever a user wants to assess, audit, review, or health-check a Salesforce org. Also triggers for "look at my org", "what's wrong with my Salesforce", pre-go-live reviews, post-implementation checkups, and org hygiene questions.
arguments: false
---

You are performing a Salesforce org assessment. You will connect to an org, gather data, and generate an HTML health report.

---

## Step 1: Identify Org

Ask the user which org to assess. If they are not sure, run:

```bash
sf org list --json
```

Show the list of authenticated orgs and ask them to pick one. Store the alias as ORG_ALIAS.

---

## Step 2: Discovery Notes (Optional)

Ask:
> "Do you have any specific areas of concern or context I should factor in? For example: pre-go-live review, post-migration, specific compliance concerns, known pain points. (Press Enter to skip.)"

Store any notes as DISCOVERY_NOTES. If blank, omit the `--notes` argument.

---

## Step 3: Set Output Path

Default output: `~/Desktop/sf_assessment_<ORG_ALIAS>.html`

Ask the user to confirm or change it. Store as OUTPUT_PATH. Create the output directory if needed.

---

## Step 4: Run Assessment Script

```bash
python3 ~/.claude/skills/sf-org-assessment/scripts/run_assessment.py \
  --org "ORG_ALIAS" \
  --output "OUTPUT_PATH" \
  [--notes "DISCOVERY_NOTES"]
```

Report progress as the script runs. The script prints section headers as it goes.

If the script fails with a CLI auth error, tell the user:
> "The org may have expired. Run `sf org login web -a ORG_ALIAS` to re-authenticate."

---

## Step 5: Open Report

Open the HTML file in the default browser:

```bash
open "OUTPUT_PATH"
```

---

## Step 6: Summarize

Read the output JSON written alongside the HTML (`OUTPUT_PATH.json` if available) or parse the script's stdout to summarize:

1. **Health Score** — number and letter grade
2. **Critical and High findings** — list them with one-line explanations
3. **Top recommendation** — the single most impactful thing to fix

Then ask:
> "Would you like to drill deeper into any area — Apex coverage, Flow hygiene, OmniScript versions, security, or data quality?"
