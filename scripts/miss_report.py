#!/usr/bin/env python3
"""
Generates a miss report CSV from the matches JSON.

Columns:
  Type            — "Custom Field" or "Picklist Value"
  English Label   — the English label that was searched for
  Field API Name  — STF field name (without __c)
  Reason          — "Not found in master sheet" or "Translation empty"
"""
import argparse
import csv
import json
import os
import sys


def main():
    parser = argparse.ArgumentParser(description="Generate miss report CSV")
    parser.add_argument("--matches", required=True, help="Path to matches JSON file")
    parser.add_argument("--object", required=True, dest="object_name", help="Salesforce object API name")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()

    with open(args.matches, "r", encoding="utf-8") as f:
        matches = json.load(f)

    os.makedirs(args.output, exist_ok=True)
    output_file = os.path.join(args.output, f"{args.object_name}_miss_report.csv")

    rows = []

    # Fields not found in master sheet
    for entry in matches.get("unmatched_fields", []):
        rows.append({
            "Type": "Custom Field",
            "English Label": entry["field_label"],
            "Field API Name": entry.get("stf_field_name", ""),
            "Reason": "Not found in master sheet",
        })

    # Fields matched but translation is empty or multi-value
    for entry in matches.get("matched_fields", []):
        issues = []
        es = entry.get("spanish", "").strip()
        pt = entry.get("portuguese", "").strip()
        if entry.get("multi_value_es"):
            issues.append("Spanish: multiple values in cell (needs manual review)")
        elif not es:
            issues.append("Spanish: empty")
        if entry.get("multi_value_pt"):
            issues.append("Portuguese: multiple values in cell (needs manual review)")
        elif not pt:
            issues.append("Portuguese: empty")
        if issues:
            rows.append({
                "Type": "Custom Field",
                "English Label": entry["field_label"],
                "Field API Name": entry.get("stf_field_name", ""),
                "Reason": "; ".join(issues),
            })

    # Picklist values not found in master sheet
    for entry in matches.get("unmatched_picklists", []):
        rows.append({
            "Type": "Picklist Value",
            "English Label": entry["picklist_label"],
            "Field API Name": entry.get("stf_field_name", ""),
            "Reason": "Not found in master sheet",
        })

    # Picklist values matched but translation is empty or multi-value
    for entry in matches.get("matched_picklists", []):
        issues = []
        es = entry.get("spanish", "").strip()
        pt = entry.get("portuguese", "").strip()
        if entry.get("multi_value_es"):
            issues.append("Spanish: multiple values in cell (needs manual review)")
        elif not es:
            issues.append("Spanish: empty")
        if entry.get("multi_value_pt"):
            issues.append("Portuguese: multiple values in cell (needs manual review)")
        elif not pt:
            issues.append("Portuguese: empty")
        if issues:
            rows.append({
                "Type": "Picklist Value",
                "English Label": entry["picklist_label"],
                "Field API Name": entry.get("stf_field_name", ""),
                "Reason": "; ".join(issues),
            })

    fieldnames = ["Type", "English Label", "Field API Name", "Reason"]
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    stats = matches.get("stats", {})
    print(json.dumps({
        "status": "ok",
        "miss_report": output_file,
        "miss_count": len(rows),
        "summary": (
            f"Miss report written: {len(rows)} item(s) with no translation.\n"
            f"  Fields matched: {stats.get('fields_matched', '?')}/{stats.get('fields_total', '?')}\n"
            f"  Picklists matched: {stats.get('picklists_matched', '?')}/{stats.get('picklists_total', '?')}"
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
