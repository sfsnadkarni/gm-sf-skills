#!/usr/bin/env python3
"""
Salesforce Org Assessment — run_assessment.py
Gathers org health data via SF CLI and generates a polished HTML report.

Usage:
  python3 run_assessment.py --org <alias> --output <path.html> [--notes "..."] [--notes-file path] [--mock]
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args():
    p = argparse.ArgumentParser(description="Salesforce Org Assessment")
    p.add_argument("--org",        required=True,  help="SF CLI org alias or username")
    p.add_argument("--output",     required=True,  help="Output HTML file path")
    p.add_argument("--notes",      default="",     help="Discovery notes (inline)")
    p.add_argument("--notes-file", default="",     help="Path to discovery notes file")
    p.add_argument("--mock",       action="store_true", help="Use mock data (no live org)")
    return p.parse_args()

# ---------------------------------------------------------------------------
# SF CLI helpers
# ---------------------------------------------------------------------------

def sf_query(soql: str, org: str, tooling: bool = False) -> list:
    cmd = ["sf", "data", "query", "--json", "-q", soql, "-o", org]
    if tooling:
        cmd.append("--use-tooling-api")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        data = json.loads(r.stdout or "{}")
        return data.get("result", {}).get("records", [])
    except Exception as e:
        print(f"  [warn] Query failed: {e}", file=sys.stderr)
        return []

def sf_limits(org: str) -> dict:
    try:
        r = subprocess.run(
            ["sf", "limits", "api", "display", "--json", "-o", org],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(r.stdout or "{}")
        return data.get("result", {})
    except Exception:
        return {}

def sf_org_display(org: str) -> dict:
    try:
        r = subprocess.run(
            ["sf", "org", "display", "--json", "-o", org],
            capture_output=True, text=True, timeout=30
        )
        data = json.loads(r.stdout or "{}")
        return data.get("result", {})
    except Exception:
        return {}

# ---------------------------------------------------------------------------
# Data gathering
# ---------------------------------------------------------------------------

def gather(org: str) -> dict:
    now = datetime.now(timezone.utc)
    ninety_days_ago = (now - timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("  Gathering org info...")
    org_info = sf_org_display(org)

    print("  Gathering user data...")
    users_all = sf_query(
        "SELECT Id, IsActive, LastLoginDate, CreatedDate FROM User WHERE IsPortalEnabled = false AND ProfileId != null",
        org
    )
    active_users  = [u for u in users_all if u.get("IsActive")]
    inactive_users = [u for u in users_all if not u.get("IsActive")]
    never_logged_in = [u for u in active_users if not u.get("LastLoginDate")]
    inactive_90 = [
        u for u in active_users
        if u.get("LastLoginDate") and u["LastLoginDate"] < ninety_days_ago
    ]

    print("  Gathering automation data...")
    # FlowDefinitionView — one row per flow definition, IsActive is a boolean
    flows = sf_query(
        "SELECT Id, MasterLabel, ProcessType, IsActive, VersionNumber, Description FROM FlowDefinitionView",
        org
    )
    active_flows   = [f for f in flows if f.get("IsActive") is True]
    inactive_flows = [f for f in flows if f.get("IsActive") is False]

    # Flows missing descriptions
    flows_no_desc = [f for f in flows if not (f.get("Description") or "").strip()]

    # Workflow rules — active flag lives on the Flow object in Tooling API, not WorkflowRule
    # Count all WorkflowRule records; any presence is a finding (deprecated automation)
    workflow_rules = sf_query(
        "SELECT Id, Name FROM WorkflowRule",
        org, tooling=True
    )
    # Active workflow rules: query Flow where ProcessType = 'Workflow' and Status = 'Active'
    active_wf_flows = sf_query(
        "SELECT Id, Name FROM Flow WHERE ProcessType = 'Workflow' AND Status = 'Active'",
        org, tooling=True
    )
    active_wf = active_wf_flows if active_wf_flows else workflow_rules  # fallback: assume all are active

    # Validation rules
    val_rules = sf_query(
        "SELECT Id, ValidationName, EntityDefinitionId, Active FROM ValidationRule",
        org, tooling=True
    )
    active_val = [v for v in val_rules if v.get("Active")]

    print("  Gathering Apex data...")
    apex_classes = sf_query(
        "SELECT Id, Name, Status, IsValid FROM ApexClass",
        org, tooling=True
    )
    apex_triggers = sf_query(
        "SELECT Id, Name, TableEnumOrId, Status, IsValid FROM ApexTrigger",
        org, tooling=True
    )
    invalid_classes  = [c for c in apex_classes  if not c.get("IsValid")]
    invalid_triggers = [t for t in apex_triggers if not t.get("IsValid")]

    # Multi-trigger objects
    trigger_objects: dict = {}
    for t in apex_triggers:
        if t.get("Status") == "Active":
            obj = t.get("TableEnumOrId", "Unknown")
            trigger_objects.setdefault(obj, []).append(t.get("Name"))
    multi_trigger_objects = {k: v for k, v in trigger_objects.items() if len(v) > 1}

    # Apex test coverage
    coverage_rows = sf_query(
        "SELECT PercentCovered FROM ApexOrgWideCoverage",
        org, tooling=True
    )
    coverage_pct = coverage_rows[0].get("PercentCovered", 0) if coverage_rows else 0

    print("  Gathering metadata...")
    custom_objects = sf_query(
        "SELECT Id, DeveloperName FROM EntityDefinition WHERE IsCustomizable = true AND KeyPrefix != null",
        org, tooling=True
    )
    custom_fields = sf_query(
        "SELECT Id FROM CustomField",
        org, tooling=True
    )
    profiles = sf_query("SELECT Id, Name FROM Profile", org)
    perm_sets = sf_query("SELECT Id, Name FROM PermissionSet WHERE IsOwnedByProfile = false", org)

    print("  Gathering OmniStudio metadata...")
    # OmniStudio objects differ by deployment type:
    #   Native OmniStudio (no namespace): OmniScript, OmniDataTransform, OmniUiCard
    #   Vlocity managed package:          vlocity_cmt__OmniScript__c, vlocity_cmt__OmniDataTransform__c, vlocity_cmt__FlexCard__c
    # Integration Procedures are stored as OmniScript records with Type = 'IntegrationProcedure'

    # --- OmniScripts ---
    omniscripts = sf_query(
        "SELECT Id, Name, Type, SubType, Language, IsActive, VersionNumber FROM OmniScript WHERE Type != 'IntegrationProcedure'",
        org
    )
    if not omniscripts:
        omniscripts = sf_query(
            "SELECT Id, Name, vlocity_cmt__Type__c, vlocity_cmt__IsActive__c, vlocity_cmt__Version__c "
            "FROM vlocity_cmt__OmniScript__c WHERE vlocity_cmt__Type__c != 'IntegrationProcedure'",
            org
        )
        # Normalize field names
        omniscripts = [{"IsActive": r.get("vlocity_cmt__IsActive__c"), "Name": r.get("Name")} for r in omniscripts]

    active_os   = [o for o in omniscripts if o.get("IsActive")]
    inactive_os = [o for o in omniscripts if not o.get("IsActive")]

    # --- Integration Procedures ---
    integration_procs = sf_query(
        "SELECT Id, Name, IsActive, VersionNumber FROM OmniScript WHERE Type = 'IntegrationProcedure'",
        org
    )
    if not integration_procs:
        integration_procs = sf_query(
            "SELECT Id, Name, vlocity_cmt__IsActive__c FROM vlocity_cmt__OmniScript__c "
            "WHERE vlocity_cmt__Type__c = 'IntegrationProcedure'",
            org
        )
        integration_procs = [{"IsActive": r.get("vlocity_cmt__IsActive__c"), "Name": r.get("Name")} for r in integration_procs]

    active_ips   = [i for i in integration_procs if i.get("IsActive")]
    inactive_ips = [i for i in integration_procs if not i.get("IsActive")]

    # --- DataRaptors ---
    data_raptors = sf_query(
        "SELECT Id, Name, InterfaceType, IsActive FROM OmniDataTransform",
        org
    )
    if not data_raptors:
        data_raptors = sf_query(
            "SELECT Id, Name, vlocity_cmt__InterfaceType__c, vlocity_cmt__IsActive__c FROM vlocity_cmt__OmniDataTransform__c",
            org
        )
        data_raptors = [{"IsActive": r.get("vlocity_cmt__IsActive__c"), "Name": r.get("Name")} for r in data_raptors]

    active_drs   = [d for d in data_raptors if d.get("IsActive")]
    inactive_drs = [d for d in data_raptors if not d.get("IsActive")]

    # --- FlexCards ---
    flexcards = sf_query(
        "SELECT Id, Name, IsActive, VersionNumber FROM OmniUiCard",
        org
    )
    if not flexcards:
        flexcards = sf_query(
            "SELECT Id, Name, vlocity_cmt__Active__c FROM vlocity_cmt__FlexCard__c",
            org
        )
        flexcards = [{"IsActive": r.get("vlocity_cmt__Active__c"), "Name": r.get("Name")} for r in flexcards]

    active_fc   = [f for f in flexcards if f.get("IsActive")]
    inactive_fc = [f for f in flexcards if not f.get("IsActive")]

    print("  Gathering security data...")
    owd_rows = sf_query(
        "SELECT SobjectType, InternalSharingModel, ExternalSharingModel FROM EntityDefinition "
        "WHERE IsCustomizable = true AND InternalSharingModel != null",
        org, tooling=True
    )
    public_read_write = [r for r in owd_rows if r.get("InternalSharingModel") == "ReadWrite"]

    print("  Gathering data quality metrics...")
    dup_sets = sf_query("SELECT Id FROM DuplicateRecordSet", org)
    # Accounts owned by inactive users
    inactive_owner_accounts = sf_query(
        "SELECT Id FROM Account WHERE Owner.IsActive = false",
        org
    )
    # Leads older than 365 days not converted
    one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
    old_leads = sf_query(
        f"SELECT Id FROM Lead WHERE IsConverted = false AND CreatedDate < {one_year_ago}",
        org
    )

    print("  Gathering integration data...")
    connected_apps = sf_query("SELECT Id, Name FROM ConnectedApplication", org, tooling=True)
    named_creds = sf_query("SELECT Id, DeveloperName, Endpoint FROM NamedCredential", org, tooling=True)

    print("  Gathering API limits...")
    limits = sf_limits(org)
    daily_api = limits.get("DailyApiRequests", {})

    return {
        "org_info": org_info,
        "users": {
            "total": len(users_all),
            "active": len(active_users),
            "inactive": len(inactive_users),
            "never_logged_in": len(never_logged_in),
            "inactive_90": len(inactive_90),
        },
        "automation": {
            "flows_total": len(flows),
            "flows_active": len(active_flows),
            "flows_inactive": len(inactive_flows),
            "flows_no_description": len(flows_no_desc),
            "flow_types": _count_by(active_flows, "ProcessType"),
            "workflow_rules_total": len(workflow_rules),
            "workflow_rules_active": len(active_wf),
            "validation_rules_total": len(val_rules),
            "validation_rules_active": len(active_val),
        },
        "apex": {
            "class_count": len(apex_classes),
            "trigger_count": len(apex_triggers),
            "invalid_classes": len(invalid_classes),
            "invalid_triggers": len(invalid_triggers),
            "invalid_class_names": [c.get("Name") for c in invalid_classes[:10]],
            "invalid_trigger_names": [t.get("Name") for t in invalid_triggers[:10]],
            "multi_trigger_objects": multi_trigger_objects,
            "coverage_pct": coverage_pct,
        },
        "omnistudio": {
            "omniscripts_total": len(omniscripts),
            "omniscripts_active": len(active_os),
            "omniscripts_inactive": len(inactive_os),
            "integration_procs_total": len(integration_procs),
            "integration_procs_active": len(active_ips),
            "integration_procs_inactive": len(inactive_ips),
            "data_raptors_total": len(data_raptors),
            "data_raptors_active": len(active_drs),
            "data_raptors_inactive": len(inactive_drs),
            "flexcards_total": len(flexcards),
            "flexcards_active": len(active_fc),
            "flexcards_inactive": len(inactive_fc),
        },
        "metadata": {
            "custom_objects": len(custom_objects),
            "custom_fields": len(custom_fields),
            "profiles": len(profiles),
            "permission_sets": len(perm_sets),
        },
        "security": {
            "owd_rows": [
                {"object": r.get("SobjectType"), "internal": r.get("InternalSharingModel"), "external": r.get("ExternalSharingModel")}
                for r in owd_rows[:30]
            ],
            "public_read_write_count": len(public_read_write),
            "public_read_write_objects": [r.get("SobjectType") for r in public_read_write[:20]],
        },
        "data_quality": {
            "duplicate_sets": len(dup_sets),
            "inactive_owner_accounts": len(inactive_owner_accounts),
            "old_unconverted_leads": len(old_leads),
        },
        "integrations": {
            "connected_apps": len(connected_apps),
            "connected_app_names": [a.get("Name") for a in connected_apps],
            "named_credentials": len(named_creds),
            "named_credential_names": [n.get("DeveloperName") for n in named_creds],
        },
        "api_limits": {
            "daily_api_max": daily_api.get("Max", 0),
            "daily_api_remaining": daily_api.get("Remaining", 0),
        },
    }

def _count_by(rows: list, field: str) -> dict:
    counts: dict = {}
    for r in rows:
        v = r.get(field, "Unknown") or "Unknown"
        counts[v] = counts.get(v, 0) + 1
    return counts

# ---------------------------------------------------------------------------
# Mock data
# ---------------------------------------------------------------------------

def mock_data() -> dict:
    return {
        "org_info": {
            "instanceUrl": "https://mock.salesforce.com",
            "orgId": "00D000000000000EAA",
            "alias": "mock-org",
            "username": "admin@mock.com",
        },
        "users": {"total": 120, "active": 85, "inactive": 35, "never_logged_in": 12, "inactive_90": 22},
        "automation": {
            "flows_total": 74, "flows_active": 52, "flows_inactive": 22,
            "flows_no_description": 18,
            "flow_types": {"AutoLaunchedFlow": 28, "Screen": 14, "RecordTriggeredFlow": 10},
            "workflow_rules_total": 9, "workflow_rules_active": 6,
            "validation_rules_total": 31, "validation_rules_active": 24,
        },
        "apex": {
            "class_count": 148, "trigger_count": 22,
            "invalid_classes": 3, "invalid_triggers": 1,
            "invalid_class_names": ["OldBatchJob", "DeprecatedUtil", "LegacyHandler"],
            "invalid_trigger_names": ["OldContactTrigger"],
            "multi_trigger_objects": {"Case": ["CaseTrigger", "CaseTriggerLegacy"], "Lead": ["LeadTrigger", "LeadRouting"]},
            "coverage_pct": 72,
        },
        "omnistudio": {
            "omniscripts_total": 18, "omniscripts_active": 12, "omniscripts_inactive": 6,
            "integration_procs_total": 34, "integration_procs_active": 22, "integration_procs_inactive": 12,
            "data_raptors_total": 47, "data_raptors_active": 31, "data_raptors_inactive": 16,
            "flexcards_total": 22, "flexcards_active": 16, "flexcards_inactive": 6,
        },
        "metadata": {"custom_objects": 42, "custom_fields": 310, "profiles": 18, "permission_sets": 34},
        "security": {
            "owd_rows": [
                {"object": "Account", "internal": "Private", "external": "None"},
                {"object": "Case", "internal": "ReadWrite", "external": "None"},
                {"object": "Lead", "internal": "ReadWrite", "external": "None"},
                {"object": "Custom_Object__c", "internal": "ReadWrite", "external": "None"},
            ],
            "public_read_write_count": 12,
            "public_read_write_objects": ["Case", "Lead", "Custom_Object__c", "Another_Object__c"],
        },
        "data_quality": {"duplicate_sets": 143, "inactive_owner_accounts": 67, "old_unconverted_leads": 892},
        "integrations": {
            "connected_apps": 7,
            "connected_app_names": ["MuleSoft Runtime", "Tableau CRM", "Slack for Salesforce", "DocuSign", "AWS S3 Connector", "Azure AD", "ServiceNow"],
            "named_credentials": 5,
            "named_credential_names": ["OnStarMulesoftNamedCred", "AzureAD", "ServiceNowAPI", "DocuSignAPI", "S3Cred"],
        },
        "api_limits": {"daily_api_max": 5000000, "daily_api_remaining": 3200000},
    }

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def score(d: dict) -> tuple[int, list]:
    """Returns (score_0_to_100, list_of_findings)."""
    points = 100
    findings = []

    def deduct(pts, severity, category, title, detail, recommendation):
        nonlocal points
        points -= pts
        findings.append({
            "severity": severity,
            "category": category,
            "title": title,
            "detail": detail,
            "recommendation": recommendation,
        })

    # --- Apex ---
    cov = d["apex"]["coverage_pct"]
    if cov < 75:
        deduct(15, "Critical", "Apex", "Apex test coverage below 75%",
               f"Current coverage: {cov}%. Salesforce requires 75% to deploy to production.",
               "Write unit tests for untested classes. Focus on triggers and service classes first.")
    elif cov < 85:
        deduct(5, "Medium", "Apex", "Apex test coverage below 85%",
               f"Current coverage: {cov}%. Best practice is ≥ 85% to leave headroom before deployments.",
               "Add tests to bring coverage above 85% as a buffer against regressions.")

    if d["apex"]["invalid_classes"] > 0 or d["apex"]["invalid_triggers"] > 0:
        names = d["apex"]["invalid_class_names"] + d["apex"]["invalid_trigger_names"]
        deduct(12, "High", "Apex", "Invalid Apex classes or triggers detected",
               f"{d['apex']['invalid_classes']} invalid class(es), {d['apex']['invalid_triggers']} invalid trigger(s): {', '.join(names[:5])}.",
               "Fix or delete invalid Apex. These block future deployments and indicate broken dependencies.")

    multi = d["apex"]["multi_trigger_objects"]
    if multi:
        objs = ", ".join(f"{k} ({len(v)} triggers)" for k, v in list(multi.items())[:5])
        deduct(10, "High", "Apex", "Multiple triggers on the same object",
               f"Objects with multiple triggers: {objs}. Multiple triggers have unpredictable execution order.",
               "Consolidate into a single trigger per object using a trigger handler framework.")

    # --- Automation ---
    if d["automation"]["workflow_rules_active"] > 0:
        deduct(10, "High", "Automation", "Active Workflow Rules (deprecated)",
               f"{d['automation']['workflow_rules_active']} active Workflow Rule(s) found. Workflow Rules are scheduled for retirement.",
               "Migrate all active Workflow Rules to Flows before the retirement deadline.")
    else:
        findings.append({
            "severity": "Pass",
            "category": "Automation",
            "title": "No active Workflow Rules",
            "detail": "All automation uses modern Flows — no legacy Workflow Rules detected.",
            "recommendation": "",
        })

    if d["automation"]["flows_no_description"] > 5:
        deduct(3, "Medium", "Automation", "Many flows missing descriptions",
               f"{d['automation']['flows_no_description']} flows have no description. This makes maintenance and handovers difficult.",
               "Add descriptions to all flows explaining the business purpose and trigger conditions.")

    # --- OmniStudio ---
    os_inactive = d["omnistudio"]["omniscripts_inactive"]
    ip_inactive = d["omnistudio"]["integration_procs_inactive"]
    dr_inactive = d["omnistudio"]["data_raptors_inactive"]

    if os_inactive > 5:
        deduct(4, "Medium", "OmniStudio", "High number of inactive OmniScript versions",
               f"{os_inactive} inactive OmniScript versions. Old versions accumulate over time and clutter the org.",
               "Review and delete OmniScript versions that are no longer needed. Keep at most 2–3 versions per script.")

    if ip_inactive > 10:
        deduct(4, "Medium", "OmniStudio", "High number of inactive Integration Procedures",
               f"{ip_inactive} inactive Integration Procedure versions. Old versions add noise and can confuse developers.",
               "Clean up inactive Integration Procedure versions. Document which version is the active baseline.")

    if dr_inactive > 10:
        deduct(3, "Medium", "OmniStudio", "High number of inactive DataRaptor versions",
               f"{dr_inactive} inactive DataRaptor versions. Stale versions increase maintenance overhead.",
               "Archive or delete outdated DataRaptor versions. Keep the active and one prior version.")

    # --- Users ---
    pct_inactive_90 = d["users"]["inactive_90"] / max(d["users"]["active"], 1)
    if pct_inactive_90 > 0.20:
        deduct(8, "High", "Users", "20%+ active users inactive for 90+ days",
               f"{d['users']['inactive_90']} of {d['users']['active']} active users have not logged in for 90+ days ({pct_inactive_90:.0%}).",
               "Review and deactivate unused accounts. Each active license has a cost and a security risk.")

    if d["users"]["never_logged_in"] > 0:
        deduct(4, "Medium", "Users", "Active users who have never logged in",
               f"{d['users']['never_logged_in']} active user(s) have never logged in.",
               "Confirm these accounts are needed. Deactivate any that were provisioned but never used.")

    # --- Security ---
    if d["security"]["public_read_write_count"] >= 10:
        objs = ", ".join(d["security"]["public_read_write_objects"][:5])
        deduct(6, "Medium", "Security", "10+ objects with Public Read/Write OWD",
               f"{d['security']['public_read_write_count']} objects have Public Read/Write sharing: {objs}...",
               "Review OWD settings. Use role hierarchy and sharing rules instead of org-wide Public Read/Write where possible.")

    # --- Data Quality ---
    if d["data_quality"]["duplicate_sets"] >= 100:
        deduct(8, "High", "Data Quality", "100+ duplicate record sets detected",
               f"{d['data_quality']['duplicate_sets']} duplicate record sets exist in the org.",
               "Run deduplication jobs and enforce duplicate rules. Consider a data cleanse before go-live.")

    if d["data_quality"]["inactive_owner_accounts"] > 50:
        deduct(4, "Medium", "Data Quality", "Accounts owned by inactive users",
               f"{d['data_quality']['inactive_owner_accounts']} Accounts are owned by inactive users, blocking assignments and automations.",
               "Reassign these records to an active owner or a queue.")

    if d["data_quality"]["old_unconverted_leads"] > 500:
        deduct(3, "Medium", "Data Quality", "Large volume of old unconverted Leads",
               f"{d['data_quality']['old_unconverted_leads']} Leads have not been converted in over a year.",
               "Implement a Lead aging policy. Convert, disqualify, or archive stale Leads.")

    points = max(0, points)
    return points, findings


def letter_grade(score: int) -> str:
    if score >= 90: return "A"
    if score >= 80: return "B"
    if score >= 70: return "C"
    if score >= 60: return "D"
    return "F"

def score_color(score: int) -> str:
    if score >= 80: return "#22c55e"
    if score >= 65: return "#eab308"
    if score >= 50: return "#f97316"
    return "#ef4444"

# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

SEVERITY_COLORS = {
    "Critical": ("#ef4444", "#fef2f2"),
    "High":     ("#f97316", "#fff7ed"),
    "Medium":   ("#eab308", "#fefce8"),
    "Low":      ("#3b82f6", "#eff6ff"),
    "Pass":     ("#22c55e", "#f0fdf4"),
}

def sev_badge(sev: str) -> str:
    col, bg = SEVERITY_COLORS.get(sev, ("#6b7280", "#f9fafb"))
    return f'<span style="background:{bg};color:{col};border:1px solid {col};border-radius:4px;padding:2px 8px;font-size:11px;font-weight:700;white-space:nowrap">{sev}</span>'

def metric_card(label: str, value, sub: str = "") -> str:
    sub_html = f'<div style="font-size:12px;color:#6b7280;margin-top:4px">{sub}</div>' if sub else ""
    return f'''
    <div style="background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:20px;text-align:center;min-width:120px;flex:1">
      <div style="font-size:32px;font-weight:700;color:#1f2937">{value}</div>
      <div style="font-size:13px;color:#6b7280;margin-top:4px">{label}</div>
      {sub_html}
    </div>'''

def build_html(d: dict, health_score: int, findings: list, notes: str, org_alias: str) -> str:
    org_info  = d["org_info"]
    org_name  = org_info.get("alias") or org_info.get("username") or org_alias
    inst_url  = org_info.get("instanceUrl", "")
    grade     = letter_grade(health_score)
    s_col     = score_color(health_score)
    gen_date  = datetime.now().strftime("%B %d, %Y %H:%M")

    critical = sum(1 for f in findings if f["severity"] == "Critical")
    high     = sum(1 for f in findings if f["severity"] == "High")
    medium   = sum(1 for f in findings if f["severity"] == "Medium")
    passes   = sum(1 for f in findings if f["severity"] == "Pass")

    # --- Key Findings ---
    finding_rows = ""
    for sev in ("Critical", "High", "Medium", "Low", "Pass"):
        for f in [x for x in findings if x["severity"] == sev]:
            col, bg = SEVERITY_COLORS.get(sev, ("#6b7280", "#f9fafb"))
            rec = f'<div style="margin-top:6px;font-size:12px;color:#374151"><strong>Recommendation:</strong> {f["recommendation"]}</div>' if f["recommendation"] else ""
            finding_rows += f'''
            <div style="border:1px solid {col};border-left:4px solid {col};background:{bg};border-radius:6px;padding:14px 16px;margin-bottom:10px">
              <div style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">
                {sev_badge(sev)}
                <span style="font-size:12px;color:#6b7280;background:#f3f4f6;padding:2px 8px;border-radius:4px">{f["category"]}</span>
                <strong style="color:#111827">{f["title"]}</strong>
              </div>
              <div style="margin-top:8px;font-size:13px;color:#374151">{f["detail"]}</div>
              {rec}
            </div>'''

    # --- Flow type chart data ---
    flow_types = d["automation"]["flow_types"]
    ft_labels  = json.dumps(list(flow_types.keys()))
    ft_values  = json.dumps(list(flow_types.values()))
    ft_colors  = json.dumps(["#6366f1","#8b5cf6","#ec4899","#14b8a6","#f59e0b","#10b981","#3b82f6"])

    # --- User adoption chart data ---
    active_recent = d["users"]["active"] - d["users"]["inactive_90"] - d["users"]["never_logged_in"]
    active_recent = max(0, active_recent)
    ua_labels = json.dumps(["Active (<90 days)", "Inactive 90+ days", "Never logged in"])
    ua_values = json.dumps([active_recent, d["users"]["inactive_90"], d["users"]["never_logged_in"]])
    ua_colors = json.dumps(["#22c55e", "#f97316", "#ef4444"])

    # --- OmniStudio chart data ---
    os_data = d["omnistudio"]
    omni_labels = json.dumps(["OmniScripts", "Integration Procedures", "DataRaptors", "FlexCards"])
    omni_active = json.dumps([os_data["omniscripts_active"], os_data["integration_procs_active"], os_data["data_raptors_active"], os_data["flexcards_active"]])
    omni_inactive = json.dumps([os_data["omniscripts_inactive"], os_data["integration_procs_inactive"], os_data["data_raptors_inactive"], os_data["flexcards_inactive"]])

    # --- API usage ---
    api_max  = d["api_limits"]["daily_api_max"]
    api_rem  = d["api_limits"]["daily_api_remaining"]
    api_used = max(0, api_max - api_rem)
    api_pct  = round(api_used / api_max * 100, 1) if api_max else 0

    # --- OWD table ---
    owd_rows_html = ""
    for row in d["security"]["owd_rows"]:
        internal = row.get("internal", "")
        ext      = row.get("external", "")
        style = ""
        if internal == "ReadWrite":
            style = "background:#fff7ed"
        elif internal == "Private":
            style = "background:#f0fdf4"
        owd_rows_html += f'<tr style="{style}"><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb">{row["object"]}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb">{internal}</td><td style="padding:8px 12px;border-bottom:1px solid #e5e7eb">{ext}</td></tr>'

    # --- Connected apps tags ---
    app_tags = " ".join(
        f'<span style="background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;border-radius:4px;padding:3px 8px;font-size:12px">{a}</span>'
        for a in d["integrations"]["connected_app_names"]
    )
    nc_tags = " ".join(
        f'<span style="background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;border-radius:4px;padding:3px 8px;font-size:12px">{n}</span>'
        for n in d["integrations"]["named_credential_names"]
    )

    # --- Discovery notes ---
    notes_section = ""
    if notes.strip():
        notes_section = f'''
        <div class="section">
          <h2>Discovery Notes</h2>
          <div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:16px;white-space:pre-wrap;font-size:13px;color:#374151">{notes.strip()}</div>
        </div>'''

    # --- Apex invalid list ---
    invalid_apex_html = ""
    all_invalid = d["apex"]["invalid_class_names"] + d["apex"]["invalid_trigger_names"]
    if all_invalid:
        items = "".join(f"<li style='font-size:13px;color:#b91c1c'>{n}</li>" for n in all_invalid)
        invalid_apex_html = f'<ul style="margin:8px 0 0 16px;padding:0">{items}</ul>'

    # --- Multi-trigger list ---
    multi_html = ""
    for obj, triggers in d["apex"]["multi_trigger_objects"].items():
        tnames = ", ".join(triggers)
        multi_html += f'<div style="font-size:13px;color:#92400e;margin-bottom:4px"><strong>{obj}</strong>: {tnames}</div>'

    cov_col = "#22c55e" if d["apex"]["coverage_pct"] >= 85 else ("#eab308" if d["apex"]["coverage_pct"] >= 75 else "#ef4444")

    return f'''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Salesforce Org Assessment — {org_name}</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f1f5f9; color: #1f2937; }}
  .header {{ background: linear-gradient(135deg, #1e1b4b 0%, #312e81 40%, #4f46e5 100%); color: #fff; padding: 40px 48px; }}
  .header h1 {{ font-size: 28px; font-weight: 700; letter-spacing: -0.5px; }}
  .header .meta {{ font-size: 13px; color: #c7d2fe; margin-top: 4px; }}
  .score-block {{ display: flex; align-items: center; gap: 24px; margin-top: 28px; }}
  .score-num {{ font-size: 72px; font-weight: 800; line-height: 1; color: {s_col}; }}
  .score-grade {{ font-size: 48px; font-weight: 800; background: rgba(255,255,255,.15); border-radius: 12px; width: 72px; height: 72px; display: flex; align-items: center; justify-content: center; color: {s_col}; }}
  .score-label {{ font-size: 13px; color: #a5b4fc; }}
  .summary-bar {{ display: flex; gap: 16px; margin-top: 24px; flex-wrap: wrap; }}
  .summary-pill {{ background: rgba(255,255,255,.12); border-radius: 20px; padding: 6px 16px; font-size: 13px; }}
  .container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
  .section {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 12px; padding: 28px; margin-bottom: 24px; }}
  .section h2 {{ font-size: 18px; font-weight: 700; color: #111827; margin-bottom: 20px; padding-bottom: 12px; border-bottom: 1px solid #f3f4f6; }}
  .cards {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
  .chart-wrap {{ position: relative; height: 240px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
  th {{ background: #f9fafb; padding: 10px 12px; text-align: left; font-size: 12px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.05em; border-bottom: 2px solid #e5e7eb; }}
  footer {{ text-align: center; color: #9ca3af; font-size: 12px; padding: 32px 0; }}
  @media print {{
    body {{ background: #fff; }}
    .section {{ break-inside: avoid; border: 1px solid #d1d5db; }}
    .header {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
  }}
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <h1>Salesforce Org Assessment</h1>
  <div class="meta">{org_name} &nbsp;·&nbsp; {inst_url} &nbsp;·&nbsp; Generated {gen_date}</div>
  <div class="score-block">
    <div>
      <div class="score-num">{health_score}</div>
      <div class="score-label">Health Score</div>
    </div>
    <div class="score-grade">{grade}</div>
    <div>
      <div style="font-size:14px;color:#e0e7ff">Overall Grade</div>
      <div style="font-size:12px;color:#a5b4fc;margin-top:4px">A ≥ 90 &nbsp;·&nbsp; B ≥ 80 &nbsp;·&nbsp; C ≥ 70 &nbsp;·&nbsp; D ≥ 60 &nbsp;·&nbsp; F &lt; 60</div>
    </div>
  </div>
  <div class="summary-bar">
    <div class="summary-pill" style="color:#fca5a5">🔴 Critical: {critical}</div>
    <div class="summary-pill" style="color:#fdba74">🟠 High: {high}</div>
    <div class="summary-pill" style="color:#fde68a">🟡 Medium: {medium}</div>
    <div class="summary-pill" style="color:#86efac">✅ Passing: {passes}</div>
  </div>
</div>

<div class="container">

<!-- KEY FINDINGS -->
<div class="section">
  <h2>Key Findings</h2>
  {finding_rows if finding_rows else '<p style="color:#6b7280;font-size:14px">No findings — org looks healthy!</p>'}
</div>

<!-- ORG OVERVIEW -->
<div class="section">
  <h2>Org Overview</h2>
  <div class="cards">
    {metric_card("Total Users", d["users"]["total"], f'{d["users"]["active"]} active')}
    {metric_card("Custom Objects", d["metadata"]["custom_objects"], f'{d["metadata"]["custom_fields"]} custom fields')}
    {metric_card("Active Flows", d["automation"]["flows_active"], f'{d["automation"]["flows_total"]} total')}
    {metric_card("Apex Classes", d["apex"]["class_count"], f'{d["apex"]["trigger_count"]} triggers')}
    {metric_card("Profiles", d["metadata"]["profiles"], f'{d["metadata"]["permission_sets"]} perm sets')}
    {metric_card("Connected Apps", d["integrations"]["connected_apps"], f'{d["integrations"]["named_credentials"]} named creds')}
  </div>
</div>

<!-- AUTOMATION -->
<div class="section">
  <h2>Automation</h2>
  <div class="two-col">
    <div>
      <h3 style="font-size:14px;color:#374151;margin-bottom:12px">Flows by Type</h3>
      <div class="chart-wrap"><canvas id="flowTypeChart"></canvas></div>
    </div>
    <div>
      <h3 style="font-size:14px;color:#374151;margin-bottom:12px">Flow Status</h3>
      <div class="chart-wrap"><canvas id="flowStatusChart"></canvas></div>
    </div>
  </div>
  <table style="margin-top:20px">
    <tr><th>Metric</th><th>Count</th><th>Notes</th></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Workflow Rules (active)</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb"><strong style="color:{'#ef4444' if d['automation']['workflow_rules_active'] > 0 else '#22c55e'}">{d["automation"]["workflow_rules_active"]}</strong> / {d["automation"]["workflow_rules_total"]}</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#6b7280">{'⚠ Deprecated — migrate to Flows' if d['automation']['workflow_rules_active'] > 0 else '✓ None active'}</td></tr>
    <tr><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Validation Rules (active)</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{d["automation"]["validation_rules_active"]} / {d["automation"]["validation_rules_total"]}</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#6b7280"></td></tr>
    <tr><td style="padding:10px 12px">Flows without descriptions</td><td style="padding:10px 12px"><strong style="color:{'#f97316' if d['automation']['flows_no_description'] > 5 else '#22c55e'}">{d["automation"]["flows_no_description"]}</strong></td><td style="padding:10px 12px;font-size:12px;color:#6b7280">Best practice: all flows should have a description</td></tr>
  </table>
</div>

<!-- OMNISTUDIO -->
<div class="section">
  <h2>OmniStudio Components</h2>
  <div class="two-col" style="margin-bottom:20px">
    <div>
      <h3 style="font-size:14px;color:#374151;margin-bottom:12px">Active vs Inactive</h3>
      <div class="chart-wrap"><canvas id="omniChart"></canvas></div>
    </div>
    <div style="padding-top:8px">
      <table>
        <tr><th>Component</th><th>Active</th><th>Inactive</th><th>Total</th></tr>
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">OmniScripts</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#22c55e;font-weight:700">{os_data["omniscripts_active"]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{'#f97316' if os_data['omniscripts_inactive'] > 5 else '#6b7280'}">{os_data["omniscripts_inactive"]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{os_data["omniscripts_total"]}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Integration Procedures</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#22c55e;font-weight:700">{os_data["integration_procs_active"]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{'#f97316' if os_data['integration_procs_inactive'] > 10 else '#6b7280'}">{os_data["integration_procs_inactive"]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{os_data["integration_procs_total"]}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">DataRaptors</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#22c55e;font-weight:700">{os_data["data_raptors_active"]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{'#f97316' if os_data['data_raptors_inactive'] > 10 else '#6b7280'}">{os_data["data_raptors_inactive"]}</td>
          <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{os_data["data_raptors_total"]}</td>
        </tr>
        <tr>
          <td style="padding:10px 12px">FlexCards</td>
          <td style="padding:10px 12px;color:#22c55e;font-weight:700">{os_data["flexcards_active"]}</td>
          <td style="padding:10px 12px;color:{'#f97316' if os_data['flexcards_inactive'] > 5 else '#6b7280'}">{os_data["flexcards_inactive"]}</td>
          <td style="padding:10px 12px">{os_data["flexcards_total"]}</td>
        </tr>
      </table>
      <p style="font-size:12px;color:#6b7280;margin-top:12px">Best practice: retain active + 1 prior version; delete older versions.</p>
    </div>
  </div>
</div>

<!-- CODE QUALITY -->
<div class="section">
  <h2>Apex Code Quality</h2>
  <div class="cards" style="margin-bottom:20px">
    {metric_card("Test Coverage", f'{d["apex"]["coverage_pct"]}%', '<span style="color:' + cov_col + '">&#9679;</span> ' + ('Good' if d['apex']['coverage_pct'] >= 85 else ('Acceptable' if d['apex']['coverage_pct'] >= 75 else 'Below minimum')))}
    {metric_card("Invalid Apex", d["apex"]["invalid_classes"] + d["apex"]["invalid_triggers"], "classes + triggers")}
    {metric_card("Multi-trigger Objects", len(d["apex"]["multi_trigger_objects"]), "should be 0")}
    {metric_card("Apex Classes", d["apex"]["class_count"], "")}
    {metric_card("Apex Triggers", d["apex"]["trigger_count"], "")}
  </div>
  {('<div style="margin-top:8px"><strong style="font-size:13px">Invalid Apex:</strong>' + invalid_apex_html + '</div>') if invalid_apex_html else ''}
  {('<div style="margin-top:12px"><strong style="font-size:13px;color:#92400e">Multi-trigger objects:</strong><div style="margin-top:6px">' + multi_html + '</div></div>') if multi_html else ''}
</div>

<!-- USER ADOPTION -->
<div class="section">
  <h2>User Adoption</h2>
  <div class="two-col">
    <div>
      <div class="chart-wrap"><canvas id="userChart"></canvas></div>
    </div>
    <div>
      <table>
        <tr><th>Metric</th><th>Count</th></tr>
        <tr><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Total users</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{d["users"]["total"]}</td></tr>
        <tr><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Active users</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{d["users"]["active"]}</td></tr>
        <tr><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Active &lt; 90 days</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:#22c55e;font-weight:700">{active_recent}</td></tr>
        <tr><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Inactive 90+ days</td><td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;color:{'#f97316' if d['users']['inactive_90'] > 0 else '#22c55e'};font-weight:700">{d["users"]["inactive_90"]}</td></tr>
        <tr><td style="padding:10px 12px">Never logged in</td><td style="padding:10px 12px;color:{'#ef4444' if d['users']['never_logged_in'] > 0 else '#22c55e'};font-weight:700">{d["users"]["never_logged_in"]}</td></tr>
      </table>
    </div>
  </div>
</div>

<!-- DATA QUALITY -->
<div class="section">
  <h2>Data Quality</h2>
  <table>
    <tr><th>Check</th><th>Count</th><th>Threshold</th><th>Status</th></tr>
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Duplicate Record Sets</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb"><strong>{d["data_quality"]["duplicate_sets"]}</strong></td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#6b7280">&lt; 100</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{sev_badge("High" if d["data_quality"]["duplicate_sets"] >= 100 else "Pass")}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">Accounts Owned by Inactive Users</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb"><strong>{d["data_quality"]["inactive_owner_accounts"]}</strong></td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb;font-size:12px;color:#6b7280">&lt; 50</td>
      <td style="padding:10px 12px;border-bottom:1px solid #e5e7eb">{sev_badge("Medium" if d["data_quality"]["inactive_owner_accounts"] > 50 else "Pass")}</td>
    </tr>
    <tr>
      <td style="padding:10px 12px">Old Unconverted Leads (1+ year)</td>
      <td style="padding:10px 12px"><strong>{d["data_quality"]["old_unconverted_leads"]}</strong></td>
      <td style="padding:10px 12px;font-size:12px;color:#6b7280">&lt; 500</td>
      <td style="padding:10px 12px">{sev_badge("Medium" if d["data_quality"]["old_unconverted_leads"] > 500 else "Pass")}</td>
    </tr>
  </table>
</div>

<!-- SECURITY -->
<div class="section">
  <h2>Security — Org-Wide Defaults</h2>
  <div style="margin-bottom:16px">
    <strong style="color:{'#f97316' if d['security']['public_read_write_count'] >= 10 else '#22c55e'}">{d["security"]["public_read_write_count"]} object(s)</strong>
    <span style="font-size:13px;color:#6b7280"> with Public Read/Write sharing</span>
    {('<span style="margin-left:8px">' + sev_badge("Medium") + '</span>') if d["security"]["public_read_write_count"] >= 10 else ''}
  </div>
  <div style="max-height:300px;overflow-y:auto">
    <table>
      <tr><th>Object</th><th>Internal Sharing</th><th>External Sharing</th></tr>
      {owd_rows_html}
    </table>
  </div>
</div>

<!-- API LIMITS -->
<div class="section">
  <h2>API Limits</h2>
  <div style="display:flex;gap:24px;align-items:center;flex-wrap:wrap">
    <div>
      <div style="font-size:13px;color:#6b7280;margin-bottom:4px">Daily API Requests Used</div>
      <div style="font-size:28px;font-weight:700;color:{'#ef4444' if api_pct > 80 else '#1f2937'}">{api_pct}%</div>
      <div style="font-size:12px;color:#9ca3af">{api_used:,} of {api_max:,}</div>
    </div>
    <div style="flex:1;min-width:200px">
      <div style="background:#f3f4f6;border-radius:8px;height:12px;overflow:hidden">
        <div style="height:12px;width:{min(api_pct,100)}%;background:{'#ef4444' if api_pct > 80 else '#6366f1'};border-radius:8px;transition:width .3s"></div>
      </div>
      <div style="font-size:12px;color:#9ca3af;margin-top:4px">{api_rem:,} remaining today</div>
    </div>
  </div>
</div>

<!-- INTEGRATIONS -->
<div class="section">
  <h2>Integrations</h2>
  <div style="margin-bottom:16px">
    <strong style="font-size:13px">Connected Apps ({d["integrations"]["connected_apps"]})</strong>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">{app_tags if app_tags else '<span style="font-size:13px;color:#9ca3af">None</span>'}</div>
  </div>
  <div>
    <strong style="font-size:13px">Named Credentials ({d["integrations"]["named_credentials"]})</strong>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-top:8px">{nc_tags if nc_tags else '<span style="font-size:13px;color:#9ca3af">None</span>'}</div>
  </div>
</div>

{notes_section}

<footer>Generated {gen_date} &nbsp;·&nbsp; Salesforce Org Assessment</footer>

</div>

<script>
new Chart(document.getElementById('flowTypeChart'), {{
  type: 'doughnut',
  data: {{ labels: {ft_labels}, datasets: [{{ data: {ft_values}, backgroundColor: {ft_colors}, borderWidth: 0 }}] }},
  options: {{ plugins: {{ legend: {{ position: 'right', labels: {{ font: {{ size: 11 }} }} }} }}, cutout: '60%' }}
}});

new Chart(document.getElementById('flowStatusChart'), {{
  type: 'bar',
  data: {{
    labels: ['Active', 'Inactive/Draft'],
    datasets: [{{ data: [{d["automation"]["flows_active"]}, {d["automation"]["flows_inactive"]}], backgroundColor: ['#22c55e', '#d1d5db'], borderRadius: 6, borderWidth: 0 }}]
  }},
  options: {{ plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ beginAtZero: true, grid: {{ color: '#f3f4f6' }} }}, x: {{ grid: {{ display: false }} }} }} }}
}});

new Chart(document.getElementById('userChart'), {{
  type: 'doughnut',
  data: {{ labels: {ua_labels}, datasets: [{{ data: {ua_values}, backgroundColor: {ua_colors}, borderWidth: 0 }}] }},
  options: {{ plugins: {{ legend: {{ position: 'right', labels: {{ font: {{ size: 11 }} }} }} }}, cutout: '60%' }}
}});

new Chart(document.getElementById('omniChart'), {{
  type: 'bar',
  data: {{
    labels: {omni_labels},
    datasets: [
      {{ label: 'Active', data: {omni_active}, backgroundColor: '#22c55e', borderRadius: 4, borderWidth: 0 }},
      {{ label: 'Inactive', data: {omni_inactive}, backgroundColor: '#fca5a5', borderRadius: 4, borderWidth: 0 }}
    ]
  }},
  options: {{
    plugins: {{ legend: {{ position: 'top', labels: {{ font: {{ size: 11 }} }} }} }},
    scales: {{
      y: {{ beginAtZero: true, stacked: false, grid: {{ color: '#f3f4f6' }} }},
      x: {{ stacked: false, grid: {{ display: false }} }}
    }}
  }}
}});
</script>

</body>
</html>'''

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = parse_args()

    notes = args.notes
    if args.notes_file and os.path.isfile(args.notes_file):
        with open(args.notes_file) as f:
            notes = f.read()

    output = os.path.expanduser(args.output)
    os.makedirs(os.path.dirname(output) if os.path.dirname(output) else ".", exist_ok=True)

    if args.mock:
        print("Running in MOCK mode — no live org connection.")
        d = mock_data()
    else:
        print(f"Connecting to org: {args.org}")
        d = gather(args.org)

    print("Calculating health score...")
    health_score, findings = score(d)
    grade = letter_grade(health_score)

    critical = sum(1 for f in findings if f["severity"] == "Critical")
    high     = sum(1 for f in findings if f["severity"] == "High")
    medium   = sum(1 for f in findings if f["severity"] == "Medium")

    print(f"Health Score: {health_score}/100 ({grade}) — {critical} Critical, {high} High, {medium} Medium")

    print("Generating HTML report...")
    html = build_html(d, health_score, findings, notes, args.org)
    with open(output, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Report written to: {output}")

    # Write JSON summary alongside
    json_path = output.replace(".html", ".json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump({"health_score": health_score, "grade": grade, "findings": findings, "data": d}, f, indent=2)
    print(f"JSON data written to: {json_path}")


if __name__ == "__main__":
    main()
