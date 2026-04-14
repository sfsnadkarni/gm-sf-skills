---
name: sf-org-assessment-report
description: Generate a professional Salesforce org assessment HTML executive report with health scores, metadata inventory, license usage, critical findings, and strategic recommendations. Use when user wants to assess, audit, or health-check a Salesforce org and generate an executive report.
---

# Salesforce Org Assessment Report Generator

Generate a professional, slide-based HTML executive report for a Salesforce org assessment using the Salesforce MCP server. Slides are generated dynamically — include everything that can be queried, skip only if data is completely unavailable.

## When to Use
- User wants to generate a Salesforce org assessment report
- User wants an executive-ready technical assessment document
- User wants to health-check a Salesforce org and present findings
- Pre-sales, pre-go-live, or post-implementation reviews

---

## Step 1: Collect Inputs

Ask the user for ALL of the following in one single message:

1. **Company / Client Name** — e.g. "GM OnStar", "Finastra EntDev"
2. **Assessment Date** — default to today's date if not provided
3. **Strategic Context** — one line describing purpose (e.g. "Pre-go-live review", "Migration readiness", "License optimization")
4. **Output file path** — where to save the HTML file (e.g. ~/Desktop/org-assessment.html)

Store as: COMPANY_NAME, ASSESSMENT_DATE, STRATEGIC_CONTEXT, OUTPUT_PATH

---

## Step 2: Select Salesforce Org

Call MCP tool:

list_all_orgs


Parse the response and show the user a numbered list:

Authenticated Salesforce Orgs:

alias=myorg username=user@example.com type=sandbox
alias=devorg username=dev@example.com type=scratch
alias=prod username=admin@example.com type=production

Ask: "Enter the number of the org to use for the assessment:"

Store selected org username as SELECTED_ORG.

Confirm connection using MCP tool:

get_username
org: SELECTED_ORG


---

## Step 3: Pull ALL Org Data via MCP

Call `run_soql_query` for EVERY query below using SELECTED_ORG.
If any query fails → store 0 or "N/A", mark as UNAVAILABLE.
Never skip a slide because one query failed — use what you have.


--- APEX ---
run_soql_query:
query: "SELECT COUNT() FROM ApexClass WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: APEX_CLASSES

run_soql_query:
query: "SELECT COUNT() FROM ApexClass WHERE NamespacePrefix = null AND Name LIKE '%Test%'"
org: SELECTED_ORG
→ store: TEST_CLASSES

run_soql_query:
query: "SELECT COUNT() FROM ApexTrigger WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: APEX_TRIGGERS

run_soql_query:
query: "SELECT Name, ApiVersion, LengthWithoutComments FROM ApexClass WHERE NamespacePrefix = null ORDER BY LengthWithoutComments DESC LIMIT 10"
org: SELECTED_ORG
→ store: TOP_APEX_CLASSES

run_soql_query:
query: "SELECT MIN(ApiVersion) minVer, MAX(ApiVersion) maxVer FROM ApexClass WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: APEX_API_RANGE

run_soql_query:
query: "SELECT COUNT() FROM ApexClass WHERE ApiVersion < 50.0 AND NamespacePrefix = null"
org: SELECTED_ORG
→ store: APEX_OLD_API_COUNT

--- UI COMPONENTS ---
run_soql_query:
query: "SELECT COUNT() FROM LightningComponentBundle WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: LWC_COUNT

run_soql_query:
query: "SELECT COUNT() FROM AuraDefinitionBundle WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: AURA_COUNT

run_soql_query:
query: "SELECT COUNT() FROM ApexPage WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: VF_COUNT

run_soql_query:
query: "SELECT MIN(ApiVersion) minVer, MAX(ApiVersion) maxVer FROM ApexPage WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: VF_API_RANGE

run_soql_query:
query: "SELECT MIN(ApiVersion) minVer, MAX(ApiVersion) maxVer FROM AuraDefinitionBundle WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: AURA_API_RANGE

run_soql_query:
query: "SELECT MIN(ApiVersion) minVer, MAX(ApiVersion) maxVer FROM ApexTrigger WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: TRIGGER_API_RANGE

--- AUTOMATION ---
run_soql_query:
query: "SELECT COUNT() FROM Flow WHERE Status = 'Active'"
org: SELECTED_ORG
→ store: FLOW_COUNT

run_soql_query:
query: "SELECT COUNT() FROM WorkflowRule"
org: SELECTED_ORG
→ store: WFR_COUNT

--- SECURITY ---
run_soql_query:
query: "SELECT COUNT() FROM Profile"
org: SELECTED_ORG
→ store: PROFILE_COUNT

run_soql_query:
query: "SELECT COUNT() FROM PermissionSet WHERE IsOwnedByProfile = false"
org: SELECTED_ORG
→ store: PERMISSION_SET_COUNT

run_soql_query:
query: "SELECT COUNT() FROM User WHERE Profile.Name = 'System Administrator' AND IsActive = true"
org: SELECTED_ORG
→ store: SYS_ADMIN_COUNT

--- DATA MODEL ---
run_soql_query:
query: "SELECT COUNT() FROM CustomObject WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: CUSTOM_OBJECT_COUNT

run_soql_query:
query: "SELECT COUNT() FROM CustomField WHERE NamespacePrefix = null"
org: SELECTED_ORG
→ store: CUSTOM_FIELD_COUNT

run_soql_query:
query: "SELECT EntityDefinition.QualifiedApiName, COUNT(Id) fieldCount FROM FieldDefinition WHERE EntityDefinition.NamespacePrefix = null GROUP BY EntityDefinition.QualifiedApiName HAVING COUNT(Id) > 100 ORDER BY COUNT(Id) DESC LIMIT 20"
org: SELECTED_ORG
→ store: COMPLEX_OBJECTS

--- INTEGRATION ---
run_soql_query:
query: "SELECT COUNT() FROM ConnectedApplication"
org: SELECTED_ORG
→ store: CONNECTED_APP_COUNT

--- REPORTS & DASHBOARDS ---
run_soql_query:
query: "SELECT COUNT() FROM Report"
org: SELECTED_ORG
→ store: REPORT_COUNT

run_soql_query:
query: "SELECT COUNT() FROM Dashboard"
org: SELECTED_ORG
→ store: DASHBOARD_COUNT

--- USERS & ADOPTION ---
run_soql_query:
query: "SELECT COUNT() FROM User WHERE IsActive = true"
org: SELECTED_ORG
→ store: TOTAL_USERS

run_soql_query:
query: "SELECT COUNT() FROM User WHERE LastLoginDate >= LAST_N_DAYS:30 AND IsActive = true"
org: SELECTED_ORG
→ store: ACTIVE_USERS_30D

--- LICENSES ---
run_soql_query:
query: "SELECT Name, TotalLicenses, UsedLicenses, Status FROM UserLicense ORDER BY Name"
org: SELECTED_ORG
→ store: USER_LICENSES

run_soql_query:
query: "SELECT MasterLabel, TotalLicenses, UsedLicenses, ExpirationDate FROM PermissionSetLicense ORDER BY MasterLabel"
org: SELECTED_ORG
→ store: PSET_LICENSES

--- PACKAGES ---
run_soql_query:
query: "SELECT SubscriberPackage.Name, SubscriberPackage.NamespacePrefix, InstalledVersion.MajorVersion, InstalledVersion.MinorVersion FROM InstalledSubscriberPackage ORDER BY SubscriberPackage.Name"
org: SELECTED_ORG
→ store: INSTALLED_PACKAGES

--- STORAGE ---
run_soql_query:
query: "SELECT StorageUsed, StorageLimit FROM Organization"
org: SELECTED_ORG
→ store: STORAGE_INFO


Now call these additional MCP tools for enhanced analysis:


--- APEX CODE QUALITY ---
scan_apex_class_for_antipatterns
org: SELECTED_ORG
→ store: APEX_ANTIPATTERNS

run_code_analyzer
org: SELECTED_ORG
→ store: CODE_ANALYSIS

query_code_analyzer_results
org: SELECTED_ORG
→ store: CODE_ISSUES

score_issues
org: SELECTED_ORG
→ store: ISSUE_SCORES

--- METADATA ---
retrieve_metadata
org: SELECTED_ORG
metadata: InstalledPackage
→ store: PACKAGE_METADATA


---

## Step 4: Calculate Health Scores

### Security Score (weight: 20%)

Base = 100
Profile penalty: -1 per profile over 20 (max -80)
Sys Admin penalty: -1 per admin over 10 (max -40)
Permission Set bonus: +0.1 per 100 sets (max +30)
Security Score = max(0, Base - profile_penalty - admin_penalty + pset_bonus)


### Modernization Score (weight: 20%)

Total UI = LWC_COUNT + AURA_COUNT + VF_COUNT
Modern Ratio = (LWC_COUNT + AURA_COUNT) / Total UI * 100
Modernization Score = min(100, Modern Ratio)


### Automation Score (weight: 20%)

Base = 100
WFR penalty: -1 per workflow rule (max -50)
Flow bonus: +0.2 per active flow (max +30)
Automation Score = max(0, Base - wfr_penalty + flow_bonus)


### Data Model Score (weight: 15%)

Base = 100
Objects > 100 fields penalty: -1.5 per object (max -50)
Data Model Score = max(0, Base - complexity_penalty)


### Integration Score (weight: 15%)

Base = 100
Connected App penalty: -0.5 per app over 50 (max -50)
Integration Score = max(0, Base - app_penalty)


### Adoption Score (weight: 10%)

Active Rate = ACTIVE_USERS_30D / TOTAL_USERS * 100
Adoption Score = min(100, Active Rate * 2)


### Overall Score

Weighted = (Security0.20) + (Modernization0.20) + (Automation0.20) +
(DataModel0.15) + (Integration0.15) + (Adoption0.10)

Critical Adjustments:
Storage > 90%: -2 points
Adoption < 10%: -3 points
WFR > 20: -2 points
CODE_ISSUES critical count > 10: -2 points

OVERALL_SCORE = round(Weighted + adjustments)


### Rating

= 80: "Strong Readiness" (green)
60-79: "Good Readiness" (blue)
40-59: "Moderate Readiness" (yellow)
< 40: "Needs Attention" (red)


---

## Step 5: Identify Critical Findings

Build FINDINGS list:

| # | Finding | Condition | Severity |
|---|---------|-----------|----------|
| 1 | Workflow Rules | WFR > 20: CRITICAL, WFR > 0: HIGH | |
| 2 | Visualforce UI | VF > 100: HIGH, VF > 0: MODERATE | |
| 3 | Profile Sprawl | PROFILES > 50: CRITICAL, > 20: HIGH | |
| 4 | Low Adoption | Active rate < 10%: CRITICAL, < 30%: HIGH | |
| 5 | Object Complexity | Objects with > 100 fields exist: HIGH | |
| 6 | System Administrators | ADMINS > 20: CRITICAL, > 10: HIGH | |
| 7 | API Compliance | Classes on API < v50 > 20%: HIGH | |
| 8 | Large Codebase | APEX > 3000: HIGH, > 1000: MODERATE | |
| 9 | Integration Complexity | APPS > 100: HIGH, > 50: MODERATE | |
| 10 | Storage Capacity | Storage > 90%: CRITICAL, > 75%: HIGH | |
| 11 | Code Antipatterns | From scan_apex_class_for_antipatterns results | |
| 12 | Code Quality Issues | From run_code_analyzer results | |

---

## Step 6: Generate HTML Report

Write and execute a Python script to generate the complete HTML file.

### Design System

Font: Inter (Google Fonts CDN)
CSS: Tailwind CSS (CDN)
Primary: blue-600 to blue-800
Nav buttons: #1976d2
Slide backgrounds: alternating white / gray-50
Cards: white, rounded-lg, shadow-sm, p-6, mb-6
Status colors:
CRITICAL → red (bg-red-50, border-red-600, text-red-700)
HIGH → orange (bg-orange-50, border-orange-600, text-orange-700)
MODERATE → yellow (bg-yellow-50, border-yellow-600, text-yellow-700)
GOOD → green (bg-green-50, border-green-600, text-green-700)
INFO → blue (bg-blue-50, border-blue-600, text-blue-700)


### HTML Shell
```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>[COMPANY_NAME] - Salesforce Org Assessment</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        body { font-family: 'Inter', sans-serif; margin: 0; padding: 0; overflow-x: hidden; }
        .slide { min-height: 100vh; width: 100vw; display: flex; flex-direction: column; padding: 4rem 2rem; box-sizing: border-box; scroll-snap-align: start; }
        .slide-container { max-width: 1200px; margin: 0 auto; width: 100%; }
        html { scroll-snap-type: y mandatory; scroll-behavior: smooth; }
        .slide-nav { position: fixed; bottom: 1rem; right: 0.5rem; z-index: 1000; display: flex; gap: 1rem; align-items: center; }
        @media print { .slide-nav { display: none !important; } }
        .nav-btn { padding: 0.75rem 1.5rem; background: #1976d2; color: white; border: none; border-radius: 0.5rem; cursor: pointer; font-weight: 600; transition: all 0.3s; }
        .nav-btn:hover { background: #1565c0; transform: translateY(-2px); }
        .nav-btn:disabled { background: #94a3b8; cursor: not-allowed; transform: none; }
        .card { background: white; border-radius: 0.5rem; box-shadow: 0 1px 3px rgba(0,0,0,0.1); padding: 1.5rem; margin-bottom: 1.5rem; }
    </style>
</head>
<body class="bg-gray-50">
    <div class="slide-nav">
        <button class="nav-btn" id="prevBtn" onclick="previousSlide()">← Previous</button>
        <span class="px-4 py-2 bg-white rounded shadow text-sm font-medium" id="slideCounter">1 / 1</span>
        <button class="nav-btn" id="nextBtn" onclick="nextSlide()">Next →</button>
    </div>
    [ALL SLIDES]
    <script>
        const slides = document.querySelectorAll('.slide');
        let current = 0;
        function updateNav() {
            document.getElementById('slideCounter').textContent = `${current + 1} / ${slides.length}`;
            document.getElementById('prevBtn').disabled = current === 0;
            document.getElementById('nextBtn').disabled = current === slides.length - 1;
        }
        function nextSlide() {
            if (current < slides.length - 1) {
                current++;
                slides[current].scrollIntoView({behavior:'smooth'});
                updateNav();
            }
        }
        function previousSlide() {
            if (current > 0) {
                current--;
                slides[current].scrollIntoView({behavior:'smooth'});
                updateNav();
            }
        }
        document.addEventListener('keydown', e => {
            if (e.key === 'ArrowDown' || e.key === 'ArrowRight') nextSlide();
            if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') previousSlide();
        });
        updateNav();
    </script>
</body>
</html>

SVG Circle Formula
radius = 80, circumference = 503
stroke-dashoffset = 503 * (1 - SCORE/100)
Color: >=80 → #16a34a, 60-79 → #2563eb, 40-59 → #ca8a04, <40 → #dc2626

Step 7: Slide Definitions
Generate ALL slides. Skip ONLY if ALL required data is UNAVAILABLE.
If partial data exists → generate slide, note gaps inline.

SLIDE 1 — Title (ALWAYS)
Background: bg-gradient-to-br from-blue-600 to-blue-800 text-white

H1: COMPANY_NAME (text-5xl font-bold)
H2: "Salesforce Org Assessment Report"
SVG circular progress: OVERALL_SCORE with rating label + colored dot
Assessment Date | Strategic Context | Methodology: "Salesforce MCP Metadata Analysis"
SLIDE 2 — Executive Summary (ALWAYS)
Background: white

Key metrics grid (10-12 cards): SYS_ADMIN_COUNT, CRITICAL findings count, PROFILE_COUNT, WFR_COUNT, LWC_COUNT, VF_COUNT, APEX_CLASSES, CONNECTED_APP_COUNT, FLOW_COUNT, TOTAL_USERS, ACTIVE_USERS_30D, CUSTOM_OBJECTS
Each card: large bold number + label + severity sub-label (color-coded)
Strategic alignment note: blue left-border box at bottom
SLIDE 3 — Overall Readiness Score (ALWAYS)
Background: gray-50

Large SVG circle: OVERALL_SCORE
6-box component grid: Security | Modernization | Automation | Data Model | Integration | Adoption
Each box: score + weight % + color
Score calculation methodology (two-column)
Key assumptions per component
SLIDE 4 — Complete Metadata Inventory (ALWAYS)
Background: white

Table: Component Type | Count | Status
Rows: Apex Classes, Test Classes, Apex Triggers, Custom Objects, Custom Fields, LWC, Aura, Visualforce, Active Flows, Workflow Rules, Profiles, Permission Sets, System Admins, Connected Apps, Reports, Dashboards, Total Users, Active Users (30d), Installed Packages
Status badge per row vs benchmark
Bold footer: TOTAL COMPONENTS
SLIDE 5 — Adoption & License Usage (skip only if USER_LICENSES completely unavailable)
Background: gray-50

Full license table: LICENSE CATEGORY | LICENSE TYPE | PROVISIONED | ACTIVATED | USED | EU* | LA* | STATUS
EU* = Used/Provisioned * 100
LA* = Used/Activated * 100
Status: >=80% EU → Good (green), >=50% → Moderate (yellow), >=20% → High (orange), <20% → CRITICAL (red), 0% → CRITICAL (red)
Footer note: "EU* = Effective Usage | LA* = License Activation"
Critical Gap Analysis (2-column grid):
🔴 0% usage licenses
⚠️ Under 20% usage
✅ Well-utilized (>80%)
Storage capacity status
SLIDE 6 — Critical Findings Overview (ALWAYS if any findings exist)
Background: white

2-column grid of finding cards
Each card: colored left border + severity emoji + title + count/detail + recommended action
Order: CRITICAL → HIGH → MODERATE
SLIDE 7 — Critical Focus Areas → Strategic Impact (ALWAYS if findings exist)
Background: gray-50

Table: Critical Focus Area | Current State | Barrier to Goals | Strategic Impact | Priority
One row per finding with colored priority badge
SLIDE 8 — Critical Finding: Workflow Rules (skip if WFR = 0)
Background: gray-50

Red left-border card
WFR_COUNT, Salesforce deprecation deadline
Business Impact | Recommended Actions (2-column)
Blue box: Strategic Value + Timeline
SLIDE 9 — Critical Finding: Visualforce UI (skip if VF = 0)
Background: gray-50

Orange left-border card
VF_COUNT, % of total UI, 3-5x performance penalty vs LWC
Business Impact | Migration Strategy (2-column)
Blue box: Strategic Value + Timeline
SLIDE 10 — Critical Finding: Profile Sprawl (skip if PROFILES <= 20)
Background: white

Left-border card: red if >50, orange if 20-50
PROFILE_COUNT vs target (<20), multiplier
Business Impact | Consolidation Strategy (2-column)
Blue box: Strategic Value + Timeline
SLIDE 11 — Critical Finding: Low Adoption (skip if active rate >= 50%)
Background: gray-50

Left-border card: red if <10%, orange if 10-30%
ACTIVE_USERS_30D / TOTAL_USERS, active rate %
Business Impact | Improvement Strategy (2-column)
Blue box: Strategic Value + Timeline
SLIDE 12 — Critical Finding: Object Complexity (skip if COMPLEX_OBJECTS empty)
Background: white

Orange left-border card
Count of objects > 100 fields
Top 5 most complex objects with field counts (from COMPLEX_OBJECTS)
Business Impact | Recommended Actions (2-column)
Blue box: Strategic Value + Timeline
SLIDE 13 — Critical Finding: System Administrators (skip if ADMINS <= 10)
Background: gray-50

Left-border card: red if >20, orange if 10-20
SYS_ADMIN_COUNT vs target (<10)
Security Risk | Remediation Steps (2-column)
Blue box: Strategic Value + Timeline
SLIDE 14 — Critical Finding: API Version Compliance (skip if data unavailable)
Background: white

Yellow left-border card
% of classes on API < v50.0
Current version range vs recommended (latest)
Recommended actions + effort estimate
SLIDE 15 — Comprehensive Apex Code Analysis (skip if APEX_CLASSES = 0)
Background: gray-50

4 metric cards: Apex Classes | Apex Triggers | Test Classes | API Version Range
3 finding cards from scan_apex_class_for_antipatterns + run_code_analyzer results:
API Version Fragmentation
Large Codebase
Code Antipatterns (real findings from MCP)
Table: Top 10 largest Apex classes from TOP_APEX_CLASSES (name, API version, size, status)
SLIDE 16 — API Version Compliance Detail (skip if data unavailable)
Background: white

Table: Component Type | API Version Range | % on API < v50 | Compliance Status
Rows: Apex Classes, Apex Triggers, Visualforce, Aura, LWC
Use APEX_API_RANGE, TRIGGER_API_RANGE, VF_API_RANGE, AURA_API_RANGE
Overall compliance score + recommendation
SLIDE 17 — Code Quality Analysis (skip if CODE_ANALYSIS unavailable)
Background: white

Results from run_code_analyzer and score_issues
Two-column: Identified Issues | Severity Breakdown
Top violations list with rule names and counts
Refactoring priorities: Monolithic (>5K lines), Large (1K-5K), Standard (<1K)
Source: Salesforce Code Analyzer via MCP
SLIDE 18 — Managed Package Ecosystem (skip if PACKAGES = 0)
Background: white

Total package count from INSTALLED_PACKAGES
Grid of packages grouped by category/namespace
Risk flags: overlapping functionality, consolidation candidates
SLIDE 19 — Integration Complexity (skip if CONNECTED_APPS = 0)
Background: gray-50

CONNECTED_APP_COUNT vs recommended (<50)
Integration risk level
Consolidation opportunities
Recommendations: inventory, testing framework, phased approach
SLIDE 20 — Current State & Gap Analysis (ALWAYS)
Background: white

Table: Domain | Observed State | Industry Benchmark | Gap Analysis
Rows: Platform Health | User Experience | Adoption | Security Posture | Data Model | Automation | Integration
Color-coded Gap column: red (critical), orange (high), green (on track)
Summary: Critical Gaps count | High Priority Gaps count
SLIDE 21 — Emerging Hypotheses (ALWAYS — AI-generated from data patterns)
Background: gray-50

2x2 grid: 👥 PEOPLE | 🔄 PROCESS | ⚙️ TECHNOLOGY | 📊 DATA
2 hypotheses per quadrant based on actual data
Each: Signal (from data) + Root Cause + → Initiative
Priority dots: red (critical), yellow (high), blue (medium)
SLIDE 22 — Technical Symptoms → Strategic Impact (ALWAYS)
Background: white

Table: Technical Symptom | Data Signal | Risk/Barrier | Strategic Impact | Priority
Map each finding to business/strategic impact
All findings from Step 5
SLIDE 23 — Assessment → Strategic Goals Mapping (ALWAYS)
Background: gray-50

Map findings to strategic objectives
Left: Assessment Finding | Right: Strategic Goal impacted
Color by alignment strength
SLIDE 24 — Strategic Timeline (ALWAYS)
Background: white

3-horizon timeline: M0 (Now) → M1 (Short Term) → M2 (Medium) → M3 (Long Term)
Horizon cards: H1 Immediate | H2 Optimization | H3 Innovation/AI
Key milestones per horizon based on actual findings
SLIDE 25 — Strategic Direction Recommendations (ALWAYS)
Background: gray-50

4-card grid (2x2)
Each card: colored left border + title + rationale + actions + strategic value
Generated from actual findings
SLIDE 26 — Next Steps (ALWAYS)
Background: white

4-card grid:
🔴 Immediate (0-30 days)
⚠️ Short-term (1-3 months)
✅ Medium-term (3-6 months)
📋 Governance & Foundation
Specific actions derived from actual findings
Each action: bold title + description
SLIDE 27 — Success Metrics (ALWAYS)
Background: gray-50

Table: Metric | Current State | Target | Timeline
Generate targets from benchmarks vs actual:
Profile count → <20
Workflow Rules → 0
Adoption rate → >80%
API compliance → 100%
System Admins → <10
Modernization ratio → >80%
SLIDE 28 — Roadmap Gantt Chart (ALWAYS)
Background: white

Horizontal bar chart: workstreams over M0-M12
One bar per initiative (color-coded by priority)
Show only workstreams relevant to actual findings:
Security Hardening
Automation Migration (if WFR > 0)
UI Modernization (if VF > 0)
License Optimization (if unused licenses found)
Integration Inventory (if APPS > 50)
AI Enablement
Adoption Improvement (if rate < 50%)
SLIDE 29 — Financial Impact Analysis (ALWAYS)
Background: gray-50

Table: Initiative | Est. Cost | Est. Annual Savings | ROI | Timeline
Generate estimates from findings:
WFR migration: WFR_COUNT * 8-12 hours * $150/hr
VF modernization: VF_COUNT * 4-8 hours * $150/hr
Profile consolidation: PROFILE_COUNT * 3-5 hours * $150/hr
License waste: unused license counts * avg license cost
Total investment vs total savings
Note: estimates are indicative, require detailed scoping
SLIDE 30 — Key Assumptions (ALWAYS)
Background: white

Bulleted list:
Benchmark sources (Salesforce Well-Architected Framework)
Scoring methodology explanation
Effort rate assumptions ($150/hr blended rate)
Data collection date and org
Limitations: metadata-only analysis via Salesforce MCP
License cost assumptions
SLIDE 31 — Appendix: Package Inventory (skip if PACKAGES = 0)
Background: gray-50

Full table: Package Name | Namespace | Version | Category
Grouped by functional category
SLIDE 32 — Appendix: Full License Data (skip if USER_LICENSES unavailable)
Background: white

Complete USER_LICENSES table with all columns
Complete PSET_LICENSES table
All license types including zero-usage ones
SLIDE 33 — Thank You (ALWAYS — last slide)
Background: bg-gradient-to-br from-blue-600 to-blue-800 text-white

"Thank You" centered (text-6xl font-bold)
COMPANY_NAME
Assessment Date
"Prepared using Salesforce MCP"
Questions/contact placeholder
Step 8: Save & Confirm
Save HTML to OUTPUT_PATH.

Tell the user:

✅ Assessment report generated!

📄 File: OUTPUT_PATH
📊 Slides generated: [count]
🏆 Overall Score: OVERALL_SCORE/100 — [RATING]

Findings:
  🔴 Critical: X
  ⚠️  High: X
  📋 Moderate: X

Slides skipped (data unavailable): [list if any]

Data sources:
  ✅ SOQL queries via Salesforce MCP
  ✅ Apex antipattern scan via MCP
  ✅ Code analyzer via MCP

Open in any browser. Arrow keys or Previous/Next to navigate.
