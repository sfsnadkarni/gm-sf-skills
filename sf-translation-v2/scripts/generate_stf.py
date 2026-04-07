#!/usr/bin/env python3
"""
Generates Salesforce STF translation files from matches JSON.

Generates:
  [ObjectName]_es.stf       — Spanish
  [ObjectName]_pt_BR.stf    — Portuguese (Brazil)

STF key formats:
  CustomField.[Object].[FieldAPINameWithout__c].FieldLabel   <TAB>  translation
  PicklistValue.[Object].[FieldAPINameWithout__c].[value]    <TAB>  translation

Rules:
  - Never overwrite keys that already exist in an optional existing STF file.
  - Skip entries where the translation is empty.
  - UTF-8 encoding, tab-separated.
"""
import argparse
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
# - Change the language code in the header from the organization's default language to the translation language. See "Supported Languages for Translatable Customizations" in the Salesforce.com online help for a list of supported languages and their associated language codes.
# - Replace the untranslated values in the LABEL column with translated values.

# Notes:
# Don't add columns to or remove columns from this file.
# Tabs (\\t), new lines (\\n) and carriage returns (\\r) are represented by special characters in this file. These characters should be preserved in the import file to maintain formatting.
# Lines that begin with the # symbol are ignored during import.
# Salesforce translation files are exported in the UTF-8 encoding to support extended and double-byte characters. This encoding cannot be changed.
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


def parse_existing_stf(stf_path: str) -> set:
    """
    Returns a set of already-translated keys from an existing STF file.

    Handles two formats:
    - Translation file (Type: Translation): all data lines are translated — collect all keys.
    - Bilingual file (Type: Bilingual): has a TRANSLATED section and an UNTRANSLATED section.
      Only collect keys from the TRANSLATED section; skip UNTRANSLATED keys since those
      still need translation.
    """
    existing_keys = set()
    if not stf_path or not os.path.isfile(stf_path):
        return existing_keys

    is_bilingual = False
    in_translated_section = False

    with open(stf_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n\r")

            # Detect file type from header
            if line.startswith("Type:"):
                file_type = line.split(":", 1)[1].strip()
                is_bilingual = (file_type.lower() == "bilingual")
                if not is_bilingual:
                    # Translation or Source file — treat all data lines as translated
                    in_translated_section = True
                continue

            # Bilingual section separators
            if is_bilingual:
                if "TRANSLATED" in line and "UNTRANSLATED" not in line and line.startswith("---"):
                    in_translated_section = True
                    continue
                if "UNTRANSLATED" in line and line.startswith("---"):
                    in_translated_section = False
                    continue

            if not in_translated_section:
                continue
            if not line or line.startswith("#"):
                continue
            if "\t" not in line:
                continue

            key, _, _ = line.partition("\t")
            key = key.strip()
            if key:
                existing_keys.add(key)

    return existing_keys


def generate_stf_lines(object_name: str, matches: dict, lang_key: str, existing_keys: set):
    """
    Yields (stf_key, translation) tuples for one language.
    lang_key: 'spanish' or 'portuguese'
    """
    skipped = 0
    written = 0

    multi_value_flag = "multi_value_es" if lang_key == "spanish" else "multi_value_pt"

    # Custom field labels
    for entry in matches.get("matched_fields", []):
        translation = entry.get(lang_key, "").strip()
        if not translation:
            skipped += 1
            continue
        if entry.get(multi_value_flag, False):
            skipped += 1
            continue
        stf_key = f"CustomField.{object_name}.{entry['stf_field_name']}.FieldLabel"
        if stf_key in existing_keys:
            skipped += 1
            continue
        yield stf_key, translation
        written += 1

    # Picklist values
    for entry in matches.get("matched_picklists", []):
        translation = entry.get(lang_key, "").strip()
        if not translation:
            skipped += 1
            continue
        if entry.get(multi_value_flag, False):
            skipped += 1
            continue
        pv_value = entry["picklist_value"]
        stf_key = f"PicklistValue.{object_name}.{entry['stf_field_name']}.{pv_value}"
        if stf_key in existing_keys:
            skipped += 1
            continue
        yield stf_key, translation
        written += 1


def write_stf_file(output_path: str, header: str, lines: list):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header)
        for stf_key, translation in lines:
            f.write(f"{stf_key}\t{translation}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate Salesforce STF translation files")
    parser.add_argument("--matches", required=True, help="Path to matches JSON file")
    parser.add_argument("--object", required=True, dest="object_name", help="Salesforce object API name")
    parser.add_argument("--output", required=True, help="Output directory")
    parser.add_argument("--existing-es", default="", help="Path to existing Spanish STF (optional)")
    parser.add_argument("--existing-pt", default="", help="Path to existing Portuguese STF (optional)")
    args = parser.parse_args()

    with open(args.matches, "r", encoding="utf-8") as f:
        matches = json.load(f)

    os.makedirs(args.output, exist_ok=True)

    results = {}

    for lang_code, lang_key, existing_path in [
        ("es",    "spanish",    args.existing_es),
        ("pt_BR", "portuguese", args.existing_pt),
    ]:
        lang_info = LANGUAGE_HEADERS[lang_code]
        header = build_stf_header(lang_info["language_code"], lang_info["language_name"])

        existing_keys = parse_existing_stf(existing_path)

        lines = list(generate_stf_lines(args.object_name, matches, lang_key, existing_keys))

        output_file = os.path.join(args.output, f"{args.object_name}_{lang_code}.stf")
        write_stf_file(output_file, header, lines)

        skipped_existing = sum(
            1 for entry in matches.get("matched_fields", []) + matches.get("matched_picklists", [])
            if (
                f"CustomField.{args.object_name}.{entry.get('stf_field_name','')}.FieldLabel" in existing_keys
                or f"PicklistValue.{args.object_name}.{entry.get('stf_field_name','')}.{entry.get('picklist_value','')}" in existing_keys
            )
        )

        results[lang_code] = {
            "file": output_file,
            "written": len(lines),
            "skipped_already_translated": len(existing_keys),
        }

    print(json.dumps({
        "status": "ok",
        "object": args.object_name,
        "files": results,
        "summary": (
            f"Spanish: {results['es']['written']} translation(s) written → {results['es']['file']}\n"
            f"Portuguese: {results['pt_BR']['written']} translation(s) written → {results['pt_BR']['file']}"
        ),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
