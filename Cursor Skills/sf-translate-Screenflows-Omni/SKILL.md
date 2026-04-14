---
name: sf-translate-screenflows-omni
description: >
  Generate Salesforce STF translation files (Spanish (Colombia) / Spanish (Mexico) / Portuguese (Brazil)) for Screen Flows,
  OmniScripts, and FlexCards. Extracts all UI text elements directly from the org,
  resolves embedded components recursively to the nth level, matches labels against a
  master Excel translation sheet, and produces STF files ready for Translation Workbench import.
arguments: true
---

You are helping the user generate Salesforce translation STF files for a Screen Flow,
OmniScript, or FlexCard component.

The component name(s) provided are: **$ARGUMENTS**

If no component name was provided in $ARGUMENTS, immediately ask the user:
> "Which Screen Flow, OmniScript, or FlexCard do you want to generate translations for?
> Provide one or more API names, comma-separated. (e.g. `CaseCreation_Flow, MyFlexCard`)"

Set COMPONENT_NAMES = comma-split list from $ARGUMENTS (trimmed).

---

## Step 0: Install Dependencies

Run silently:
```bash
python3 -c "import openpyxl, xml.etree.ElementTree, json, csv; print('OK')" 2>&1
```

If it fails, run:
```bash
pip3 install openpyxl --quiet
```

Tell the user if any install failed and ask them to run `pip3 install openpyxl` manually.

---

## Step 1: Select Salesforce Org

Run:
```bash
sf org list --json 2>/dev/null
```

Parse the JSON. Collect all entries from `result.nonScratchOrgs` and `result.scratchOrgs`.
Display a numbered list:
```
Authenticated Salesforce orgs:
  1. alias=myorg    username=user@example.com    status=Connected
  2. alias=devorg   username=dev@example.com     status=Connected
  0. Connect a new org
```

Ask: "Enter the number of the org to use:"

If the user picks 0, run:
```bash
sf org login web
```
Then re-run `sf org list --json`, show the updated list, and ask the user to select the newly connected org.

Store the selected org's **username** as SELECTED_ORG.

---

## Step 2: Collect File Paths

Ask the user for the following in a single message:

1. **Component type** — `Screen Flow`, `OmniScript`, `FlexCard`, or `Auto-detect`
   (default: `Auto-detect`)
2. **Master Excel Sheet path** — translation reference file
   (Col C = English source, Col D = Spanish, Col E = Portuguese (Brazil))
3. **Output directory** — where to save all generated files
   (default: `~/Desktop/sf-translation-output`)
4. **(Optional) Existing Spanish (Colombia) STF** — a previously downloaded Bilingual STF for `es_CO`;
   already-translated keys are skipped. Press Enter to skip.
5. **(Optional) Existing Spanish (Mexico) STF** — a previously downloaded Bilingual STF for `es_MX`;
   already-translated keys are skipped. Press Enter to skip.
6. **(Optional) Existing Portuguese (Brazil) STF** — a previously downloaded Bilingual STF for `pt_BR`;
   already-translated keys are skipped. Press Enter to skip.

Store as: COMPONENT_TYPE, MASTER_PATH, OUTPUT_DIR, EXISTING_ES_CO, EXISTING_ES_MX, EXISTING_PT_BR.

If the user skips OUTPUT_DIR, use `~/Desktop/sf-translation-output`.
Expand `~` and create the directory:
```bash
mkdir -p "OUTPUT_DIR"
mkdir -p "OUTPUT_DIR/metadata"
mkdir -p "OUTPUT_DIR/scripts"
```

---

## Step 3: Detect Component Type and Retrieve Metadata Recursively

### 3a — Auto-detect component type (if COMPONENT_TYPE = "Auto-detect")

For each name in COMPONENT_NAMES, run the following SOQL queries in order and stop at the
first match. Store the detected type per component.

**Screen Flow:**
```bash
sf data query \
  --query "SELECT Id, ApiName, ActiveVersionId, MasterLabel FROM FlowDefinition WHERE ApiName = 'COMPONENT_NAME'" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```

**OmniScript:**
```bash
sf data query \
  --query "SELECT Id, Name, Type__c, SubType__c, Language__c, IsActive FROM OmniProcess WHERE Name = 'COMPONENT_NAME' AND IsActive = true LIMIT 1" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```
If that fails (object not present), also try the legacy object:
```bash
sf data query \
  --query "SELECT Id, Name, IsActive__c FROM vlocity_cmt__OmniScript__c WHERE Name = 'COMPONENT_NAME' AND IsActive__c = true LIMIT 1" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```

**FlexCard:**
```bash
sf data query \
  --query "SELECT Id, Name, IsActive FROM OmniUiCard WHERE Name = 'COMPONENT_NAME' LIMIT 1" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```
If that fails, try the legacy object:
```bash
sf data query \
  --query "SELECT Id, Name FROM vlocity_cmt__VlocityCard__c WHERE Name = 'COMPONENT_NAME' LIMIT 1" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```

If **no match** is found for a component name, tell the user and ask them to confirm the API name or choose the type manually.

### 3b — Retrieve metadata files from the org

For each component, retrieve its metadata. Use a temporary retrieve directory inside OUTPUT_DIR/metadata.

**Screen Flow — retrieve active version:**
```bash
sf project retrieve start \
  --metadata "Flow:COMPONENT_NAME" \
  --target-org "SELECTED_ORG" \
  --output-dir "OUTPUT_DIR/metadata" \
  --json 2>/dev/null
```
The flow XML will appear at `OUTPUT_DIR/metadata/force-app/main/default/flows/COMPONENT_NAME.flow-meta.xml`
(or similar path depending on retrieve structure — scan OUTPUT_DIR/metadata recursively for `*.flow-meta.xml`).

**OmniScript — retrieve:**
```bash
sf project retrieve start \
  --metadata "OmniScript:COMPONENT_TYPE/COMPONENT_SUBTYPE/COMPONENT_LANGUAGE" \
  --target-org "SELECTED_ORG" \
  --output-dir "OUTPUT_DIR/metadata" \
  --json 2>/dev/null
```
If the retrieve API name format is unclear, fall back to SOQL export:
```bash
sf data query \
  --query "SELECT Id, Name, OmniProcessType, LovType, PropertySet FROM OmniProcess WHERE Name = 'COMPONENT_NAME' AND IsActive = true LIMIT 1" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```
Save the `PropertySet` JSON field (which contains the full OmniScript definition) to
`OUTPUT_DIR/metadata/COMPONENT_NAME_omniscript.json`.

**FlexCard — retrieve:**
```bash
sf project retrieve start \
  --metadata "OmniFlexCard:COMPONENT_NAME" \
  --target-org "SELECTED_ORG" \
  --output-dir "OUTPUT_DIR/metadata" \
  --json 2>/dev/null
```
If that fails, use SOQL:
```bash
sf data query \
  --query "SELECT Id, Name, Definition FROM OmniUiCard WHERE Name = 'COMPONENT_NAME' LIMIT 1" \
  --target-org "SELECTED_ORG" --json 2>/dev/null
```
Save the `Definition` JSON field to `OUTPUT_DIR/metadata/COMPONENT_NAME_flexcard.json`.

### 3c — Recursive embedded component detection

After retrieving each component, parse its metadata to find embedded/referenced components.

Write the following Python script to `OUTPUT_DIR/scripts/find_embedded.py` and run it:

```python
#!/usr/bin/env python3
"""
Find embedded component references in Screen Flow, OmniScript, or FlexCard metadata.
Usage: python3 find_embedded.py --file PATH --type [flow|omniscript|flexcard]
"""
import sys, json, argparse, xml.etree.ElementTree as ET
from pathlib import Path

def find_flow_embedded(xml_path):
    """Return list of (type, name) tuples for embedded components in a flow."""
    embedded = []
    try:
        tree = ET.parse(xml_path)
        root = tree.getroot()
        ns = {'sf': 'http://soap.sforce.com/2006/04/metadata'}
        # Subflow references
        for el in root.findall('.//{http://soap.sforce.com/2006/04/metadata}subflowLaunch') + \
                   root.findall('.//{http://soap.sforce.com/2006/04/metadata}subflow'):
            name_el = el.find('{http://soap.sforce.com/2006/04/metadata}flowName') or \
                      el.find('{http://soap.sforce.com/2006/04/metadata}name')
            if name_el is not None and name_el.text:
                embedded.append(('flow', name_el.text.strip()))
        # Action calls that are flows
        for el in root.findall('.//{http://soap.sforce.com/2006/04/metadata}actionCalls'):
            atype = el.find('{http://soap.sforce.com/2006/04/metadata}actionType')
            aname = el.find('{http://soap.sforce.com/2006/04/metadata}actionName')
            if atype is not None and atype.text in ('Flow', 'SubFlow') and aname is not None:
                embedded.append(('flow', aname.text.strip()))
        # Screen component references (LWC or Aura embedded in flow screen)
        for el in root.findall('.//{http://soap.sforce.com/2006/04/metadata}fields'):
            ftype = el.find('{http://soap.sforce.com/2006/04/metadata}fieldType')
            comp  = el.find('{http://soap.sforce.com/2006/04/metadata}extensionName') or \
                    el.find('{http://soap.sforce.com/2006/04/metadata}componentType')
            if ftype is not None and ftype.text == 'ComponentInstance' and comp is not None:
                embedded.append(('lwc', comp.text.strip()))
    except Exception as e:
        print(f"WARN: parse error {e}", file=sys.stderr)
    return embedded

def find_omniscript_embedded(json_path):
    """Return embedded OmniScript/FlexCard references from OmniScript JSON."""
    embedded = []
    try:
        data = json.loads(Path(json_path).read_text())
        def walk(node):
            if isinstance(node, dict):
                t = node.get('type','').lower()
                if t in ('omniscript', 'omni_script', 'embeddedscript'):
                    name = node.get('propSetMap',{}).get('scriptName') or node.get('name','')
                    if name:
                        embedded.append(('omniscript', name))
                if t in ('flexcard', 'vlocitycard', 'flexcardinput'):
                    name = node.get('propSetMap',{}).get('cardName') or node.get('name','')
                    if name:
                        embedded.append(('flexcard', name))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(data)
    except Exception as e:
        print(f"WARN: parse error {e}", file=sys.stderr)
    return embedded

def find_flexcard_embedded(json_path):
    """Return embedded OmniScript/FlexCard references from FlexCard JSON."""
    embedded = []
    try:
        data = json.loads(Path(json_path).read_text())
        def walk(node):
            if isinstance(node, dict):
                t = (node.get('type','') or '').lower()
                if 'omniscript' in t or 'omni_script' in t:
                    name = node.get('name','') or node.get('scriptName','')
                    if name:
                        embedded.append(('omniscript', name))
                if 'flexcard' in t or 'vlocitycard' in t:
                    name = node.get('name','') or node.get('cardName','')
                    if name:
                        embedded.append(('flexcard', name))
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    walk(item)
        walk(data)
    except Exception as e:
        print(f"WARN: parse error {e}", file=sys.stderr)
    return embedded

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--file', required=True)
    parser.add_argument('--type', required=True, choices=['flow','omniscript','flexcard'])
    args = parser.parse_args()
    if args.type == 'flow':
        results = find_flow_embedded(args.file)
    elif args.type == 'omniscript':
        results = find_omniscript_embedded(args.file)
    else:
        results = find_flexcard_embedded(args.file)
    print(json.dumps(results))
```

Run for each retrieved component and collect all embedded references. Track a **visited set** to avoid infinite loops. For each new embedded component found, retrieve its metadata (Step 3b) and re-run `find_embedded.py` recursively.

Maintain a **component tree** (dict of component → list of children). Print the full tree to the user after all levels are resolved:
```
Component Tree:
  [Flow] CaseCreation_Flow
    └─ [Flow] SharedAddressCapture
    └─ [LWC] c:MyAddressInput
  [FlexCard] CaseSummaryCard
    └─ [OmniScript] OSCreateCase/Case/English
```

Tell the user how many total components were resolved and where all metadata files were saved.

---

## Step 4: Extract UI Elements from Metadata

Write the following Python script to `OUTPUT_DIR/scripts/extract_ui_elements.py` and run it:

```python
#!/usr/bin/env python3
"""
Extract all translatable UI text elements from Screen Flow, OmniScript, and FlexCard metadata.
Produces an Excel file with all identified labels/messages.

Usage:
  python3 extract_ui_elements.py \
    --metadata-dir OUTPUT_DIR/metadata \
    --component-tree PATH_TO_COMPONENT_TREE_JSON \
    --output OUTPUT_DIR/COMPONENT_NAME_ui_elements.xlsx
"""
import sys, json, argparse, xml.etree.ElementTree as ET
from pathlib import Path
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment

SF_NS = 'http://soap.sforce.com/2006/04/metadata'

# ── UI element categories ─────────────────────────────────────────────────────
# Each entry: (category, confidence)
# confidence: "certain" → always include; "review" → prompt user to confirm

def extract_flow_elements(xml_path, flow_name):
    """Extract all UI-visible text from a Flow XML file."""
    elements = []

    def tag(name): return f'{{{SF_NS}}}{name}'
    def text(el, child_name): 
        c = el.find(tag(child_name))
        return c.text.strip() if c is not None and c.text else ''

    try:
        root = ET.parse(xml_path).getroot()
    except Exception as e:
        return [{'component': flow_name, 'type': 'ERROR', 'location': str(xml_path),
                 'element_type': 'ParseError', 'label': str(e), 'confidence': 'skip'}]

    # ── Screens ───────────────────────────────────────────────────────────────
    for screen in root.findall(tag('screens')):
        screen_name = text(screen, 'name')
        screen_label = text(screen, 'label')
        screen_loc = f"{flow_name} > Screen:{screen_name}"

        if screen_label:
            elements.append({'component': flow_name, 'type': 'Screen Flow',
                             'location': screen_loc, 'element_type': 'Screen Title',
                             'label': screen_label, 'confidence': 'certain'})

        # Header / footer text
        for attr in ('headerText', 'footerText', 'header', 'footer', 'pausedText'):
            val = text(screen, attr)
            if val:
                elements.append({'component': flow_name, 'type': 'Screen Flow',
                                 'location': screen_loc, 'element_type': attr.replace('Text','').title(),
                                 'label': val, 'confidence': 'certain'})

        # Navigation button labels
        for btn in ('nextOrFinishButtonLabel', 'backButtonLabel', 'pauseButtonLabel',
                    'nextButtonLabel', 'finishButtonLabel'):
            val = text(screen, btn)
            if val:
                elements.append({'component': flow_name, 'type': 'Screen Flow',
                                 'location': screen_loc, 'element_type': 'Button Label',
                                 'label': val, 'confidence': 'certain'})

        # ── Screen fields ─────────────────────────────────────────────────────
        for field in screen.findall(tag('fields')):
            fname      = text(field, 'name')
            ftype      = text(field, 'fieldType')
            field_loc  = f"{screen_loc} > Field:{fname}"

            # ── DisplayText — HTML / rich-text blocks ─────────────────────────
            if ftype == 'DisplayText':
                # Direct text value
                fval = text(field, 'fieldText')
                if fval:
                    elements.append({'component': flow_name, 'type': 'Screen Flow',
                                     'location': field_loc, 'element_type': 'Display Text',
                                     'label': fval, 'confidence': 'certain'})

            # ── Input / Output fields ─────────────────────────────────────────
            for param in field.findall(tag('inputParameters')):
                param_name  = text(param, 'name')
                param_value = text(param, 'value') or (param.find(f'{{{SF_NS}}}value/{{{SF_NS}}}stringValue') or type('',(),{'text':''})()).text or ''
                str_val_el  = param.find(f'{{{SF_NS}}}value')
                if str_val_el is not None:
                    sv = str_val_el.find(tag('stringValue'))
                    if sv is not None and sv.text:
                        param_value = sv.text.strip()

                ui_params = {
                    'label':          ('Field Label',       'certain'),
                    'helpText':       ('Help Text',         'certain'),
                    'placeholder':    ('Placeholder Text',  'certain'),
                    'header':         ('Section Header',    'certain'),
                    'columnHeader':   ('Column Header',     'certain'),
                    'noItemsMessage': ('Empty State Msg',   'certain'),
                    'errorMessage':   ('Validation Error',  'certain'),
                    'message':        ('Message',           'certain'),
                    'title':          ('Title',             'certain'),
                    'description':    ('Description',       'review'),
                    'text':           ('Text',              'review'),
                    'content':        ('Content',           'review'),
                }
                if param_name in ui_params and param_value:
                    elem_type, conf = ui_params[param_name]
                    elements.append({'component': flow_name, 'type': 'Screen Flow',
                                     'location': f"{field_loc} > {param_name}",
                                     'element_type': elem_type, 'label': param_value,
                                     'confidence': conf})

            # Direct label/helpText on the field element itself
            for attr, etype, conf in [('fieldLabel', 'Field Label', 'certain'),
                                       ('helpText',   'Help Text',   'certain'),
                                       ('description','Description', 'review')]:
                val = text(field, attr)
                if val:
                    elements.append({'component': flow_name, 'type': 'Screen Flow',
                                     'location': f"{field_loc}", 'element_type': etype,
                                     'label': val, 'confidence': conf})

    # ── Choices ───────────────────────────────────────────────────────────────
    for choice in root.findall(tag('choices')):
        cname  = text(choice, 'name')
        clabel = text(choice, 'label') or text(choice, 'choiceText') or text(choice, 'value')
        if clabel:
            elements.append({'component': flow_name, 'type': 'Screen Flow',
                             'location': f"{flow_name} > Choice:{cname}",
                             'element_type': 'Choice Label', 'label': clabel,
                             'confidence': 'certain'})

    # ── Stages ────────────────────────────────────────────────────────────────
    for stage in root.findall(tag('stages')):
        slabel = text(stage, 'label')
        sname  = text(stage, 'name')
        if slabel:
            elements.append({'component': flow_name, 'type': 'Screen Flow',
                             'location': f"{flow_name} > Stage:{sname}",
                             'element_type': 'Stage Label', 'label': slabel,
                             'confidence': 'certain'})

    # ── Text Templates ────────────────────────────────────────────────────────
    for tmpl in root.findall(tag('textTemplates')):
        tname  = text(tmpl, 'name')
        ttext  = text(tmpl, 'text')
        if ttext and len(ttext) > 2:
            elements.append({'component': flow_name, 'type': 'Screen Flow',
                             'location': f"{flow_name} > TextTemplate:{tname}",
                             'element_type': 'Text Template', 'label': ttext,
                             'confidence': 'review'})

    # ── Custom Error Messages (fault connectors / recordCreate faults) ────────
    for el_type in ('recordCreates', 'recordUpdates', 'recordDeletes', 'recordLookups',
                    'actionCalls', 'decisions'):
        for el in root.findall(tag(el_type)):
            ename = text(el, 'name')
            for fault_attr in ('faultMessage', 'faultMessageText'):
                val = text(el, fault_attr)
                if val:
                    elements.append({'component': flow_name, 'type': 'Screen Flow',
                                     'location': f"{flow_name} > {el_type}:{ename}",
                                     'element_type': 'Error/Fault Message', 'label': val,
                                     'confidence': 'certain'})

    return elements


def extract_omniscript_elements(json_path, script_name):
    """Extract UI-visible text from an OmniScript PropertySet JSON."""
    elements = []
    try:
        data = json.loads(Path(json_path).read_text())
    except Exception as e:
        return [{'component': script_name, 'type': 'OmniScript', 'location': str(json_path),
                 'element_type': 'ParseError', 'label': str(e), 'confidence': 'skip'}]

    def walk(node, path=''):
        if isinstance(node, dict):
            ntype = (node.get('type','') or '').lower()
            pset  = node.get('propSetMap', node)   # some schemas embed props directly

            # ── Always-UI elements by element type ───────────────────────────
            ui_element_types = {
                'text':              ('Input Label',    'certain'),
                'heading':           ('Heading',        'certain'),
                'displaytext':       ('Display Text',   'certain'),
                'display text':      ('Display Text',   'certain'),
                'message':           ('Message',        'certain'),
                'paragraph':         ('Paragraph',      'certain'),
                'formula':           ('Formula Label',  'review'),
                'radio':             ('Radio Option',   'certain'),
                'checkbox':          ('Checkbox Label', 'certain'),
                'select':            ('Dropdown Label', 'certain'),
                'datepicker':        ('Date Label',     'certain'),
                'datetimepicker':    ('DateTime Label', 'certain'),
                'timepicker':        ('Time Label',     'certain'),
                'fileupload':        ('File Upload',    'certain'),
                'signature':         ('Signature',      'certain'),
                'teleinput':         ('Phone Label',    'certain'),
                'currency':          ('Currency Label', 'certain'),
                'lookuprecord':      ('Lookup Label',   'certain'),
                'step':              ('Step Name',      'certain'),
            }

            prop_map = {
                'label':            ('Label',           'certain'),
                'helpText':         ('Help Text',       'certain'),
                'help':             ('Help Text',       'certain'),
                'header':           ('Header',          'certain'),
                'placeholder':      ('Placeholder',     'certain'),
                'errorMsg':         ('Error Message',   'certain'),
                'errorMessage':     ('Error Message',   'certain'),
                'validationMessage':('Validation Msg',  'certain'),
                'message':          ('Message',         'certain'),
                'title':            ('Title',           'certain'),
                'text':             ('Text',            'review'),
                'confirmMessage':   ('Confirm Message', 'certain'),
                'cancelMessage':    ('Cancel Message',  'certain'),
                'noResultsText':    ('No Results Text', 'certain'),
                'emptyText':        ('Empty State',     'certain'),
                'successMsg':       ('Success Message', 'certain'),
                'info':             ('Info Text',       'review'),
                'note':             ('Note',            'review'),
                'tooltip':          ('Tooltip',         'certain'),
                'optionLabel':      ('Option Label',    'certain'),
                'tabName':          ('Tab Name',        'certain'),
                'tabLabel':         ('Tab Label',       'certain'),
            }

            nname = pset.get('name','') or node.get('name','')
            loc   = f"{script_name} > {path}/{nname}".replace('//','/')

            if ntype in ui_element_types:
                etype, conf = ui_element_types[ntype]
                for key, (ptype, pconf) in prop_map.items():
                    val = pset.get(key,'') or ''
                    if val and isinstance(val, str) and val.strip():
                        elements.append({'component': script_name, 'type': 'OmniScript',
                                         'location': f"{loc} > {key}",
                                         'element_type': ptype, 'label': val.strip(),
                                         'confidence': pconf})

            # ── Options / picklist values ─────────────────────────────────────
            for opt_key in ('options', 'choices', 'items', 'values'):
                opts = pset.get(opt_key, []) or []
                if isinstance(opts, list):
                    for i, opt in enumerate(opts):
                        if isinstance(opt, dict):
                            for label_key in ('label','name','text','value'):
                                v = opt.get(label_key,'')
                                if v and isinstance(v, str):
                                    elements.append({
                                        'component': script_name, 'type': 'OmniScript',
                                        'location': f"{loc} > {opt_key}[{i}]",
                                        'element_type': 'Option Label', 'label': v,
                                        'confidence': 'certain'})
                                    break

            # Recurse
            for k, v in node.items():
                if k not in ('propSetMap',):
                    walk(v, f"{path}/{nname}")
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(data)
    return elements


def extract_flexcard_elements(json_path, card_name):
    """Extract UI-visible text from a FlexCard definition JSON."""
    elements = []
    try:
        raw = Path(json_path).read_text()
        # FlexCard definitions can be double-encoded
        data = json.loads(raw)
        if isinstance(data, str):
            data = json.loads(data)
    except Exception as e:
        return [{'component': card_name, 'type': 'FlexCard', 'location': str(json_path),
                 'element_type': 'ParseError', 'label': str(e), 'confidence': 'skip'}]

    ui_props = {
        'label':            ('Label',          'certain'),
        'title':            ('Title',          'certain'),
        'header':           ('Header',         'certain'),
        'body':             ('Body Text',       'review'),
        'text':             ('Text',            'review'),
        'helpText':         ('Help Text',       'certain'),
        'placeholder':      ('Placeholder',     'certain'),
        'tooltip':          ('Tooltip',         'certain'),
        'message':          ('Message',         'certain'),
        'emptyLabel':       ('Empty Label',     'certain'),
        'noDataMessage':    ('No Data Message', 'certain'),
        'errorMessage':     ('Error Message',   'certain'),
        'stateName':        ('State Name',      'certain'),
        'actionLabel':      ('Action Label',    'certain'),
        'buttonLabel':      ('Button Label',    'certain'),
        'tabLabel':         ('Tab Label',       'certain'),
        'columnLabel':      ('Column Header',   'certain'),
        'fieldLabel':       ('Field Label',     'certain'),
    }

    def walk(node, path=''):
        if isinstance(node, dict):
            ntype = (node.get('type','') or '').lower()
            nname = node.get('name','') or node.get('id','')
            loc   = f"{card_name} > {path}/{nname}".replace('//','/')
            for prop, (etype, conf) in ui_props.items():
                val = node.get(prop,'')
                if val and isinstance(val, str) and val.strip() and \
                   not val.startswith('{!') and not val.startswith('$'):
                    elements.append({'component': card_name, 'type': 'FlexCard',
                                     'location': f"{loc} > {prop}",
                                     'element_type': etype, 'label': val.strip(),
                                     'confidence': conf})
            # Options/states
            for key in ('states', 'stateProperties', 'actions', 'columns', 'fields'):
                sub = node.get(key, []) or []
                if isinstance(sub, list):
                    for i, item in enumerate(sub):
                        walk(item, f"{path}/{nname}/{key}[{i}]")
                elif isinstance(sub, dict):
                    walk(sub, f"{path}/{nname}/{key}")
            for k,v in node.items():
                if k not in ui_props and k not in ('states','stateProperties','actions','columns','fields'):
                    walk(v, f"{path}/{nname}")
        elif isinstance(node, list):
            for item in node:
                walk(item, path)

    walk(data)
    return elements


def write_excel(elements, output_path):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "UI Elements"

    headers = ['Component','Type','Element Type','Location','Label / Text','Confidence','In Scope?']
    HDR = PatternFill("solid", fgColor="1F3864")
    HDR_FONT = Font(bold=True, color="FFFFFF")
    OK_FILL  = PatternFill("solid", fgColor="C6EFCE")
    REV_FILL = PatternFill("solid", fgColor="FFEB9C")
    SKP_FILL = PatternFill("solid", fgColor="DDDDDD")

    for j, h in enumerate(headers, 1):
        c = ws.cell(1, j, h)
        c.fill = HDR; c.font = HDR_FONT

    for i, el in enumerate(elements, 2):
        conf   = el.get('confidence','certain')
        in_scope = '' if conf == 'review' else ('Yes' if conf != 'skip' else 'Skip')
        fill   = OK_FILL if conf == 'certain' else (REV_FILL if conf == 'review' else SKP_FILL)
        row    = [el.get('component',''), el.get('type',''), el.get('element_type',''),
                  el.get('location',''), el.get('label',''), conf, in_scope]
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, v)
            c.fill = fill

    col_widths = [20, 12, 18, 55, 70, 10, 10]
    from openpyxl.utils import get_column_letter
    for j, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"

    # Summary tab
    ws2 = wb.create_sheet("Summary")
    from collections import Counter
    by_type = Counter(el.get('element_type','') for el in elements if el.get('confidence') != 'skip')
    by_conf = Counter(el.get('confidence','') for el in elements)
    ws2.append(['Element Type', 'Count'])
    for k,v in sorted(by_type.items(), key=lambda x: -x[1]):
        ws2.append([k, v])
    ws2.append([])
    ws2.append(['Confidence', 'Count'])
    for k,v in sorted(by_conf.items(), key=lambda x: -x[1]):
        ws2.append([k, v])

    wb.save(output_path)
    return len([e for e in elements if e.get('confidence') == 'certain']), \
           len([e for e in elements if e.get('confidence') == 'review']), \
           len([e for e in elements if e.get('confidence') == 'skip'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--metadata-dir', required=True)
    parser.add_argument('--component-tree', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()

    tree = json.loads(Path(args.component_tree).read_text())
    meta_dir = Path(args.metadata_dir)
    all_elements = []

    for entry in tree:
        cname = entry['name']
        ctype = entry['type'].lower()
        cfile = entry.get('file','')
        fpath = meta_dir / cfile if cfile else None

        # Search for file if not specified
        if fpath is None or not fpath.exists():
            if ctype == 'flow':
                candidates = list(meta_dir.rglob(f"{cname}.flow-meta.xml"))
                fpath = candidates[0] if candidates else None
            elif ctype == 'omniscript':
                candidates = list(meta_dir.rglob(f"{cname}_omniscript.json"))
                fpath = candidates[0] if candidates else None
            elif ctype in ('flexcard','omniflexcard'):
                candidates = list(meta_dir.rglob(f"{cname}_flexcard.json")) + \
                             list(meta_dir.rglob(f"{cname}.card-meta.json"))
                fpath = candidates[0] if candidates else None

        if fpath and fpath.exists():
            if ctype == 'flow':
                elems = extract_flow_elements(str(fpath), cname)
            elif ctype == 'omniscript':
                elems = extract_omniscript_elements(str(fpath), cname)
            else:
                elems = extract_flexcard_elements(str(fpath), cname)
            all_elements.extend(elems)
            print(f"  {cname} ({ctype}): {len(elems)} elements found")
        else:
            print(f"  WARN: No metadata file found for {cname} ({ctype})")

    certain, review, skip = write_excel(all_elements, args.output)
    print(f"\nTotal elements: {len(all_elements)}")
    print(f"  Certain (auto-included): {certain}")
    print(f"  Needs review:            {review}")
    print(f"  Skipped:                 {skip}")
    print(f"Output: {args.output}")
```

Build the component tree JSON file at `OUTPUT_DIR/component_tree.json` (list of
`{name, type, file}` objects) from Step 3c, then run:
```bash
python3 "OUTPUT_DIR/scripts/extract_ui_elements.py" \
  --metadata-dir "OUTPUT_DIR/metadata" \
  --component-tree "OUTPUT_DIR/component_tree.json" \
  --output "OUTPUT_DIR/COMPONENT_NAME_ui_elements.xlsx"
```

### 4a — User review of ambiguous elements

Open `OUTPUT_DIR/COMPONENT_NAME_ui_elements.xlsx` and show the user a summary:
```
Extracted UI elements:
  ✅  NNN elements auto-included (Field Labels, Button Labels, Error Messages, etc.)
  🔍  NNN elements flagged for your review (Text Templates, Descriptions, Body Text, etc.)
  ⏭   NNN elements skipped (ParseErrors, dynamic expressions)
```

For **review** items, print a numbered list of up to the first 30. Ask:
> "The following elements were flagged for review. Please confirm which should be included
> in the translation scope (enter comma-separated numbers, 'all', or 'none'):"

```
  1. [TextTemplate]  MyFlow > TextTemplate:WelcomeMsg
     Text: "Thank you for contacting us. We will..."
  2. [Description]   MyFlow > Screen:Intro > Field:disclaimer > description
     Text: "By continuing, you agree to our terms..."
```

Update the `In Scope?` column in the Excel for all confirmed items (set to "Yes") and
rejected items (set to "No"). Resave the file.

### 4b — Deduplicate

Remove exact duplicate label values across all components (keep one entry, note
duplicates in a `Duplicate Of` column). Print the final unique label count.

---

## Step 5: Match Labels Against Master Excel

Write the following Python script to `OUTPUT_DIR/scripts/match_master.py` and run it:

```python
#!/usr/bin/env python3
"""
Match extracted UI element labels against the master Excel translation sheet.

Master Excel structure:
  Col C (index 2) = English source text
  Col D (index 3) = Spanish translation
  Col E (index 4) = Portuguese (pt-BR) translation

Usage:
  python3 match_master.py \
    --ui-elements PATH_TO_ui_elements.xlsx \
    --master PATH_TO_MASTER.xlsx \
    --output PATH_TO_matches.json
"""
import argparse, json, re
from pathlib import Path
import openpyxl

def normalize(text):
    """Lowercase, collapse whitespace, strip punctuation for fuzzy matching."""
    if not text:
        return ''
    text = str(text).strip().lower()
    text = re.sub(r'\s+', ' ', text)
    return text

def load_master(master_path):
    wb = openpyxl.load_workbook(master_path, read_only=True, data_only=True)
    entries = []
    for ws in wb.worksheets:
        for row in ws.iter_rows(min_row=2, values_only=True):
            if row and len(row) >= 5:
                en = str(row[2]).strip() if row[2] else ''
                es = str(row[3]).strip() if row[3] else ''
                pt = str(row[4]).strip() if row[4] else ''
                if en:
                    entries.append({'en': en, 'es': es, 'pt': pt,
                                    'en_norm': normalize(en)})
    wb.close()
    return entries

def load_ui_elements(ui_path):
    wb = openpyxl.load_workbook(ui_path, read_only=True, data_only=True)
    ws = wb['UI Elements']
    elements = []
    for row in ws.iter_rows(min_row=2, values_only=True):
        if not row or not row[4]:
            continue
        in_scope = str(row[6] or '').strip().lower()
        if in_scope in ('no', 'skip'):
            continue
        elements.append({
            'component':    str(row[0] or ''),
            'type':         str(row[1] or ''),
            'element_type': str(row[2] or ''),
            'location':     str(row[3] or ''),
            'label':        str(row[4] or '').strip(),
            'confidence':   str(row[5] or ''),
        })
    wb.close()
    return elements

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--ui-elements', required=True)
    parser.add_argument('--master',      required=True)
    parser.add_argument('--output',      required=True)
    args = parser.parse_args()

    master   = load_master(args.master)
    elements = load_ui_elements(args.ui_elements)
    master_norm = {e['en_norm']: e for e in master}

    matched   = []
    unmatched = []

    for el in elements:
        label      = el['label']
        label_norm = normalize(label)
        m = master_norm.get(label_norm)
        if m:
            matched.append({**el, 'es': m['es'], 'pt': m['pt'],
                            'master_en': m['en'], 'match_type': 'exact'})
        else:
            # Partial / substring match
            best = None
            best_score = 0
            for entry in master:
                if label_norm in entry['en_norm'] or entry['en_norm'] in label_norm:
                    score = min(len(label_norm), len(entry['en_norm'])) / \
                            max(len(label_norm), len(entry['en_norm']), 1)
                    if score > best_score and score >= 0.85:
                        best_score = score
                        best = entry
            if best:
                matched.append({**el, 'es': best['es'], 'pt': best['pt'],
                                'master_en': best['en'], 'match_type': f'partial({best_score:.0%})'})
            else:
                unmatched.append({**el, 'es': '', 'pt': '', 'master_en': '', 'match_type': 'none'})

    result = {'matched': matched, 'unmatched': unmatched}
    Path(args.output).write_text(json.dumps(result, indent=2, ensure_ascii=False))

    print(f"Matched:   {len(matched)}")
    print(f"Unmatched: {len(unmatched)}")
    print(f"Output:    {args.output}")
```

Run:
```bash
python3 "OUTPUT_DIR/scripts/match_master.py" \
  --ui-elements "OUTPUT_DIR/COMPONENT_NAME_ui_elements.xlsx" \
  --master      "MASTER_PATH" \
  --output      "OUTPUT_DIR/COMPONENT_NAME_matches.json"
```

Report the printed summary (matched count, unmatched count).

---

## Step 6: Generate STF Translation Files

Write the following Python script to `OUTPUT_DIR/scripts/generate_stf.py` and run it:

```python
#!/usr/bin/env python3
"""
Generate Salesforce STF translation files for Screen Flow, OmniScript, and FlexCard
UI elements from the matches JSON produced by match_master.py.

For Screen Flows: generates FlowDefinition-type STF entries.
For OmniScripts / FlexCards: generates CustomLabel-type STF entries
  (since Omni components require custom labels for Translation Workbench).

Produces three STF files per run:
  - COMPONENT_NAME_es_CO.stf   — Spanish (Colombia)
  - COMPONENT_NAME_es_MX.stf   — Spanish (Mexico)
  - COMPONENT_NAME_pt_BR.stf   — Portuguese (Brazil)

Both Spanish variants use the same Spanish translation column (Col D) from the master
sheet; only the language code in the STF header differs.

Usage:
  python3 generate_stf.py \
    --matches PATH_TO_matches.json \
    --component-name NAME \
    --output-dir OUTPUT_DIR \
    [--existing-es-co PATH] [--existing-es-mx PATH] [--existing-pt-br PATH]
"""
import argparse, json, re
from pathlib import Path
from datetime import datetime

def load_existing_stf_keys(stf_path):
    """Return set of already-translated keys from an existing bilingual STF."""
    keys = set()
    if not stf_path or not Path(stf_path).exists():
        return keys
    in_block = False
    for line in Path(stf_path).read_text(encoding='utf-8', errors='replace').splitlines():
        line = line.strip()
        if line.startswith('---'):
            in_block = True
            continue
        if in_block and '\t' in line and not line.startswith('#'):
            parts = line.split('\t')
            if len(parts) >= 2 and parts[1].strip():
                keys.add(parts[0].strip().lower())
    return keys

def sanitize_stf_label(text):
    return re.sub(r'[\r\n\t]', ' ', text).strip()

def generate_stf_flow(matched, component_name, existing_keys, master_lang_key, lang_code, lang_label):
    """
    Generate STF lines for Screen Flow translations.
    STF format for flows:
      # FlowDefinition
      ---
      # FLOW_API_NAME
      # FlowScreen
      # SCREEN_NAME
      # FlowScreenField
      # FIELD_NAME
      ENGLISH_LABEL<TAB>TRANSLATED_LABEL
    """
    lines = [f"# Salesforce Translation File",
             f"# Component: {component_name}",
             f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"# Language: {lang_label} ({lang_code})",
             f"# Type: FlowDefinition", ""]

    by_location = {}
    for m in matched:
        label  = m.get('label','').strip()
        transl = m.get(master_lang_key,'').strip()
        key    = label.lower()
        if not label or not transl:
            continue
        if key in existing_keys:
            continue
        loc  = m.get('location','')
        by_location.setdefault(loc, []).append((label, transl))

    for loc, pairs in sorted(by_location.items()):
        parts = loc.split(' > ')
        lines.append(f"# {' > '.join(parts)}")
        lines.append("---")
        for label, transl in pairs:
            lines.append(f"{sanitize_stf_label(label)}\t{sanitize_stf_label(transl)}")
        lines.append("")

    return '\n'.join(lines)

def generate_stf_custom_labels(matched, component_name, existing_keys, master_lang_key, lang_code, lang_label):
    """
    Generate CustomLabel STF entries for OmniScript / FlexCard elements.
    STF format for custom labels:
      # CustomLabel
      ---
      LABEL_API_NAME
      MASTER_LABEL<TAB>TRANSLATION
    """
    lines = [f"# Salesforce Translation File",
             f"# Component: {component_name}",
             f"# Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"# Language: {lang_label}",
             f"Language code: {lang_code}",
             f"# Type: CustomLabel", ""]

    for m in matched:
        label  = m.get('label','').strip()
        transl = m.get(master_lang_key,'').strip()
        key    = label.lower()
        if not label or not transl:
            continue
        if key in existing_keys:
            continue
        api_name = re.sub(r'[^a-zA-Z0-9_]', '_', label[:40]).strip('_')
        lines.append(f"# {m.get('location','')}")
        lines.append("---")
        lines.append(api_name)
        lines.append(f"{sanitize_stf_label(label)}\t{sanitize_stf_label(transl)}")
        lines.append("")

    return '\n'.join(lines)

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--matches',          required=True)
    parser.add_argument('--component-name',   required=True)
    parser.add_argument('--output-dir',       required=True)
    parser.add_argument('--existing-es-co',   default='')
    parser.add_argument('--existing-es-mx',   default='')
    parser.add_argument('--existing-pt-br',   default='')
    args = parser.parse_args()

    data    = json.loads(Path(args.matches).read_text())
    matched = data.get('matched', [])
    out_dir = Path(args.output_dir)

    existing_es_co = load_existing_stf_keys(args.existing_es_co)
    existing_es_mx = load_existing_stf_keys(args.existing_es_mx)
    existing_pt_br = load_existing_stf_keys(args.existing_pt_br)

    # Determine majority component type
    from collections import Counter
    type_counts  = Counter(m.get('type','').lower() for m in matched)
    primary_type = type_counts.most_common(1)[0][0] if type_counts else 'flow'

    cname      = args.component_name
    es_co_out  = out_dir / f"{cname}_es_CO.stf"
    es_mx_out  = out_dir / f"{cname}_es_MX.stf"
    pt_br_out  = out_dir / f"{cname}_pt_BR.stf"

    # Both Spanish variants use Col D ('es') from the master sheet.
    # Portuguese (Brazil) uses Col E ('pt').
    if 'flow' in primary_type:
        es_co_content = generate_stf_flow(matched, cname, existing_es_co, 'es', 'es_CO', 'Spanish (Colombia)')
        es_mx_content = generate_stf_flow(matched, cname, existing_es_mx, 'es', 'es_MX', 'Spanish (Mexico)')
        pt_br_content = generate_stf_flow(matched, cname, existing_pt_br, 'pt', 'pt_BR', 'Portuguese (Brazil)')
    else:
        es_co_content = generate_stf_custom_labels(matched, cname, existing_es_co, 'es', 'es_CO', 'Spanish (Colombia)')
        es_mx_content = generate_stf_custom_labels(matched, cname, existing_es_mx, 'es', 'es_MX', 'Spanish (Mexico)')
        pt_br_content = generate_stf_custom_labels(matched, cname, existing_pt_br, 'pt', 'pt_BR', 'Portuguese (Brazil)')

    es_co_out.write_text(es_co_content, encoding='utf-8')
    es_mx_out.write_text(es_mx_content, encoding='utf-8')
    pt_br_out.write_text(pt_br_content, encoding='utf-8')

    print(f"STF generated:")
    print(f"  Spanish (Colombia) es_CO  ({es_co_content.count(chr(9))} entries): {es_co_out}")
    print(f"  Spanish (Mexico)   es_MX  ({es_mx_content.count(chr(9))} entries): {es_mx_out}")
    print(f"  Portuguese (Brazil) pt_BR ({pt_br_content.count(chr(9))} entries): {pt_br_out}")
    print(f"  Already-translated keys skipped: es_CO={len(existing_es_co)}  es_MX={len(existing_es_mx)}  pt_BR={len(existing_pt_br)}")
```

Build the command — include `--existing-*` flags only if the user provided the corresponding STF:
```bash
python3 "OUTPUT_DIR/scripts/generate_stf.py" \
  --matches          "OUTPUT_DIR/COMPONENT_NAME_matches.json" \
  --component-name   "COMPONENT_NAME" \
  --output-dir       "OUTPUT_DIR" \
  [--existing-es-co  "EXISTING_ES_CO"] \
  [--existing-es-mx  "EXISTING_ES_MX"] \
  [--existing-pt-br  "EXISTING_PT_BR"]
```

Report the printed summary (es_CO entries, es_MX entries, pt_BR entries, skipped keys per language).

---

## Step 7: Generate Miss Report

Write the following Python script to `OUTPUT_DIR/scripts/miss_report.py` and run it:

```python
#!/usr/bin/env python3
"""
Generate a CSV miss report of UI elements with no translation found in the master sheet.

Usage:
  python3 miss_report.py \
    --matches PATH_TO_matches.json \
    --component-name NAME \
    --output-dir OUTPUT_DIR
"""
import argparse, json, csv
from pathlib import Path

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--matches',        required=True)
    parser.add_argument('--component-name', required=True)
    parser.add_argument('--output-dir',     required=True)
    args = parser.parse_args()

    data      = json.loads(Path(args.matches).read_text())
    unmatched = data.get('unmatched', [])
    matched   = data.get('matched',   [])

    out_dir = Path(args.output_dir)
    miss_path = out_dir / f"{args.component_name}_miss_report.csv"

    with miss_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=[
            'Jira/Component', 'Type', 'Element Type', 'Location', 'English Label',
            'Reason', 'Suggested Action'
        ])
        writer.writeheader()
        for el in unmatched:
            writer.writerow({
                'Jira/Component':   el.get('component',''),
                'Type':             el.get('type',''),
                'Element Type':     el.get('element_type',''),
                'Location':         el.get('location',''),
                'English Label':    el.get('label',''),
                'Reason':           'No match found in master Excel',
                'Suggested Action': 'Add to master Excel (Col C=English, Col D=Spanish, Col E=Portuguese (Brazil)) and re-run'
            })

    # Partial-match entries
    partial_path = out_dir / f"{args.component_name}_partial_matches.csv"
    partials = [m for m in matched if 'partial' in m.get('match_type','')]
    if partials:
        with partial_path.open('w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=[
                'Component', 'Type', 'Element Type', 'Location',
                'UI Label', 'Matched Master English', 'Match Quality',
                'Spanish (es_CO / es_MX)', 'Portuguese (pt_BR)'
            ])
            writer.writeheader()
            for m in partials:
                writer.writerow({
                    'Component':               m.get('component',''),
                    'Type':                    m.get('type',''),
                    'Element Type':            m.get('element_type',''),
                    'Location':                m.get('location',''),
                    'UI Label':                m.get('label',''),
                    'Matched Master English':  m.get('master_en',''),
                    'Match Quality':           m.get('match_type',''),
                    'Spanish (es_CO / es_MX)': m.get('es',''),
                    'Portuguese (pt_BR)':       m.get('pt',''),
                })
        print(f"Partial matches: {len(partials)} entries → {partial_path}")

    print(f"Miss report: {len(unmatched)} unmatched entries → {miss_path}")
```

Run:
```bash
python3 "OUTPUT_DIR/scripts/miss_report.py" \
  --matches        "OUTPUT_DIR/COMPONENT_NAME_matches.json" \
  --component-name "COMPONENT_NAME" \
  --output-dir     "OUTPUT_DIR"
```

---

## Step 8: Verify Missing Labels Against Org and Generate Custom Label Deployment Files

Take the unmatched labels from the miss report and check whether each one **already
exists in the org** as a Custom Label by exact-matching its English text against the
`Value` field of every `ExternalString` record in the org.

Only labels whose value does **not** already exist in the org are written to the
deployment XML. Labels that are already present (under any API name) are noted in the
review Excel but excluded from the XML.

Write the following Python script to `OUTPUT_DIR/scripts/verify_and_gen_labels.py`
and run it:

```python
#!/usr/bin/env python3
"""
Verify unmatched UI labels against existing Custom Labels in the org (exact value match).
Generates a deployable labels-meta.xml and a review Excel only for truly new labels.

Usage:
  python3 verify_and_gen_labels.py \
    --matches        PATH_TO_matches.json \
    --component-name COMPONENT_NAME \
    --output-dir     OUTPUT_DIR \
    --target-org     SELECTED_ORG
"""
import argparse, json, re, subprocess, sys
from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter


def query_org_custom_label_values(target_org):
    """
    Return a dict { value_lower_stripped: api_name } for every Custom Label in the org.
    Uses the Tooling API (ExternalString). Falls back to standard SOQL if Tooling fails.
    """
    soql = "SELECT Name, Value FROM ExternalString LIMIT 50000"

    # Try Tooling API first
    for use_tooling in (True, False):
        cmd = [
            "sf", "data", "query",
            "--query", soql,
            "--target-org", target_org,
            "--json",
        ]
        if use_tooling:
            cmd.append("--use-tooling-api")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            data = json.loads(result.stdout or "{}")
            records = (data.get("result", {}) or {}).get("records", [])
            if records or data.get("status") == 0:
                lookup = {}
                for rec in records:
                    val = (rec.get("Value") or "").strip()
                    name = rec.get("Name", "")
                    if val:
                        lookup[val.lower()] = name
                print(f"  Loaded {len(lookup)} existing Custom Label values from org "
                      f"({'Tooling' if use_tooling else 'Standard'} API)")
                return lookup
        except Exception as e:
            print(f"  WARN: query attempt failed ({e})", file=sys.stderr)

    print("  WARN: Could not load Custom Labels from org — all unmatched treated as new",
          file=sys.stderr)
    return {}


def derive_api_name(text):
    """Derive a valid Custom Label API name from free text (max 40 chars)."""
    name = re.sub(r'[^a-zA-Z0-9_]', '_', text[:40])
    name = re.sub(r'_+', '_', name).strip('_')
    return name or "Label"


def generate_labels_xml(new_labels, component_name):
    """Build a CustomLabels metadata XML string."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<CustomLabels xmlns="http://soap.sforce.com/2006/04/metadata">',
    ]
    for lbl in new_labels:
        short_desc = escape(lbl['value'][:80])
        value_esc  = escape(lbl['value'])
        lines += [
            '    <labels>',
            f'        <fullName>{lbl["api_name"]}</fullName>',
            f'        <categories>ScreenFlow:{escape(component_name)}</categories>',
            '        <language>en_US</language>',
            '        <protected>false</protected>',
            f'        <shortDescription>{short_desc}</shortDescription>',
            f'        <value>{value_esc}</value>',
            '    </labels>',
        ]
    lines.append('</CustomLabels>')
    return '\n'.join(lines)


def write_review_excel(all_labels, output_path):
    """
    Write a review Excel with columns:
      API Name | English Value | Status | Existing API Name
    Colour coding:
      Green  — truly new (will be in XML)
      Yellow — already exists in org (excluded from XML)
    """
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Custom Labels Review"

    headers  = ['API Name', 'English Value', 'Status', 'Existing API Name in Org']
    HDR_FILL = PatternFill("solid", fgColor="1F3864")
    HDR_FONT = Font(bold=True, color="FFFFFF")
    NEW_FILL = PatternFill("solid", fgColor="C6EFCE")   # green  — new
    EXI_FILL = PatternFill("solid", fgColor="FFEB9C")   # yellow — exists

    for j, h in enumerate(headers, 1):
        c = ws.cell(1, j, h)
        c.fill = HDR_FILL
        c.font = HDR_FONT

    for i, lbl in enumerate(all_labels, 2):
        is_new = lbl['status'] == 'New'
        fill   = NEW_FILL if is_new else EXI_FILL
        row    = [lbl['api_name'], lbl['value'], lbl['status'],
                  lbl.get('existing_api_name', '')]
        for j, v in enumerate(row, 1):
            c = ws.cell(i, j, v)
            c.fill = fill

    col_widths = [35, 70, 20, 35]
    for j, w in enumerate(col_widths, 1):
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.freeze_panes = "A2"
    wb.save(output_path)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--matches',        required=True)
    parser.add_argument('--component-name', required=True)
    parser.add_argument('--output-dir',     required=True)
    parser.add_argument('--target-org',     required=True)
    args = parser.parse_args()

    data      = json.loads(Path(args.matches).read_text())
    unmatched = data.get('unmatched', [])
    out_dir   = Path(args.output_dir)
    cname     = args.component_name

    if not unmatched:
        print("No unmatched labels — skipping Custom Label generation.")
        sys.exit(0)

    print(f"Checking {len(unmatched)} unmatched label(s) against org Custom Label values...")
    org_lookup = query_org_custom_label_values(args.target_org)

    all_labels  = []   # for review Excel (all unmatched)
    new_labels  = []   # for XML (truly missing from org)

    for el in unmatched:
        label     = (el.get('label') or '').strip()
        label_key = label.lower()
        api_name  = derive_api_name(label)

        if label_key in org_lookup:
            existing_name = org_lookup[label_key]
            all_labels.append({
                'api_name':         api_name,
                'value':            label,
                'status':           'Exists in Org',
                'existing_api_name': existing_name,
            })
        else:
            all_labels.append({
                'api_name':         api_name,
                'value':            label,
                'status':           'New',
                'existing_api_name': '',
            })
            new_labels.append({'api_name': api_name, 'value': label})

    # Write review Excel
    review_path = out_dir / f"{cname}_new_custom_labels_review.xlsx"
    write_review_excel(all_labels, str(review_path))
    print(f"Review Excel   : {review_path}")

    # Write XML only if there are truly new labels
    if new_labels:
        xml_path = out_dir / f"{cname}_new_custom_labels.labels-meta.xml"
        xml_path.write_text(generate_labels_xml(new_labels, cname), encoding='utf-8')
        print(f"Deployment XML : {xml_path}  ({len(new_labels)} new label(s))")
    else:
        print("All unmatched labels already exist in the org — no XML generated.")

    exists_count = len(all_labels) - len(new_labels)
    print(f"\nSummary:")
    print(f"  Unmatched labels checked : {len(unmatched)}")
    print(f"  Already exist in org     : {exists_count}  (excluded from XML)")
    print(f"  Truly new (added to XML) : {len(new_labels)}")
```

Run:
```bash
python3 "OUTPUT_DIR/scripts/verify_and_gen_labels.py" \
  --matches        "OUTPUT_DIR/COMPONENT_NAME_matches.json" \
  --component-name "COMPONENT_NAME" \
  --output-dir     "OUTPUT_DIR" \
  --target-org     "SELECTED_ORG"
```

If `_new_custom_labels.labels-meta.xml` was generated, tell the user:
> **Action required before importing the STF files:**
> 1. Review `COMPONENT_NAME_new_custom_labels_review.xlsx`:
>    - **Green rows** — new Custom Labels that will be deployed (verify API names look correct)
>    - **Yellow rows** — labels already present in the org under the shown API name (no action needed)
> 2. Deploy the new Custom Labels to the org:
>    `sf project deploy start --source-dir path/to/force-app/main/default/customLabels/`
> 3. Then import the STF files into Translation Workbench.

---

## Final Summary

Tell the user:

```
Translation files generated for [COMPONENT_NAME(S)]:

  Component Analysis:
    OUTPUT_DIR/component_tree.json                      — Full component hierarchy (N levels deep)
    OUTPUT_DIR/COMPONENT_NAME_ui_elements.xlsx          — All UI elements extracted (certain + reviewed)
    OUTPUT_DIR/COMPONENT_NAME_matches.json              — Internal match data

  Translation Files (import into Translation Workbench):
    OUTPUT_DIR/COMPONENT_NAME_es_CO.stf                 — Spanish (Colombia) translations  (N entries)
    OUTPUT_DIR/COMPONENT_NAME_es_MX.stf                 — Spanish (Mexico) translations    (N entries)
    OUTPUT_DIR/COMPONENT_NAME_pt_BR.stf                 — Portuguese (Brazil) translations (N entries)

  Review Items:
    OUTPUT_DIR/COMPONENT_NAME_miss_report.csv                   — Labels with no translation found (N items)
    OUTPUT_DIR/COMPONENT_NAME_partial_matches.csv               — Partial matches needing human review (N items)
    OUTPUT_DIR/COMPONENT_NAME_new_custom_labels_review.xlsx     — Custom label org-check results (green=new, yellow=already exists)
    [if any new labels were found:]
    OUTPUT_DIR/COMPONENT_NAME_new_custom_labels.labels-meta.xml — Deploy to org BEFORE importing STF files

  Metadata Files:
    OUTPUT_DIR/metadata/                                — All retrieved flow/omni/flexcard XML/JSON

Counts:
  - Components resolved:              N (including N embedded)
  - UI elements extracted:            N (N certain + N reviewed in-scope)
  - Matched to master:                N  (N exact + N partial)
  - Missing translations:             N  → add to master Excel and re-run
  - Unmatched labels checked vs org:  N  (N already exist in org, N truly new)
  - Skipped (excluded):               N

To import translations into Salesforce:
  1. [If new custom labels XML was generated] Deploy custom labels first:
     sf project deploy start --source-dir path/to/customLabels/
  2. Log in to Setup → Translation Workbench → Import
  3. Import all three .stf files (es_CO, es_MX, pt_BR)
```

If any `unmatched` items exist, add:
> **Action required:** N labels have no translation in the master Excel.
> See `COMPONENT_NAME_miss_report.csv` — add the missing entries to the master sheet
> (Col C = English, Col D = Spanish, Col E = Portuguese (Brazil)) and re-run from Step 5.
