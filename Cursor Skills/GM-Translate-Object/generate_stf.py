#!/usr/bin/env python3
"""
generate_stf.py — Salesforce STF Translation File Generator
============================================================
Generates bilingual STF files for import into Salesforce Translation Workbench.

Usage:
    python3 generate_stf.py \
        --object Case \
        --master "/path/to/Master Sheet Copy.xlsx" \
        --bilingual-es-co "/path/to/Bilingual_es_CO.stf" \
        --bilingual-pt-br "/path/to/Bilingual_pt_BR.stf" \
        --output-dir "~/Desktop/sf-translation-output"

Output:
    <output-dir>/<object>_es_CO.stf
    <output-dir>/<object>_pt_BR.stf
    <output-dir>/<object>_es.stf          (only if --bilingual-es provided)
    <output-dir>/<object>_over40_report.txt

Rules:
    - Output format: Bilingual (4-column: KEY\\tSOURCE\\tTRANSLATION\\t-)
    - Keys are sourced from the bilingual UNTRANSLATED section only
    - STRICT object filter: only keys where object segment == OBJECT_NAME, plus GVS
    - Accepted key types: CustomField, PicklistValue, LayoutSection, RecordType,
                          QuickAction, CustomLabel, ButtonOrLink
    - Skip if key is already in TRANSLATED section (already done in org)
    - Skip if translation not found in master sheet
    - Skip if translation is empty or multi-value (contains a comma)
    - CRITICAL: Skip if len(translation) > 40 characters — log to over40 report
    - DO NOT skip if translation == source label (brand names, acronyms are valid)
"""

import argparse
import os
import sys
import pandas as pd

# ── Constants ─────────────────────────────────────────────────────────────────

ACCEPTED_KEY_TYPES = {
    'CustomField',
    'PicklistValue',
    'LayoutSection',
    'RecordType',
    'QuickAction',
    'CustomLabel',
    'ButtonOrLink',
}

BILINGUAL_HEADER = """\
# Use the Bilingual file to review translations, edit labels that have already been translated, and add translations for labels that haven't been translated.
# - The TRANSLATED section of the file contains the text that has been translated and needs to be reviewed.
# - The OUTDATED AND UNTRANSLATED section of the file contains text that hasn't been translated. You can replace untranslated labels in the LABEL column with translated values.

# Notes:
# Don't add columns to or remove columns from this file.
# Tabs (\\t), new lines (\\n) and carriage returns (\\r) are represented by special characters in this file.
# Lines that begin with the # symbol are ignored during import.
# Salesforce translation files are exported in the UTF-8 encoding.

# Language: {lang_name}
Language code: {lang_code}
Type: Bilingual
Translation type: Metadata

------------------TRANSLATED-------------------

# KEY\tLABEL\tTRANSLATION\tOUT OF DATE

"""

# ── Helpers ───────────────────────────────────────────────────────────────────

def load_master(master_path):
    """Load master Excel sheet. Returns dict keyed by lowercased English label."""
    df = pd.read_excel(master_path, sheet_name='Sheet1', header=0)
    master = {}
    for _, row in df.iterrows():
        eng = str(row.iloc[2]).strip() if pd.notna(row.iloc[2]) else ''
        es  = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else ''
        pt  = str(row.iloc[4]).strip() if pd.notna(row.iloc[4]) else ''
        if not eng or eng.lower() in ('nan', 'field name', 'english'):
            continue
        key = eng.lower()
        if key not in master:
            master[key] = {
                'es': '' if es == 'nan' else es,
                'pt': '' if pt == 'nan' else pt,
            }
    return master


def is_valid_key(key, object_name):
    """
    Return True if this key should be included in the STF for the given object.

    STRICT FILTER:
      - key_type must be in ACCEPTED_KEY_TYPES
      - key_object must equal object_name (e.g. 'Case')
        EXCEPT for GVS picklist values where key_object ends with '__gvs'
    """
    parts = key.split('.')
    if len(parts) < 2:
        return False
    key_type   = parts[0]
    key_object = parts[1]

    if key_type not in ACCEPTED_KEY_TYPES:
        return False

    is_target_object = (key_object == object_name)
    is_gvs           = (key_type == 'PicklistValue' and key_object.endswith('__gvs'))

    return is_target_object or is_gvs


def parse_bilingual(filepath, object_name):
    """
    Parse a Salesforce bilingual STF file.

    Returns:
        translated_keys : set of keys already translated in org (skip these)
        untranslated    : dict of {key: source_label} for keys needing translation
    """
    translated_keys = set()
    untranslated    = {}
    in_translated   = False
    in_untranslated = False

    with open(filepath, 'r', encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n')

            # Detect section boundaries
            stripped = line.replace('-', '').replace('*', '').strip().upper()
            if stripped == 'TRANSLATED':
                in_translated = True
                in_untranslated = False
                continue
            if 'OUTDATED' in stripped and 'UNTRANSLATED' in stripped:
                in_translated = False
                in_untranslated = True
                continue

            # Skip comments and blank lines
            if not line.strip() or line.strip().startswith('#'):
                continue
            if '\t' not in line:
                continue

            parts = line.split('\t')
            key   = parts[0].strip().lstrip('-').lstrip('*').strip()
            if not key:
                continue

            # Apply strict object + key-type filter
            if not is_valid_key(key, object_name):
                continue

            if in_translated:
                translated_keys.add(key)
            elif in_untranslated:
                source = parts[1].strip() if len(parts) > 1 else ''
                untranslated[key] = source

    return translated_keys, untranslated


def generate_stf(object_name, bilingual_path, lang_key, lang_name, lang_code,
                 master, output_path, lrp_label_keys=None):
    """
    Generate one bilingual STF file.

    Args:
        object_name    : e.g. 'Case'
        bilingual_path : path to the downloaded bilingual STF
        lang_key       : 'es' or 'pt' (key into master dict)
        lang_name      : e.g. 'Spanish (Colombia)'
        lang_code      : e.g. 'es_CO'
        master         : dict from load_master()
        output_path    : where to write the output STF
        lrp_label_keys : optional set of CustomLabel.* keys from LRP (Step 7)
    """
    translated_keys, untranslated = parse_bilingual(bilingual_path, object_name)

    stats = {
        'written':            0,
        'skipped_translated': 0,
        'skipped_no_master':  0,
        'skipped_empty':      0,
        'skipped_multivalue': 0,
        'skipped_over40':     0,
    }
    over40_entries = []
    lines = []

    for key, source_label in untranslated.items():
        # Skip if already translated in org
        if key in translated_keys:
            stats['skipped_translated'] += 1
            continue

        # For CustomLabel keys, only include if they come from the LRP flexipages
        key_type = key.split('.')[0]
        if key_type == 'CustomLabel':
            if lrp_label_keys is None or key not in lrp_label_keys:
                continue

        # Look up translation in master sheet by source label
        lookup = source_label.lower()
        match  = master.get(lookup)
        if match is None:
            stats['skipped_no_master'] += 1
            continue

        trans = match[lang_key]

        if not trans:
            stats['skipped_empty'] += 1
            continue

        # Multi-value check — any comma means multiple alternatives, skip
        if ',' in trans:
            stats['skipped_multivalue'] += 1
            continue

        # CRITICAL: 40-character limit — Salesforce rejects longer translations
        if len(trans) > 40:
            stats['skipped_over40'] += 1
            over40_entries.append((key, source_label, trans, len(trans)))
            continue

        # DO NOT skip if trans == source_label
        # Brand names, acronyms, state names that stay the same are valid translations

        lines.append(f"{key}\t{source_label}\t{trans}\t-")
        stats['written'] += 1

    # Write STF file
    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(BILINGUAL_HEADER.format(lang_name=lang_name, lang_code=lang_code))
        for l in lines:
            f.write(l + '\n')

    return stats, over40_entries


def print_stats(lang_code, output_path, stats, over40):
    print(f"\n[{lang_code}]")
    print(f"  Written:                  {stats['written']}")
    print(f"  Skipped (already in org): {stats['skipped_translated']}")
    print(f"  Skipped (not in master):  {stats['skipped_no_master']}")
    print(f"  Skipped (empty):          {stats['skipped_empty']}")
    print(f"  Skipped (multi-value):    {stats['skipped_multivalue']}")
    print(f"  Skipped (>40 chars):      {stats['skipped_over40']}")
    print(f"  → {output_path}")
    if over40:
        print(f"\n  Over-40 entries (NOT written to STF — fix translations in master sheet):")
        for key, src, trans, length in over40:
            print(f"    [{length} chars] {key}")
            print(f"      Source:      {src}")
            print(f"      Translation: {trans}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Generate Salesforce bilingual STF translation files.')
    parser.add_argument('--object',          required=True,  help='Salesforce object API name, e.g. Case')
    parser.add_argument('--master',          required=True,  help='Path to master Excel sheet')
    parser.add_argument('--bilingual-es-co', required=False, help='Path to bilingual STF for es_CO')
    parser.add_argument('--bilingual-pt-br', required=False, help='Path to bilingual STF for pt_BR')
    parser.add_argument('--bilingual-es',    required=False, help='Path to bilingual STF for es (optional)')
    parser.add_argument('--output-dir',      default='~/Desktop/sf-translation-output',
                        help='Output directory (default: ~/Desktop/sf-translation-output)')
    parser.add_argument('--lrp-labels',      required=False,
                        help='Comma-separated CustomLabel API names from LRP flexipages, e.g. MyLabel1,MyLabel2')
    args = parser.parse_args()

    object_name = args.object.strip()
    output_dir  = os.path.expanduser(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if not args.bilingual_es_co and not args.bilingual_pt_br and not args.bilingual_es:
        print("ERROR: At least one bilingual STF must be provided (--bilingual-es-co or --bilingual-pt-br).")
        sys.exit(1)

    # Build LRP label key set
    lrp_label_keys = None
    if args.lrp_labels:
        lrp_label_keys = {f"CustomLabel.{name.strip()}" for name in args.lrp_labels.split(',')}

    print(f"Loading master sheet: {args.master}")
    master = load_master(args.master)
    print(f"  Loaded {len(master)} entries")

    all_over40 = []

    languages = []
    if args.bilingual_es_co:
        languages.append((args.bilingual_es_co, 'es', 'Spanish (Colombia)', 'es_CO'))
    if args.bilingual_pt_br:
        languages.append((args.bilingual_pt_br, 'pt', 'Portuguese (Brazil)', 'pt_BR'))
    if args.bilingual_es:
        languages.append((args.bilingual_es,    'es', 'Spanish',             'es'))

    for bilingual_path, lang_key, lang_name, lang_code in languages:
        output_path = os.path.join(output_dir, f"{object_name}_{lang_code}.stf")
        stats, over40 = generate_stf(
            object_name, bilingual_path, lang_key, lang_name, lang_code,
            master, output_path, lrp_label_keys
        )
        print_stats(lang_code, output_path, stats, over40)
        all_over40.extend([(lang_code, k, s, t, l) for k, s, t, l in over40])

    # Write over-40 report
    if all_over40:
        report_path = os.path.join(output_dir, f"{object_name}_over40_report.txt")
        with open(report_path, 'w', encoding='utf-8') as f:
            f.write(f"Translations exceeding 40 characters — NOT written to STF\n")
            f.write(f"Fix these in the master sheet and rerun.\n\n")
            for lang_code, key, src, trans, length in all_over40:
                f.write(f"[{lang_code}] [{length} chars] {key}\n")
                f.write(f"  Source:      {src}\n")
                f.write(f"  Translation: {trans}\n\n")
        print(f"\nOver-40 report: {report_path}")

    print(f"\nDone.")


if __name__ == '__main__':
    main()
