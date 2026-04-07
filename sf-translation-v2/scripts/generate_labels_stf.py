#!/usr/bin/env python3
"""
Generates custom label STF files and (when needed) a new custom labels XML file.

Reads the lrp_matches JSON produced by extract_lrp.py.

Outputs:
  OBJECT_labels_es.stf                     — ES custom label translations
  OBJECT_labels_pt_BR.stf                  — PT custom label translations
  OBJECT_new_custom_labels.labels-meta.xml — new labels to deploy (only if plain text matched)
  OBJECT_lrp_miss_report.csv               — items with no translation

IMPORTANT: If a new_custom_labels XML file is generated, you must:
  1. Deploy it to the org (sf project deploy start --source-dir ...)
  2. Update the LRP to reference {!$Label.ApiName} instead of the plain text
  3. Then import the STF into Translation Workbench
"""
import argparse
import csv
import json
import os
import sys


LANGUAGE_HEADERS = {
    "es": {
        "language_name": "Spanish",
        "language_code": "es",
    },
    "pt_BR": {
        "language_name": "Portuguese (Brazil)",
        "language_code": "pt_BR",
    },
}

STF_COMMENT_HEADER = """\
# Use the Source file to translate labels for the first time.
# - Change the language code in the header from the organization's default language to the translation language.
# - Replace the untranslated values in the LABEL column with translated values.

# Notes:
# Lines that begin with the # symbol are ignored during import.
# Salesforce translation files are exported in the UTF-8 encoding.
"""


def build_stf_header(language_code: str, language_name: str) -> str:
    return (
        f"{STF_COMMENT_HEADER}"
        f"\n"
        f"# Language: {language_name}\n"
        f"Language code: {language_code}\n"
        f"Type: Source\n"
        f"Translation type: Metadata\n"
        f"\n"
        f"# KEY\tLABEL\n"
        f"\n"
    )


def build_custom_labels_xml(labels: list, object_name: str) -> str:
    """
    Build a .labels-meta.xml string for new custom labels.

    labels: list of {derived_api_name, raw_title, component_type}
    categories naming convention: Onstar:{Object}:{ComponentType}:{ComponentName}
    """
    seen = set()
    items = []
    for label in labels:
        api = label["derived_api_name"]
        if api in seen:
            continue
        seen.add(api)
        eng           = label["raw_title"].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        comp_type     = label.get("component_type", "Tab")  # Tab or RelatedList
        category      = f"Onstar:{object_name}:{comp_type}:{label['raw_title']}"
        items.append(
            f"    <labels>\n"
            f"        <fullName>{api}</fullName>\n"
            f"        <categories>{category}</categories>\n"
            f"        <language>en_US</language>\n"
            f"        <protected>false</protected>\n"
            f"        <shortDescription>{eng}</shortDescription>\n"
            f"        <value>{eng}</value>\n"
            f"    </labels>"
        )
    body = "\n".join(items)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<CustomLabels xmlns="http://soap.sforce.com/2006/04/metadata">\n'
        f"{body}\n"
        '</CustomLabels>\n'
    )


def main():
    parser = argparse.ArgumentParser(description="Generate custom label STF files from LRP matches")
    parser.add_argument("--lrp-matches", required=True, help="Path to lrp_matches JSON from extract_lrp.py")
    parser.add_argument("--object",      required=True, dest="object_name", help="Salesforce object API name")
    parser.add_argument("--output",      required=True, help="Output directory")
    args = parser.parse_args()

    with open(args.lrp_matches, "r", encoding="utf-8") as f:
        data = json.load(f)

    os.makedirs(args.output, exist_ok=True)

    label_needs = data.get("label_needs_translation", [])
    plain_matched = data.get("plain_matched", [])
    label_not_in_org = data.get("label_not_in_org", [])

    results = {}

    # ── Generate STF files for ES and PT ──────────────────────────────────────
    for lang_code, lang_key, write_flag, miss_flag in [
        ("es",    "spanish",    "write_es", "miss_es"),
        ("pt_BR", "portuguese", "write_pt", "miss_pt"),
    ]:
        lang_info = LANGUAGE_HEADERS[lang_code]
        header    = build_stf_header(lang_info["language_code"], lang_info["language_name"])
        lines     = []
        seen_keys = set()

        # $Label refs
        for c in label_needs:
            if c.get(write_flag):
                key = f"customLabel.{c['label_api_name']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    lines.append((key, c[lang_key]))

        # Plain text matched in master → new custom label
        for c in plain_matched:
            if c.get(write_flag):
                key = f"customLabel.{c['derived_api_name']}"
                if key not in seen_keys:
                    seen_keys.add(key)
                    lines.append((key, c[lang_key]))

        output_file = os.path.join(args.output, f"{args.object_name}_labels_{lang_code}.stf")
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(header)
            for stf_key, translation in lines:
                f.write(f"{stf_key}\t{translation}\n")

        results[lang_code] = {"file": output_file, "written": len(lines)}

    # ── Generate new custom labels XML (only if plain text labels found) ──────
    xml_file = None
    if plain_matched:
        xml_file = os.path.join(args.output, f"{args.object_name}_new_custom_labels.labels-meta.xml")
        xml_content = build_custom_labels_xml(plain_matched, args.object_name)
        with open(xml_file, "w", encoding="utf-8") as f:
            f.write(xml_content)

    # ── Generate miss report ──────────────────────────────────────────────────
    miss_rows = []

    # $Label refs: per-language misses (only for in-master entries)
    for c in label_needs:
        if not c.get("in_master"):
            continue
        for lang_code, miss_flag, has_flag in [("es", "miss_es", "has_es"), ("pt_BR", "miss_pt", "has_pt")]:
            if c.get(miss_flag) and not c.get(has_flag):
                reason = (
                    "Multi-value in master sheet"
                    if c.get("spanish" if lang_code == "es" else "portuguese")
                    else "Empty in master sheet"
                )
                miss_rows.append({
                    "Type":           c["component_type"],
                    "Label API Name": c["label_api_name"],
                    "English Value":  c.get("english_value", ""),
                    "Language":       lang_code,
                    "Reason":         reason,
                })

    # $Label refs not in master sheet → single combined row
    for c in [c for c in label_needs if not c.get("in_master")]:
        langs = []
        if c.get("miss_es") and not c.get("has_es"):
            langs.append("es")
        if c.get("miss_pt") and not c.get("has_pt"):
            langs.append("pt_BR")
        if langs:
            miss_rows.append({
                "Type":           c["component_type"],
                "Label API Name": c["label_api_name"],
                "English Value":  c.get("english_value", ""),
                "Language":       " + ".join(langs),
                "Reason":         "Not found in master sheet",
            })

    # Labels not found in org
    for c in label_not_in_org:
        miss_rows.append({
            "Type":           c["component_type"],
            "Label API Name": c["label_api_name"],
            "English Value":  "",
            "Language":       "es + pt_BR",
            "Reason":         "Custom label does not exist in org",
        })

    # Plain text not in master
    for c in data.get("plain_unmatched", []):
        miss_rows.append({
            "Type":           c["component_type"],
            "Label API Name": c["raw_title"],
            "English Value":  c["raw_title"],
            "Language":       "es + pt_BR",
            "Reason":         "Plain text label not found in master sheet",
        })

    # Plain matched but translation missing/multi-value
    for c in plain_matched:
        for lang_code, miss_flag in [("es", "miss_es"), ("pt_BR", "miss_pt")]:
            if c.get(miss_flag):
                lang_val = c.get("spanish" if lang_code == "es" else "portuguese", "")
                reason = "Multi-value in master sheet" if lang_val else "Empty in master sheet"
                miss_rows.append({
                    "Type":           c["component_type"],
                    "Label API Name": c.get("derived_api_name", c["raw_title"]),
                    "English Value":  c["raw_title"],
                    "Language":       lang_code,
                    "Reason":         reason,
                })

    miss_file = os.path.join(args.output, f"{args.object_name}_lrp_miss_report.csv")
    with open(miss_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["Type", "Label API Name", "English Value", "Language", "Reason"]
        )
        writer.writeheader()
        writer.writerows(miss_rows)

    # ── Print summary ─────────────────────────────────────────────────────────
    output_info = {
        "es_stf":       results["es"]["file"],
        "pt_BR_stf":    results["pt_BR"]["file"],
        "miss_report":  miss_file,
    }
    if xml_file:
        output_info["new_custom_labels_xml"] = xml_file

    notes = []
    if xml_file:
        notes.append(
            "ACTION REQUIRED: Deploy the new_custom_labels_xml file and update the LRP "
            "to reference {!$Label.ApiName} before importing the STF."
        )

    print(json.dumps({
        "status": "ok",
        "files":  output_info,
        "summary": (
            f"ES: {results['es']['written']} custom label translation(s) written. "
            f"PT: {results['pt_BR']['written']} custom label translation(s) written. "
            f"Miss report: {len(miss_rows)} item(s). "
            f"New custom labels to create: {len(plain_matched)}."
        ),
        "notes": notes,
        "miss_count": len(miss_rows),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
