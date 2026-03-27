#!/usr/bin/env python3
"""
Fetches Salesforce metadata files from a GitHub repo for a given component,
parses them, and returns structured JSON for documentation generation.

Usage:
  python3 fetch_metadata.py \
    --repo owner/repo \
    --branch tst \
    --token ghp_xxx \
    --component "Lock Unlock Omniscript" \
    --output /path/to/output.json
"""
import argparse
import base64
import json
import os
import re
import sys
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET


# ── GitHub API helpers ────────────────────────────────────────────────────────

def github_api_get(url, token=None):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github.v3+json")
    req.add_header("User-Agent", "sf-document-skill/1.0")
    if token:
        req.add_header("Authorization", f"token {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"ERROR: GitHub API {e.code} for {url}", file=sys.stderr)
        if e.code == 401:
            print("  Invalid or missing GitHub token. Provide --token with 'repo' scope.", file=sys.stderr)
        elif e.code == 403:
            print("  Access denied. Repo is private — provide a valid --token.", file=sys.stderr)
            msg = json.loads(body).get("message", "") if body.startswith("{") else ""
            if "rate limit" in msg.lower():
                print("  GitHub rate limit hit. Provide --token to increase limits.", file=sys.stderr)
        elif e.code == 404:
            print(f"  Not found. Check repo name and branch.", file=sys.stderr)
        else:
            print(f"  Response: {body[:200]}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


def get_repo_tree(owner, repo, branch, token):
    """Get full recursive file tree."""
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{branch}?recursive=1"
    data = github_api_get(url, token)
    truncated = data.get("truncated", False)
    if truncated:
        print("  WARNING: Repo tree was truncated by GitHub (>100k files). Some files may be missed.", file=sys.stderr)
    return data.get("tree", [])


def download_file(owner, repo, path, branch, token):
    """Download a file from GitHub and return its text content."""
    encoded = urllib.parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{encoded}?ref={branch}"
    data = github_api_get(url, token)
    if "content" in data:
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None
    return None


# ── File classification ───────────────────────────────────────────────────────

METADATA_TYPES = [
    (".os-meta.xml",                "OmniScript"),
    (".oip-meta.xml",               "IntegrationProcedure"),
    (".rpt-meta.xml",               "DataRaptor"),
    (".cls-meta.xml",               "ApexClass_Meta"),
    (".cls",                        "ApexClass"),
    (".flow-meta.xml",              "Flow"),
    (".js",                         "LWC_JS"),
    (".html",                       "LWC_HTML"),
    (".md-meta.xml",                "CustomMetadata"),
    (".validationRule-meta.xml",    "ValidationRule"),
    (".layout-meta.xml",            "Layout"),
    (".flexipage-meta.xml",         "Flexipage"),
    (".permissionset-meta.xml",     "PermissionSet"),
    (".permissionsetgroup-meta.xml","PermissionSetGroup"),
]


def classify_file(filepath):
    lower = filepath.lower()
    for ext, ftype in METADATA_TYPES:
        if lower.endswith(ext):
            return ftype
    return None


# ── Keyword scoring ───────────────────────────────────────────────────────────

STOP_WORDS = {"the", "a", "an", "and", "or", "for", "to", "of", "in", "on", "with"}


def keywords_from_name(component_name):
    words = re.split(r"[\s/\-_]+", component_name.lower())
    return [w for w in words if w and w not in STOP_WORDS and len(w) > 1]


TYPE_PRIORITY = {
    "OmniScript":          3,
    "IntegrationProcedure":3,
    "DataRaptor":          3,
    "CustomMetadata":      3,
    "Flow":                3,
    "ValidationRule":      3,
    "ApexClass":           2,
    "Layout":              2,
    "Flexipage":           2,
    "PermissionSet":       2,
    "PermissionSetGroup":  2,
    "LWC_JS":              1,
    "LWC_HTML":            0,
    "ApexClass_Meta":      0,
}

# Generated LWC framework files — no doc value
SKIP_BASENAMES = {"definition.js", "styledefinition.js"}


def score_file(filepath, keywords):
    lower = filepath.lower()
    basename = os.path.basename(lower)
    if basename in SKIP_BASENAMES:
        return 0
    ftype = classify_file(filepath)
    if ftype == "LWC_HTML":
        return 0  # HTML templates add noise; LWC_JS is sufficient
    keyword_score = sum(1 for kw in keywords if kw in lower)
    ftype = classify_file(filepath)
    priority = TYPE_PRIORITY.get(ftype, 1)
    return keyword_score * priority if keyword_score > 0 else 0


# ── XML namespace helper ──────────────────────────────────────────────────────

def strip_ns(tag):
    return tag.split("}")[-1] if "}" in tag else tag


def iter_tag_text(root):
    """Yield (tag, text) for all elements with non-empty text."""
    for el in root.iter():
        text = (el.text or "").strip()
        if text:
            yield strip_ns(el.tag).lower(), text


# ── Parsers ───────────────────────────────────────────────────────────────────

def _extract_propertyset_refs(root):
    """
    OmniScript/IP elements store their configuration as JSON inside
    <propertySetConfig> XML elements.  Extract all relevant references.
    Returns: (ips, drs, lwcs, apex_classes, named_credentials)
    """
    ips, drs, lwcs, apex, creds = set(), set(), set(), set(), set()
    for el in root.iter():
        if strip_ns(el.tag).lower() not in ("propertysetconfig", "propertyset"):
            continue
        text = (el.text or "").strip()
        if not text:
            continue
        try:
            cfg = json.loads(text)
        except Exception:
            cfg = {}

        def _get(key):
            v = cfg.get(key)
            if v and isinstance(v, str):
                return v
            m = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]+)"', text)
            return m.group(1) if m else None

        def _get_nested(obj, *keys):
            for k in keys:
                if not isinstance(obj, dict):
                    return None
                obj = obj.get(k)
            return obj if isinstance(obj, str) else None

        bundle = _get("bundle")
        if bundle:
            drs.add(bundle)

        ip = _get("integrationProcedureKey")
        if ip:
            ips.add(ip)

        lwc = _get("lwcName")
        if lwc:
            lwcs.add(lwc)

        # Apex Remote Action: remoteClass
        remote_class = _get("remoteClass")
        if remote_class:
            apex.add(remote_class)

        # Named Credential: remoteOptions.metadataName
        meta_name = _get_nested(cfg, "remoteOptions", "metadataName")
        if not meta_name:
            meta_name = _get("metadataName")
        if meta_name:
            creds.add(meta_name)

        # Sub-procedure key
        sub_ip = _get("subIntegrationProcedureKey") or _get("iProcedureKey")
        if sub_ip:
            ips.add(sub_ip)

    return sorted(ips), sorted(drs), sorted(lwcs), sorted(apex), sorted(creds)


def parse_omniscript(content, filepath):
    result = {
        "type": "OmniScript",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".os-meta.xml", ""),
        "label": "",
        "description": "",
        "element_types": [],
        "integration_procedures": [],
        "dataraptors": [],
        "lwc_components": [],
        "apex_classes": [],
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "label" and not result["label"]:
            result["label"] = text
        elif tag == "description" and not result["description"]:
            result["description"] = text
        elif tag in ("type", "elementtype") and text not in ("true", "false"):
            result["element_types"].append(text)
        elif tag == "name" and not result["label"]:
            result["label"] = text

    # Primary source: propertySetConfig JSON blobs
    ips, drs, lwcs, apex, creds = _extract_propertyset_refs(root)
    result["integration_procedures"] = ips
    result["dataraptors"] = drs
    result["lwc_components"] = lwcs
    result["apex_classes"] = apex

    result["element_types"] = sorted(set(result["element_types"]))
    return result


def parse_integration_procedure(content, filepath):
    result = {
        "type": "IntegrationProcedure",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".oip-meta.xml", ""),
        "label": "",
        "description": "",
        "is_active": True,
        "element_types": [],
        "apex_classes": [],
        "named_credentials": [],
        "dataraptors": [],
        "sub_procedures": [],
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "label" and not result["label"]:
            result["label"] = text
        elif tag == "description" and not result.get("description"):
            result["description"] = text
        elif tag == "name" and not result["label"]:
            result["label"] = text
        elif tag in ("isactive", "active"):
            result["is_active"] = text.lower() not in ("false", "0", "no")
        elif tag in ("type", "elementtype") and text not in ("true", "false"):
            result["element_types"].append(text)

    # Extract refs from propertySetConfig JSON
    ips, drs, lwcs, apex, creds = _extract_propertyset_refs(root)
    result["sub_procedures"] = ips
    result["dataraptors"] = drs
    result["apex_classes"] = apex
    result["named_credentials"] = creds

    result["element_types"] = sorted(set(result["element_types"]))
    return result


def parse_dataraptor(content, filepath):
    result = {
        "type": "DataRaptor",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".rpt-meta.xml", ""),
        "label": "",
        "dr_type": "",
        "objects": [],
        "operations": [],
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "label" and not result["label"]:
            result["label"] = text
        elif tag in ("type", "interfacetype", "drtype", "dataraptoraction"):
            result["dr_type"] = result["dr_type"] or text
        elif tag in ("objectname", "sobjecttype", "targetobjecttype", "sourceobjecttype"):
            result["objects"].append(text)
        elif tag in ("operation", "actiontype"):
            result["operations"].append(text)

    result["objects"] = sorted(set(result["objects"]))
    result["operations"] = sorted(set(result["operations"]))
    return result


def parse_apex_class(content, filepath):
    result = {
        "type": "ApexClass",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".cls", ""),
        "implements": [],
        "extends": "",
        "named_credentials": [],
        "has_http_callout": False,
        "key_methods": [],
    }

    # Class declaration
    m = re.search(r"\bclass\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+([\w\s,]+))?", content, re.IGNORECASE)
    if m:
        result["name"] = m.group(1)
        if m.group(2):
            result["extends"] = m.group(2)
        if m.group(3):
            result["implements"] = [i.strip() for i in m.group(3).split(",")]

    # Named credentials: callout:CredName
    result["named_credentials"] = sorted(set(re.findall(r"callout:(\w+)", content)))

    # HTTP callout
    result["has_http_callout"] = bool(re.search(r"\bHttpRequest\b|\bHttp\s*\(", content))

    # Public methods
    methods = re.findall(r"\b(?:public|global)\s+(?:static\s+)?(?:[\w<>\[\]]+)\s+(\w+)\s*\(", content)
    result["key_methods"] = sorted(set(methods))[:10]  # cap at 10

    return result


def parse_lwc_js(content, filepath):
    result = {
        "type": "LWC_JS",
        "filepath": filepath,
        "name": "",
        "apex_imports": [],
        "lwc_imports": [],
        "wire_adapters": [],
        "pubsub_events": [],
    }

    # Derive LWC name from path: .../lwc/componentName/componentName.js
    parts = filepath.replace("\\", "/").split("/")
    for i, part in enumerate(parts):
        if part == "lwc" and i + 1 < len(parts):
            result["name"] = parts[i + 1]
            break

    imports = re.findall(r"import\s+.+?\s+from\s+'([^']+)'", content)
    for imp in imports:
        if "@salesforce/apex" in imp:
            result["apex_imports"].append(imp)
        elif imp.startswith("c/") or imp.startswith("lightning/"):
            result["lwc_imports"].append(imp)

    result["wire_adapters"] = sorted(set(re.findall(r"@wire\((\w+)", content)))
    result["pubsub_events"] = sorted(set(re.findall(r"fireEvent\s*\(\s*\w+\s*,\s*'([^']+)'", content)
                                         + re.findall(r"publish\s*\(\s*\w+\s*,\s*\w+\s*,\s*\{[^}]*\}\s*\)", content)))

    return result


def parse_flow(content, filepath):
    result = {
        "type": "Flow",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".flow-meta.xml", ""),
        "label": "",
        "flow_type": "",
        "status": "",
        "decision_count": 0,
        "record_types_referenced": [],
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "label" and not result["label"]:
            result["label"] = text
        elif tag == "processtype":
            result["flow_type"] = text
        elif tag == "status":
            result["status"] = text

    result["decision_count"] = len(list(root.iter("{*}decisions"))) + len(list(root.iter("decisions")))

    # Record types referenced anywhere in the file
    rts = sorted(set(re.findall(r'\b([A-Z][A-Za-z_]+(?:Draft|RecordType|Portal|Care|Draft_Global)[A-Za-z_]*)\b', content)))
    result["record_types_referenced"] = rts
    return result


def parse_validation_rule(content, filepath):
    result = {
        "type": "ValidationRule",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".validationRule-meta.xml", ""),
        "active": True,
        "description": "",
        "error_message": "",
        "condition_formula": "",
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "active":
            result["active"] = text.lower() not in ("false", "0")
        elif tag == "description" and not result["description"]:
            result["description"] = text[:200]
        elif tag == "errormessage" and not result["error_message"]:
            result["error_message"] = text[:200]
        elif tag == "errorconditionformula" and not result["condition_formula"]:
            result["condition_formula"] = text[:500]

    return result


def parse_layout(content, filepath):
    result = {
        "type": "Layout",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".layout-meta.xml", ""),
        "sections": [],
        "field_count": 0,
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    sections = set()
    for el in root.iter():
        tag = strip_ns(el.tag).lower()
        if tag == "label":
            sections.add((el.text or "").strip())

    result["sections"] = sorted(s for s in sections if s)
    result["field_count"] = len(re.findall(r"<field>", content))
    return result


def parse_flexipage(content, filepath):
    result = {
        "type": "Flexipage",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".flexipage-meta.xml", ""),
        "label": "",
        "page_type": "",
        "components": [],
        "record_types_referenced": [],
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "masterlabel" and not result["label"]:
            result["label"] = text
        elif tag == "pagetype" and not result["page_type"]:
            result["page_type"] = text
        elif tag == "componentname":
            result["components"].append(text)

    result["components"] = sorted(set(result["components"]))
    result["record_types_referenced"] = sorted(set(re.findall(r'\bDealer_Care\w*', content)))
    return result


def parse_permission_set(content, filepath):
    result = {
        "type": "PermissionSet",
        "filepath": filepath,
        "name": os.path.basename(filepath).replace(".permissionset-meta.xml", "").replace(".permissionsetgroup-meta.xml", ""),
        "label": "",
        "record_type_visibilities": [],
    }
    try:
        root = ET.fromstring(content)
    except ET.ParseError as e:
        result["parse_error"] = str(e)
        return result

    for tag, text in iter_tag_text(root):
        if tag == "label" and not result["label"]:
            result["label"] = text

    # Extract record type visibility entries
    for el in root.iter():
        if strip_ns(el.tag).lower() == "recordtypevisibilities":
            children = {strip_ns(c.tag).lower(): (c.text or "").strip() for c in el}
            rt = children.get("recordtype", "")
            visible = children.get("visible", "false")
            if rt:
                result["record_type_visibilities"].append({"record_type": rt, "visible": visible})

    return result


PARSERS = {
    "OmniScript":          parse_omniscript,
    "IntegrationProcedure":parse_integration_procedure,
    "DataRaptor":          parse_dataraptor,
    "ApexClass":           parse_apex_class,
    "LWC_JS":              parse_lwc_js,
    "Flow":                parse_flow,
    "ValidationRule":      parse_validation_rule,
    "Layout":              parse_layout,
    "Flexipage":           parse_flexipage,
    "PermissionSet":       parse_permission_set,
    "PermissionSetGroup":  parse_permission_set,
}


# ── Content grep scan (scope-of-change mode) ─────────────────────────────────

def scan_by_content(local_path, grep_term, max_files):
    """
    Walk repo and find files whose CONTENT contains grep_term.
    Used for scope-of-change docs where we know the reference component name.
    Returns parsed_components grouped by type.
    """
    hits = []
    for root_dir, dirs, files in os.walk(local_path):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            full_path = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(full_path, local_path)
            ftype = classify_file(fname)
            if not ftype or TYPE_PRIORITY.get(ftype, 0) == 0:
                continue
            try:
                with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            except Exception:
                continue
            if grep_term in content:
                hits.append((rel_path, full_path, ftype, content))

    if not hits:
        return []

    # Sort: by type priority desc, then name asc
    hits.sort(key=lambda x: (-TYPE_PRIORITY.get(x[2], 1), x[0]))

    print(f"\nFound {len(hits)} file(s) containing '{grep_term}'. Parsing top {min(len(hits), max_files)}:\n")

    parsed = []
    for rel_path, full_path, ftype, content in hits[:max_files]:
        print(f"  [{ftype:22}] {rel_path}")
        parse_fn = PARSERS.get(ftype)
        if parse_fn:
            result = parse_fn(content, rel_path)
            parsed.append(result)

    return parsed


# ── Local directory scanning ──────────────────────────────────────────────────

def scan_local_dir(local_path, keywords, max_files):
    """Walk a local directory, score files, return parsed components."""
    candidates = []
    for root_dir, dirs, files in os.walk(local_path):
        # Skip hidden dirs
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for fname in files:
            full_path = os.path.join(root_dir, fname)
            rel_path = os.path.relpath(full_path, local_path)
            ftype = classify_file(fname)
            if not ftype:
                continue
            score = score_file(rel_path, keywords)
            if score > 0:
                candidates.append((score, rel_path, full_path, ftype))

    candidates.sort(key=lambda x: (-x[0], x[1]))

    if not candidates:
        return [], []

    print(f"\nFound {len(candidates)} relevant file(s). Parsing top {min(len(candidates), max_files)}:\n")

    parsed_components = []
    for score, rel_path, full_path, ftype in candidates[:max_files]:
        print(f"  [{ftype:22}] {rel_path}  (score={score})")
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
        except Exception as e:
            print(f"    WARNING: Could not read {rel_path}: {e}", file=sys.stderr)
            continue

        parse_fn = PARSERS.get(ftype)
        if parse_fn:
            parsed = parse_fn(content, rel_path)
            parsed_components.append(parsed)

    return candidates, parsed_components


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Fetch and parse Salesforce metadata for documentation")
    parser.add_argument("--repo",       default="", help="GitHub repo in owner/repo format (for remote)")
    parser.add_argument("--branch",     default="main", help="Branch or tag (default: main)")
    parser.add_argument("--token",      default="", help="GitHub PAT (for private repos)")
    parser.add_argument("--local-path", default="", help="Local repo path (alternative to --repo)")
    parser.add_argument("--component",  default="", help="Component/feature name to search for (integration mode)")
    parser.add_argument("--grep-term",  default="", help="String to grep in file contents (scope-of-change mode)")
    parser.add_argument("--output",     required=True, help="Output JSON file path")
    parser.add_argument("--max-files",  type=int, default=25, help="Max files to process (default: 25)")
    args = parser.parse_args()

    if not args.component and not args.grep_term:
        print("ERROR: Provide either --component (integration mode) or --grep-term (scope-of-change mode)", file=sys.stderr)
        sys.exit(1)

    if not args.repo and not args.local_path:
        print("ERROR: Provide either --repo (GitHub) or --local-path (local directory)", file=sys.stderr)
        sys.exit(1)

    mode = "scope" if args.grep_term else "integration"
    print(f"Mode:      {'Scope of Change (grep)' if mode == 'scope' else 'Integration Flow (keyword)'}")

    if mode == "integration":
        keywords = keywords_from_name(args.component)
        print(f"Component: {args.component}")
        print(f"Keywords:  {', '.join(keywords)}")
    else:
        keywords = []
        print(f"Grep term: {args.grep_term}")

    if args.local_path:
        local_path = os.path.expanduser(args.local_path)
        if not os.path.isdir(local_path):
            print(f"ERROR: Local path not found: {local_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Source:    Local — {local_path}")
        print()

        if mode == "scope":
            parsed_components = scan_by_content(local_path, args.grep_term, args.max_files)
            if not parsed_components:
                print(f"\nNo files found containing '{args.grep_term}'.", file=sys.stderr)
                sys.exit(1)
            candidates = parsed_components  # for count reporting
        else:
            candidates, parsed_components = scan_local_dir(local_path, keywords, args.max_files)
            if not candidates:
                print(f"\nNo relevant files found for keywords: {', '.join(keywords)}", file=sys.stderr)
                print("Try a different component name.", file=sys.stderr)
                sys.exit(1)

        source_info = {"type": "local", "path": local_path}

    else:
        if "/" not in args.repo:
            print("ERROR: --repo must be in 'owner/repo' format", file=sys.stderr)
            sys.exit(1)

        owner, repo = args.repo.split("/", 1)
        token = args.token.strip() or None
        print(f"Source:    GitHub — {args.repo} @ {args.branch}")
        print()

        print("Fetching repo file tree (this may take a moment)...")
        tree = get_repo_tree(owner, repo, args.branch, token)
        print(f"  {len(tree)} files in tree")

        candidates_raw = []
        for item in tree:
            if item.get("type") != "blob":
                continue
            path = item["path"]
            ftype = classify_file(path)
            if not ftype:
                continue
            score = score_file(path, keywords)
            if score > 0:
                candidates_raw.append((score, path, ftype))

        candidates_raw.sort(key=lambda x: (-x[0], x[1]))

        if not candidates_raw:
            print(f"\nNo relevant files found for keywords: {', '.join(keywords)}", file=sys.stderr)
            sys.exit(1)

        print(f"\nFound {len(candidates_raw)} relevant file(s). Downloading top {min(len(candidates_raw), args.max_files)}:\n")

        parsed_components = []
        for score, path, ftype in candidates_raw[:args.max_files]:
            print(f"  [{ftype:22}] {path}  (score={score})")
            content = download_file(owner, repo, path, args.branch, token)
            if content is None:
                print(f"    WARNING: Could not download {path}", file=sys.stderr)
                continue
            parse_fn = PARSERS.get(ftype)
            if parse_fn:
                parsed = parse_fn(content, path)
                parsed_components.append(parsed)

        candidates = candidates_raw
        source_info = {"type": "github", "repo": args.repo, "branch": args.branch}

    print(f"\nParsed {len(parsed_components)} files.")

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    output_data = {
        "mode": mode,
        "component_name": args.component,
        "grep_term": args.grep_term,
        "source": source_info,
        "keywords": keywords,
        "files_found": len(candidates),
        "files_parsed": len(parsed_components),
        "components": parsed_components,
    }

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)

    print(json.dumps({"status": "ok", "output": args.output, "component_count": len(parsed_components)}))


if __name__ == "__main__":
    main()
