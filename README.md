# sf-translation

A Claude Code skill that generates Salesforce STF translation files (Spanish / Portuguese Brazil) for any Salesforce object, by comparing org field metadata against a master translation Excel sheet.

## Installation

```bash
git clone <your-repo-url> sf-translation
cd sf-translation
python3 install.py
```

## Usage

```
/sf-translation Vehicle
/sf-translation Case
/sf-translation Account
```

## Prerequisites

- **Salesforce CLI** (`sf`) — [Install](https://developer.salesforce.com/tools/salesforcecli)
- **Python 3** — standard on macOS/Linux
- **pandas + openpyxl** — auto-installed by `install.py`

## Master Excel Sheet format

| Column | Header | Content |
|--------|--------|---------|
| A | Object Name | e.g. `Vehicle`, `Account` |
| B | Field Type | e.g. `Custom Field`, `Picklist Value` |
| **C** | **Field Name** | **English label — matched against** |
| **D** | **Spanish Translation** | **Output for `_es.stf`** |
| **E** | **Portuguese Translation** | **Output for `_pt_BR.stf`** |

Row 1 is a header row. Data starts at row 2.

## Output files

| File | Description |
|------|-------------|
| `[Object]_intermediate.xlsx` | Field/picklist inventory from org |
| `[Object]_es.stf` | Spanish translations |
| `[Object]_pt_BR.stf` | Portuguese (Brazil) translations |
| `[Object]_miss_report.csv` | Fields with no translation found |

## STF key formats

```
CustomField.[Object].[FieldAPINameWithout__c].FieldLabel    <TAB>  translation
PicklistValue.[Object].[FieldAPINameWithout__c].[value]     <TAB>  translation
```

## Phase 1 scope

- Custom field labels
- Picklist values

Future phases: LRP, buttons, related lists, custom labels.
