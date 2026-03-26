#!/usr/bin/env python3
"""
Extracts custom fields and picklist values from a Salesforce object.

Tries sf CLI first. If sf/node is unavailable, falls back to direct
Salesforce REST API using stored credentials in ~/.sfdx/<username>.json.

Generates an intermediate Excel with two tabs:
  - Custom_Fields:    Field Label | Field API Name
  - Picklist_Values:  Field API Name | Picklist Value | Picklist Label
"""
import argparse
import json
import os
import subprocess
import sys
import urllib.request
import urllib.error
import urllib.parse

import openpyxl


def strip_custom_suffix(api_name: str) -> str:
    """Remove __c suffix from a field API name for use in STF keys."""
    if api_name.endswith("__c"):
        return api_name[:-3]
    return api_name


# ── SF CLI approach ──────────────────────────────────────────────────────────

def describe_via_cli(org: str, object_name: str) -> dict:
    cmd = ["sf", "sobject", "describe", "--sobject", object_name,
           "--target-org", org, "--json"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[:300] or result.stdout[:300])
    data = json.loads(result.stdout)
    return data.get("result", {})


# ── REST API fallback ─────────────────────────────────────────────────────────

def load_auth(org_identifier: str) -> dict:
    """
    Loads auth from ~/.sfdx/<username>.json.
    org_identifier can be an alias (looked up in alias.json) or a username.
    """
    sfdx_dir = os.path.expanduser("~/.sfdx")

    # Resolve alias → username
    alias_file = os.path.join(sfdx_dir, "alias.json")
    username = org_identifier
    if os.path.isfile(alias_file):
        with open(alias_file) as f:
            aliases = json.load(f).get("orgs", {})
        if org_identifier in aliases:
            username = aliases[org_identifier]

    auth_file = os.path.join(sfdx_dir, f"{username}.json")
    if not os.path.isfile(auth_file):
        raise FileNotFoundError(
            f"No auth file found for '{username}' at {auth_file}.\n"
            "Run 'sf org login web' to authenticate."
        )
    with open(auth_file) as f:
        return json.load(f)


def refresh_access_token(auth: dict) -> str:
    """Use the refresh token to get a new access token and update the auth file."""
    login_url = auth.get("loginUrl", "https://login.salesforce.com").rstrip("/")
    client_id = auth.get("clientId", "PlatformCLI")
    refresh_token = auth.get("refreshToken", "")

    if not refresh_token:
        raise RuntimeError("No refresh token available. Re-authenticate with: sf org login web")

    params = urllib.parse.urlencode({
        "grant_type": "refresh_token",
        "client_id": client_id,
        "refresh_token": refresh_token,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{login_url}/services/oauth2/token",
        data=params,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        raise RuntimeError(f"Token refresh failed ({e.code}): {body[:300]}")

    new_token = data.get("access_token")
    if not new_token:
        raise RuntimeError(f"Token refresh returned no access_token: {data}")

    # Persist the new token back to the auth file
    sfdx_dir = os.path.expanduser("~/.sfdx")
    auth_file = os.path.join(sfdx_dir, f"{auth['username']}.json")
    if os.path.isfile(auth_file):
        auth["accessToken"] = new_token
        with open(auth_file, "w") as f:
            json.dump(auth, f, indent=2)

    return new_token


def sf_api_get(url: str, access_token: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {access_token}",
                 "Accept": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def describe_via_api(org_identifier: str, object_name: str) -> dict:
    auth = load_auth(org_identifier)
    instance_url = auth["instanceUrl"].rstrip("/")
    access_token = auth["accessToken"]
    api_version = auth.get("instanceApiVersion", "62.0")
    url = f"{instance_url}/services/data/v{api_version}/sobjects/{object_name}/describe/"

    try:
        return sf_api_get(url, access_token)
    except urllib.error.HTTPError as e:
        if e.code != 401:
            body = e.read().decode("utf-8")
            try:
                msg = json.loads(body)[0].get("message", body)
            except Exception:
                msg = body[:300]
            raise RuntimeError(f"Salesforce API error {e.code}: {msg}")

    # 401 — try refreshing the token
    print("Access token expired, refreshing...")
    access_token = refresh_access_token(auth)
    try:
        return sf_api_get(url, access_token)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8")
        try:
            msg = json.loads(body)[0].get("message", body)
        except Exception:
            msg = body[:300]
        raise RuntimeError(f"Salesforce API error after refresh {e.code}: {msg}")


# ── Shared extraction logic ───────────────────────────────────────────────────

def describe_object(org: str, object_name: str) -> dict:
    """Try sf CLI first; fall back to REST API if node/sf unavailable."""
    try:
        result = subprocess.run(["sf", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            print("Using sf CLI...")
            return describe_via_cli(org, object_name)
    except (FileNotFoundError, RuntimeError):
        pass

    print("sf CLI unavailable (node not found) — using Salesforce REST API directly...")
    return describe_via_api(org, object_name)


def extract_custom_fields(describe_result: dict):
    """
    Returns:
      fields: list of (field_label, field_api_name, stf_field_name)
      picklist_values: list of (stf_field_name, picklist_value, picklist_label)
    """
    fields = []
    picklist_values = []

    for field in describe_result.get("fields", []):
        api_name = field.get("name", "")
        label = field.get("label", "")

        # Only process custom fields (API name ends with __c)
        if not api_name.endswith("__c"):
            continue

        stf_field_name = strip_custom_suffix(api_name)
        fields.append((label, api_name, stf_field_name))

        # Collect active picklist values
        for pv in field.get("picklistValues", []):
            pv_value = pv.get("value", "")
            pv_label = pv.get("label", "")
            active = pv.get("active", True)
            if active and pv_value:
                picklist_values.append((stf_field_name, pv_value, pv_label))

    return fields, picklist_values


def write_intermediate_excel(output_path: str, fields: list, picklist_values: list):
    wb = openpyxl.Workbook()

    ws_fields = wb.active
    ws_fields.title = "Custom_Fields"
    ws_fields.append(["Field Label", "Field API Name"])
    for label, api_name, stf_name in fields:
        ws_fields.append([label, api_name])

    ws_pv = wb.create_sheet("Picklist_Values")
    ws_pv.append(["Field API Name", "Picklist Value", "Picklist Label"])
    for stf_field_name, pv_value, pv_label in picklist_values:
        ws_pv.append([stf_field_name, pv_value, pv_label])

    wb.save(output_path)


def main():
    parser = argparse.ArgumentParser(description="Extract Salesforce object fields to intermediate Excel")
    parser.add_argument("--org", required=True, help="Salesforce org username or alias")
    parser.add_argument("--object", required=True, dest="object_name", help="Salesforce object API name")
    parser.add_argument("--output", required=True, help="Output directory")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print(f"Describing {args.object_name} in org {args.org}...")
    try:
        describe_result = describe_object(args.org, args.object_name)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    fields, picklist_values = extract_custom_fields(describe_result)

    if not fields:
        print(f"WARNING: No custom fields found on {args.object_name}. "
              "Verify the object API name and org access.", file=sys.stderr)

    output_path = os.path.join(args.output, f"{args.object_name}_intermediate.xlsx")
    write_intermediate_excel(output_path, fields, picklist_values)

    print(json.dumps({
        "status": "ok",
        "object": args.object_name,
        "org": args.org,
        "intermediate_excel": output_path,
        "custom_field_count": len(fields),
        "picklist_value_count": len(picklist_values),
        "summary": (
            f"Found {len(fields)} custom field(s) and "
            f"{len(picklist_values)} active picklist value(s) on {args.object_name}."
        ),
    }, indent=2))


if __name__ == "__main__":
    main()
