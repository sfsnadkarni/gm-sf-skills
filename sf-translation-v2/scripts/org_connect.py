#!/usr/bin/env python3
"""
Lists authenticated Salesforce orgs.
Tries sf CLI first; falls back to reading ~/.sfdx/ auth files directly.
"""
import json
import os
import subprocess
import sys


def list_via_cli() -> list:
    result = subprocess.run(
        ["sf", "org", "list", "--json"],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    orgs = []
    for section in ("nonScratchOrgs", "scratchOrgs"):
        for org in data.get("result", {}).get(section, []):
            orgs.append({
                "alias": org.get("alias") or "",
                "username": org.get("username") or "",
                "instanceUrl": org.get("instanceUrl") or "",
                "connectedStatus": org.get("connectedStatus") or "Unknown",
            })
    return orgs


def list_via_sfdx_files() -> list:
    """Read ~/.sfdx/<username>.json files directly when sf CLI is unavailable."""
    sfdx_dir = os.path.expanduser("~/.sfdx")
    if not os.path.isdir(sfdx_dir):
        return []

    # Load aliases
    alias_map = {}  # username -> alias
    alias_file = os.path.join(sfdx_dir, "alias.json")
    if os.path.isfile(alias_file):
        with open(alias_file) as f:
            for alias, username in json.load(f).get("orgs", {}).items():
                alias_map[username] = alias

    orgs = []
    for fname in os.listdir(sfdx_dir):
        if not fname.endswith(".json") or fname in ("alias.json", "sfdx-config.json"):
            continue
        fpath = os.path.join(sfdx_dir, fname)
        try:
            with open(fpath) as f:
                data = json.load(f)
            username = data.get("username", "")
            if not username:
                continue
            orgs.append({
                "alias": alias_map.get(username, ""),
                "username": username,
                "instanceUrl": data.get("instanceUrl", ""),
                "connectedStatus": "Connected",
                "isSandbox": data.get("isSandbox", False),
            })
        except Exception:
            continue

    return orgs


def main():
    orgs = []
    try:
        result = subprocess.run(["sf", "--version"], capture_output=True, text=True)
        if result.returncode == 0:
            orgs = list_via_cli()
    except FileNotFoundError:
        pass

    if not orgs:
        orgs = list_via_sfdx_files()

    print(json.dumps({"orgs": orgs}, indent=2))


if __name__ == "__main__":
    main()
