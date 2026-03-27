---
name: sf-document
description: Generate Salesforce implementation documentation. Supports two modes — Integration Flow (single component, with Mermaid diagram) and Scope of Change (TA notes from Jira, explains what was built and why).
arguments: true
---

You are helping the user generate Salesforce implementation documentation. The input is: **$ARGUMENTS**

---

## Step 1: Determine Mode

Read the input in $ARGUMENTS and determine which mode to use:

**Mode 1 — Integration Flow**: The user provided a specific component name (short, e.g. "Lock Unlock Omniscript", "Care_CreateDraftDealerCase"). Output: a flow diagram showing how components connect, with a Mermaid diagram.

**Mode 2 — Scope of Change**: The user pasted a Jira story, TA notes, or functional description (long text with acceptance criteria, technical notes, or "Given that..." language). Output: a plain-English implementation document explaining what was built and why. No Mermaid diagram.

If it is not clear from $ARGUMENTS, ask:
> "Are you documenting a specific component (e.g. an OmniScript or Flow name), or do you want to paste Jira/TA notes for a scope-of-change document?"

---

## Step 2: Collect Inputs

Ask the user for the following in a single message:

1. **Local repo path** — path to the local Salesforce project (e.g. `~/Documents/GM - Onstar Project/OCRM_219315_salesforce`). Press Enter to use GitHub instead.
2. **GitHub repo** — only if no local path, in `owner/repo` format.
3. **Branch** — branch to use (default: `tst`).
4. **GitHub token** — only if using GitHub and the repo is private.
5. **Output directory** — where to save the file (default: `~/Desktop/sf-translation-output`).

Create OUTPUT_DIR if it does not exist. Store as: LOCAL_PATH, GITHUB_REPO, BRANCH, GITHUB_TOKEN, OUTPUT_DIR.

---

## Step 3: Fetch and Parse Metadata

### Mode 1 — Integration Flow

Run:
```bash
python3 ~/.claude/skills/sf-document/scripts/fetch_metadata.py \
  --local-path "LOCAL_PATH" \
  --component "COMPONENT_NAME" \
  --output "OUTPUT_DIR/COMPONENT_NAME_metadata.json" \
  --max-files 20
```

### Mode 2 — Scope of Change

First, extract the **reference component name** from the TA notes — the existing Salesforce component that the change is based on or modifies (e.g. if the notes say "copy from `Dealer_Care_Draft`", the grep term is `Dealer_Care_Draft`).

If multiple reference names are mentioned, pick the most specific one (e.g. a record type API name, not a generic word like "Case").

Run:
```bash
python3 ~/.claude/skills/sf-document/scripts/fetch_metadata.py \
  --local-path "LOCAL_PATH" \
  --grep-term "REFERENCE_COMPONENT_NAME" \
  --output "OUTPUT_DIR/DOC_NAME_metadata.json" \
  --max-files 40
```

For GitHub source, replace `--local-path` with `--repo`, `--branch`, and optionally `--token`.

Report how many files were found. If zero, ask the user to confirm the reference component name.

---

## Step 4: Read the Metadata JSON

Read the output JSON file. Understand the full picture:
- What components exist and what type they are
- What each component does based on its parsed content
- How they relate to each other

**Mode 1**: Focus on the latest version of each component (highest version number suffix). Build the integration chain: OmniScript → IPs → Apex → Named Credentials → External API → callback → Flow → Salesforce records.

**Mode 2**: Group components by type. For each one, understand what it does in the context of the business change described in the TA notes.

---

## Step 5: Generate the Documentation

### Mode 1 — Integration Flow Document

Write to `OUTPUT_DIR/COMPONENT_NAME_documentation.md` using this structure:

```markdown
# [Component Name] — Implementation Documentation

## Overview
[2–3 sentences: what this feature does, who uses it, what it enables]

## Component Inventory
| Component | Type | Description |
|-----------|------|-------------|

## Integration Flow
[Numbered step-by-step — each step says what happens, which component does it, and why]

## API Integration Details
[Only if there is an external API call — endpoint, method, headers, request body, response pattern, inbound callback if async]

## Mermaid Diagram
[flowchart TD — 6–12 nodes, primary components only]

## Notes
[Active version, async patterns, shared utilities, known limitations]
```

**Writing rules:**
- Every step in the flow must name the specific component AND explain what it does, not just that it runs
- For async APIs: show the outbound call and the callback as two separate phases
- Mermaid shapes: `[Name]` = OmniScript/LWC, `(Name)` = Integration Procedure, `[[Name]]` = DataRaptor, `{Name}` = Apex, `[(Name)]` = SF Records, `((Name))` = External API

---

### Mode 2 — Scope of Change Document

Write to `OUTPUT_DIR/DOC_NAME_documentation.md` using this structure:

```markdown
# [Feature Name] — Implementation Documentation

## What Was Built
[3–5 sentences explaining the business problem, what existed before, and what is different after this change. Written for someone who was not in the design discussions.]

## New [Object / Record Type / Component]
[If a new component was created — what it is, what it inherits, what makes it different]

## How [Primary Flow / Process] Works
[Step-by-step narrative of the main user journey or automated process. Each step names the component AND explains what it does in context. Do not say "add record type to conditions" — say what the component does and what specifically changed and why.]

## Other Components Updated
| Component | What It Does | What Changed |
|-----------|-------------|--------------|
[For every other impacted component — one row. The "What It Does" column must explain the component's purpose, not just its name. The "What Changed" column must say the specific change in plain English.]

## [Access / Permissions / Routing / Queues] — if applicable
[Any configuration tables — queues, permission sets, record type access]

## What Was Not Changed
[Explicitly state what is unchanged so the reader knows the blast radius]

## Dependencies
[Other stories or components this depends on]
```

**Writing rules:**
- Never use internal developer shorthand ("add RT to conditions", "AC2 logic", "same as Dealer_Care_Draft") — always explain in full sentences what the change means
- Every component row in the "Other Components Updated" table must have a plain-English "What It Does" description — not just the component name repeated
- Write as if the reader was not in any of the design meetings

---

## Step 6: Report

Tell the user:
```
Documentation written to:
  OUTPUT_DIR/DOC_NAME_documentation.md

Components documented: [count by type]
```

Then ask: "Does this look accurate? Anything to adjust?"
