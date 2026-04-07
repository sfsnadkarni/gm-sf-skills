#!/usr/bin/env python3
"""
GM Salesforce Skills — standalone CLI runner.

No Claude Code required. Run this directly:

  python3 run.py sf-translation Vehicle
  python3 run.py sf-translation-v2 Vehicle
  python3 run.py sf-translation-verify Vehicle
  python3 run.py sf-org-assessment

Usage:
  python3 run.py <skill> [object]
  python3 run.py --list
"""
import json
import os
import subprocess
import sys

# ── Paths ─────────────────────────────────────────────────────────────────────
ROOT = os.path.dirname(os.path.abspath(__file__))

SCRIPTS = {
    "sf-translation":        os.path.join(ROOT, "scripts"),
    "sf-translation-v2":     os.path.join(ROOT, "sf-translation-v2", "scripts"),
    "sf-translation-verify": os.path.join(ROOT, "sf-translation-verify", "scripts"),
    "sf-org-assessment":     os.path.join(ROOT, "sf-org-assessment", "scripts"),
}

DEFAULT_OUTPUT = os.path.expanduser("~/Desktop/sf-translation-output")


# ── Helpers ───────────────────────────────────────────────────────────────────

def hr(char="─", width=65):
    print(char * width)


def header(title):
    print()
    hr("═")
    print(f"  {title}")
    hr("═")
    print()


def step(n, title):
    print()
    hr()
    print(f"  Step {n}: {title}")
    hr()
    print()


def ask(prompt, default=""):
    suffix = f" [{default}]" if default else ""
    val = input(f"  {prompt}{suffix}: ").strip()
    return val or default


def ask_optional(prompt):
    val = input(f"  {prompt} (press Enter to skip): ").strip()
    return val


def run_script(script_path, args, label=""):
    """Run a Python script, print output, return parsed JSON from last line."""
    cmd = [sys.executable, script_path] + args
    label_str = f"  Running {label or os.path.basename(script_path)}..."
    print(label_str)

    result = subprocess.run(cmd, capture_output=True, text=True)

    # Print non-JSON stderr (warnings, progress lines)
    if result.stderr.strip():
        for line in result.stderr.strip().splitlines():
            print(f"    {line}")

    # Print stdout lines that are not pure JSON
    output_lines = result.stdout.strip().splitlines()
    json_result = None
    for line in output_lines:
        stripped = line.strip()
        if stripped.startswith("{") or stripped.startswith("["):
            try:
                json_result = json.loads("\n".join(
                    l for l in output_lines if l.strip().startswith(("{", "[", "}", "]", '"', " "))
                ))
                break
            except Exception:
                pass
        else:
            print(f"    {line}")

    if result.returncode != 0:
        print(f"\n  ERROR: {label or os.path.basename(script_path)} failed.")
        if result.stderr:
            print(f"  {result.stderr.strip()}")
        sys.exit(1)

    return json_result


def run_script_streaming(script_path, args, label=""):
    """Run a script and stream output live (for long-running steps)."""
    cmd = [sys.executable, script_path] + args
    print(f"  Running {label or os.path.basename(script_path)}...")
    result = subprocess.run(cmd, text=True)
    if result.returncode != 0:
        print(f"\n  ERROR: {label or os.path.basename(script_path)} failed.")
        sys.exit(1)


def check_file(path, label):
    """Verify a file path exists."""
    expanded = os.path.expanduser(path)
    if not os.path.isfile(expanded):
        print(f"\n  ERROR: {label} not found: {expanded}")
        sys.exit(1)
    return expanded


def list_orgs(scripts_dir):
    """Run org_connect.py and return list of orgs."""
    result = subprocess.run(
        [sys.executable, os.path.join(scripts_dir, "org_connect.py")],
        capture_output=True, text=True
    )
    try:
        data = json.loads(result.stdout)
        return data.get("orgs", [])
    except Exception:
        return []


def select_org(scripts_dir):
    """Show org list and return selected org alias/username."""
    orgs = list_orgs(scripts_dir)

    if not orgs:
        print("  No authenticated Salesforce orgs found.")
        print("  Run: sf org login web")
        sys.exit(1)

    print("  Authenticated Salesforce orgs:")
    print()
    for i, org in enumerate(orgs, 1):
        alias    = org.get("alias", "")
        username = org.get("username", "")
        status   = org.get("connectedStatus", "")
        display  = f"{alias}  ({username})" if alias else username
        print(f"    {i}. {display}  —  {status}")
    print(f"    0. Connect a new org")
    print()

    while True:
        choice = ask("Enter number").strip()
        if choice == "0":
            subprocess.run(["sf", "org", "login", "web"])
            orgs = list_orgs(scripts_dir)
            for i, org in enumerate(orgs, 1):
                alias    = org.get("alias", "")
                username = org.get("username", "")
                display  = f"{alias}  ({username})" if alias else username
                print(f"    {i}. {display}")
            continue
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(orgs):
                org = orgs[idx]
                selected = org.get("alias") or org.get("username")
                print(f"\n  Selected: {selected}")
                return selected
        except ValueError:
            pass
        print("  Invalid choice. Try again.")


# ── Skills ────────────────────────────────────────────────────────────────────

def skill_sf_translation(object_name, scripts_dir):
    header(f"SF Translation — {object_name}")

    # Step 1: Select org
    step(1, "Select Salesforce Org")
    org = select_org(scripts_dir)

    # Step 2: Collect paths
    step(2, "File Paths")
    master_path = ask("Master Excel Sheet path")
    master_path = check_file(master_path, "Master Excel Sheet")

    output_dir = ask("Output directory", DEFAULT_OUTPUT)
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    existing_es = ask_optional("Existing Spanish bilingual STF path")
    if existing_es:
        existing_es = check_file(existing_es, "Spanish STF")

    existing_pt = ask_optional("Existing Portuguese bilingual STF path")
    if existing_pt:
        existing_pt = check_file(existing_pt, "Portuguese STF")

    # Step 3: Extract fields
    step(3, "Extract Fields from Salesforce")
    run_script(
        os.path.join(scripts_dir, "extract_fields.py"),
        ["--org", org, "--object", object_name, "--output", output_dir],
        "extract_fields"
    )
    intermediate = os.path.join(output_dir, f"{object_name}_intermediate.xlsx")

    # Step 4: Match master
    step(4, "Match Against Master Sheet")
    matches_file = os.path.join(output_dir, f"{object_name}_matches.json")
    run_script(
        os.path.join(scripts_dir, "compare_master.py"),
        ["--intermediate", intermediate, "--master", master_path, "--output", matches_file],
        "compare_master"
    )

    # Step 5: Generate STF
    step(5, "Generate STF Files")
    stf_args = ["--matches", matches_file, "--object", object_name, "--output", output_dir]
    if existing_es:
        stf_args += ["--existing-es", existing_es]
    if existing_pt:
        stf_args += ["--existing-pt", existing_pt]
    run_script(os.path.join(scripts_dir, "generate_stf.py"), stf_args, "generate_stf")

    # Step 6: Miss report
    step(6, "Generate Miss Report")
    run_script(
        os.path.join(scripts_dir, "miss_report.py"),
        ["--matches", matches_file, "--object", object_name, "--output", output_dir],
        "miss_report"
    )

    # Summary
    header("Done")
    print(f"  Output files in: {output_dir}")
    print()
    print(f"    {object_name}_intermediate.xlsx  — field/picklist inventory")
    print(f"    {object_name}_es.stf             — Spanish translations")
    print(f"    {object_name}_pt_BR.stf           — Portuguese translations")
    print(f"    {object_name}_miss_report.csv     — fields with no translation")
    print()


def skill_sf_translation_v2(object_name, scripts_dir):
    header(f"SF Translation v2 — {object_name}")

    # Step 1: Select org
    step(1, "Select Salesforce Org")
    org = select_org(scripts_dir)

    # Step 2: Collect paths
    step(2, "File Paths")
    master_path = ask("Master Excel Sheet path")
    master_path = check_file(master_path, "Master Excel Sheet")

    output_dir = ask("Output directory", DEFAULT_OUTPUT)
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    existing_es = ask_optional("Existing Spanish bilingual STF path")
    if existing_es:
        existing_es = check_file(existing_es, "Spanish STF")

    existing_pt = ask_optional("Existing Portuguese bilingual STF path")
    if existing_pt:
        existing_pt = check_file(existing_pt, "Portuguese STF")

    repo_path = ask_optional("Local Salesforce repo path (for LRP tab/label translations)")
    if repo_path:
        repo_path = os.path.expanduser(repo_path)
        if not os.path.isdir(repo_path):
            print(f"  WARNING: Repo path not found: {repo_path} — skipping LRP")
            repo_path = ""

    # Step 3: Extract fields
    step(3, "Extract Fields from Salesforce")
    run_script(
        os.path.join(scripts_dir, "extract_fields.py"),
        ["--org", org, "--object", object_name, "--output", output_dir],
        "extract_fields"
    )
    intermediate = os.path.join(output_dir, f"{object_name}_intermediate.xlsx")

    # Step 4: Match master
    step(4, "Match Against Master Sheet")
    matches_file = os.path.join(output_dir, f"{object_name}_matches.json")
    run_script(
        os.path.join(scripts_dir, "compare_master.py"),
        ["--intermediate", intermediate, "--master", master_path, "--output", matches_file],
        "compare_master"
    )

    # Step 5: Generate STF
    step(5, "Generate Field/Picklist STF Files")
    stf_args = ["--matches", matches_file, "--object", object_name, "--output", output_dir]
    if existing_es:
        stf_args += ["--existing-es", existing_es]
    if existing_pt:
        stf_args += ["--existing-pt", existing_pt]
    run_script(os.path.join(scripts_dir, "generate_stf.py"), stf_args, "generate_stf")

    # Step 6: Miss report
    step(6, "Generate Field/Picklist Miss Report")
    run_script(
        os.path.join(scripts_dir, "miss_report.py"),
        ["--matches", matches_file, "--object", object_name, "--output", output_dir],
        "miss_report"
    )

    # Steps 7-9: LRP (if repo provided)
    flexipage_path = ""
    if repo_path:
        step(7, "Find Lightning Record Page (LRP)")
        matches = []
        for dirpath, _, filenames in os.walk(repo_path):
            for fname in filenames:
                if fname.endswith(".flexipage-meta.xml") and object_name.lower() in fname.lower():
                    matches.append(os.path.join(dirpath, fname))

        if not matches:
            print(f"  No flexipage found matching '{object_name}' in repo — skipping LRP")
        else:
            if len(matches) == 1:
                flexipage_path = matches[0]
                print(f"  Found: {os.path.basename(flexipage_path)}")
                confirm = ask("Use this flexipage? (y/n)", "y")
                if confirm.lower() != "y":
                    flexipage_path = ""
            else:
                print("  Multiple flexipages found:")
                for i, m in enumerate(matches, 1):
                    print(f"    {i}. {os.path.relpath(m, repo_path)}")
                while True:
                    choice = ask("Enter number (0 to skip LRP)", "0")
                    if choice == "0":
                        break
                    try:
                        idx = int(choice) - 1
                        if 0 <= idx < len(matches):
                            flexipage_path = matches[idx]
                            break
                    except ValueError:
                        pass
                    print("  Invalid choice.")

        if flexipage_path:
            step(8, "Extract LRP Label Data")
            lrp_args = [
                "--flexipage", flexipage_path,
                "--org", org,
                "--master", master_path,
                "--object", object_name,
                "--output", output_dir,
            ]
            if existing_es:
                lrp_args += ["--existing-es", existing_es]
            if existing_pt:
                lrp_args += ["--existing-pt", existing_pt]
            lrp_result = run_script(
                os.path.join(scripts_dir, "extract_lrp.py"), lrp_args, "extract_lrp"
            )

            step(9, "Generate Custom Label STF Files")
            lrp_matches = os.path.join(output_dir, f"{object_name}_lrp_matches.json")
            label_result = run_script(
                os.path.join(scripts_dir, "generate_labels_stf.py"),
                ["--lrp-matches", lrp_matches, "--object", object_name, "--output", output_dir],
                "generate_labels_stf"
            )

            # Warn if new custom labels XML was generated
            if label_result and label_result.get("files", {}).get("new_custom_labels_xml"):
                xml_file = label_result["files"]["new_custom_labels_xml"]
                print()
                print("  ┌─────────────────────────────────────────────────────────┐")
                print("  │  ACTION REQUIRED before importing the label STF:        │")
                print("  │                                                         │")
                print(f"  │  1. Deploy: {os.path.basename(xml_file):<44}│")
                print("  │     sf project deploy start --source-dir <path>        │")
                print("  │  2. Update the LRP to use {!$Label.ApiName}            │")
                print("  │  3. Then import the STF into Translation Workbench      │")
                print("  └─────────────────────────────────────────────────────────┘")

    # Summary
    header("Done")
    print(f"  Output files in: {output_dir}")
    print()
    print("  Custom Fields & Picklists:")
    print(f"    {object_name}_intermediate.xlsx  — field/picklist inventory")
    print(f"    {object_name}_es.stf             — Spanish translations")
    print(f"    {object_name}_pt_BR.stf           — Portuguese translations")
    print(f"    {object_name}_miss_report.csv     — fields with no translation")
    if flexipage_path:
        print()
        print("  Lightning Record Page Labels:")
        print(f"    {object_name}_labels_es.stf          — Spanish custom label translations")
        print(f"    {object_name}_labels_pt_BR.stf        — Portuguese custom label translations")
        print(f"    {object_name}_lrp_miss_report.csv     — LRP labels with no translation")
        new_xml = os.path.join(output_dir, f"{object_name}_new_custom_labels.labels-meta.xml")
        if os.path.isfile(new_xml):
            print(f"    {object_name}_new_custom_labels.labels-meta.xml  — deploy before importing STF")
    print()


def skill_sf_translation_verify(object_name, scripts_dir):
    header(f"SF Translation Verify — {object_name}")

    step(1, "File Paths")
    master_path = ask("Master Excel Sheet path")
    master_path = check_file(master_path, "Master Excel Sheet")

    output_dir = ask("Output directory", DEFAULT_OUTPUT)
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    bilingual_es = ask_optional("Spanish Bilingual STF path (downloaded from org)")
    if bilingual_es:
        bilingual_es = check_file(bilingual_es, "Spanish Bilingual STF")

    bilingual_pt = ask_optional("Portuguese Bilingual STF path (downloaded from org)")
    if bilingual_pt:
        bilingual_pt = check_file(bilingual_pt, "Portuguese Bilingual STF")

    if not bilingual_es and not bilingual_pt:
        print()
        print("  ERROR: At least one bilingual STF is required.")
        print("  Download it from Salesforce: Setup → Translation Workbench → Export")
        sys.exit(1)

    step(2, "Run Verification")
    verify_args = ["--object", object_name, "--master", master_path, "--output", output_dir]
    if bilingual_es:
        verify_args += ["--bilingual-es", bilingual_es]
    if bilingual_pt:
        verify_args += ["--bilingual-pt", bilingual_pt]

    run_script(
        os.path.join(scripts_dir, "verify_translations.py"),
        verify_args,
        "verify_translations"
    )

    header("Done")
    print(f"  Verification Excel: {output_dir}/{object_name}_verification.xlsx")
    print()
    print("  Open it and filter the Match column:")
    print("    ✓  Match        — translation in org matches master sheet")
    print("    ✗  Mismatch     — translation in org differs from master sheet")
    print("    ⚠  Not in Master — translated in org but not in master sheet")
    print("    —  Missing      — in master sheet but not yet translated in org")
    print()


def skill_sf_org_assessment(scripts_dir):
    header("SF Org Assessment")

    step(1, "Select Salesforce Org")
    # org_connect.py lives in sf-translation scripts dir
    org_connect_dir = os.path.join(ROOT, "scripts")
    org = select_org(org_connect_dir)

    step(2, "Output Directory")
    output_dir = ask("Output directory", DEFAULT_OUTPUT)
    output_dir = os.path.expanduser(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    step(3, "Running Assessment (this may take a minute...)")
    output_html = os.path.join(output_dir, f"org_assessment_{org}.html")
    run_script_streaming(
        os.path.join(scripts_dir, "run_assessment.py"),
        ["--org", org, "--output", output_html],
    )

    header("Done")
    print(f"  Report: {output_html}")
    print()
    print("  Open the HTML file in your browser to view the full assessment.")
    print()


# ── Entry point ───────────────────────────────────────────────────────────────

SKILL_LIST = [
    ("sf-translation <Object>",        "Generate STF translation files (fields + picklists)"),
    ("sf-translation-v2 <Object>",     "Generate STF files + LRP custom label translations"),
    ("sf-translation-verify <Object>", "Verify translations in org against master sheet"),
    ("sf-org-assessment",              "Assess Salesforce org health"),
]


def print_usage():
    print()
    print("Usage:  python3 run.py <skill> [object]")
    print()
    print("Skills:")
    for name, desc in SKILL_LIST:
        print(f"  {name:<38}  {desc}")
    print()
    print("Examples:")
    print("  python3 run.py sf-translation Vehicle")
    print("  python3 run.py sf-translation-v2 Vehicle")
    print("  python3 run.py sf-translation-verify Vehicle")
    print("  python3 run.py sf-org-assessment")
    print()


def check_dependencies():
    """Ensure openpyxl is installed."""
    try:
        import openpyxl  # noqa: F401
    except ImportError:
        print("Installing dependencies...")
        subprocess.run([sys.executable, "-m", "pip", "install", "openpyxl", "-q"], check=True)


def main():
    args = sys.argv[1:]

    if not args or args[0] in ("--help", "-h", "--list"):
        print_usage()
        sys.exit(0)

    skill = args[0].lower()
    object_name = args[1].strip() if len(args) > 1 else ""

    check_dependencies()

    if skill == "sf-translation":
        if not object_name:
            object_name = ask("Which Salesforce object?")
        skill_sf_translation(object_name, SCRIPTS["sf-translation"])

    elif skill == "sf-translation-v2":
        if not object_name:
            object_name = ask("Which Salesforce object?")
        skill_sf_translation_v2(object_name, SCRIPTS["sf-translation-v2"])

    elif skill == "sf-translation-verify":
        if not object_name:
            object_name = ask("Which Salesforce object?")
        skill_sf_translation_verify(object_name, SCRIPTS["sf-translation-verify"])

    elif skill == "sf-org-assessment":
        skill_sf_org_assessment(SCRIPTS["sf-org-assessment"])

    else:
        print(f"\n  Unknown skill: '{skill}'")
        print_usage()
        sys.exit(1)


if __name__ == "__main__":
    main()
