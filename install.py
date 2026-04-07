#!/usr/bin/env python3
"""
Installs all GM Salesforce skills to ~/.claude/skills/.

Usage:
  python3 install.py
"""
import os
import shutil
import subprocess
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def check_prerequisites():
    """Check that Claude Code is installed and authenticated before installing skills."""
    print("Checking prerequisites...\n")

    # ── 1. Check Claude Code is installed ─────────────────────────────────────
    result = subprocess.run(["which", "claude"], capture_output=True, text=True)
    if result.returncode != 0:
        print("ERROR: Claude Code is not installed.")
        print()
        print("  Install it from: https://claude.ai/code")
        print("  Or via npm:  npm install -g @anthropic-ai/claude-code")
        print()
        sys.exit(1)

    print("  ✓ Claude Code is installed")

    # ── 2. Check Claude Code is authenticated ─────────────────────────────────
    claude_dir   = os.path.expanduser("~/.claude")
    auth_markers = [
        os.path.join(claude_dir, "credentials.json"),
        os.path.join(claude_dir, ".credentials.json"),
        os.path.join(claude_dir, "settings.json"),
    ]
    authenticated = any(os.path.isfile(p) for p in auth_markers)

    if not authenticated:
        print()
        print("  ✗ Claude Code is not authenticated yet.")
        print()
        print("  ─────────────────────────────────────────────────────────────")
        print("  ACTION REQUIRED — Log in with your Claude account:")
        print()
        print("    1. Run:  claude")
        print("    2. When prompted, choose: 'Login with Claude.ai'")
        print("       (do NOT enter an API key)")
        print("    3. A browser window will open — log in with your")
        print("       Claude account (the same one you use on claude.ai)")
        print("    4. Come back here and re-run:  python3 install.py")
        print("  ─────────────────────────────────────────────────────────────")
        print()
        sys.exit(1)

    print("  ✓ Claude Code is authenticated")
    print()

SKILLS = [
    {
        "name": "sf-translation",
        "src":  SCRIPT_DIR,                                    # files at repo root
        "files": ["SKILL.md", "requirements.txt", "README.md"],
    },
    {
        "name": "sf-translation-verify",
        "src":  os.path.join(SCRIPT_DIR, "sf-translation-verify"),
        "files": ["SKILL.md", "requirements.txt"],
    },
    {
        "name": "sf-document",
        "src":  os.path.join(SCRIPT_DIR, "sf-document"),
        "files": ["SKILL.md", "requirements.txt"],
    },
    {
        "name": "sf-org-assessment",
        "src":  os.path.join(SCRIPT_DIR, "sf-org-assessment"),
        "files": ["SKILL.md"],
    },
    {
        "name": "sf-translation-v2",
        "src":  os.path.join(SCRIPT_DIR, "sf-translation-v2"),
        "files": ["SKILL.md", "requirements.txt"],
    },
]


def install_skill(skill: dict):
    name     = skill["name"]
    src_dir  = skill["src"]
    dst_dir  = os.path.expanduser(f"~/.claude/skills/{name}")

    print(f"\nInstalling {name} → {dst_dir}")
    os.makedirs(dst_dir, exist_ok=True)

    # Copy individual files
    for filename in skill["files"]:
        src = os.path.join(src_dir, filename)
        dst = os.path.join(dst_dir, filename)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  Copied {filename}")

    # Copy scripts/ directory
    scripts_src = os.path.join(src_dir, "scripts")
    scripts_dst = os.path.join(dst_dir, "scripts")
    if os.path.isdir(scripts_src):
        if os.path.exists(scripts_dst):
            shutil.rmtree(scripts_dst)
        shutil.copytree(scripts_src, scripts_dst)
        print(f"  Copied scripts/")

    # Install Python dependencies
    req_file = os.path.join(dst_dir, "requirements.txt")
    if os.path.isfile(req_file):
        result = subprocess.run(
            f'pip3 install -r "{req_file}" -q',
            shell=True, capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  WARNING: pip3 install failed — run manually: pip3 install pandas openpyxl")
        else:
            print(f"  Dependencies installed.")


def main():
    check_prerequisites()
    for skill in SKILLS:
        install_skill(skill)

    print("\nInstallation complete.")
    print("\nUsage:")
    print("  /sf-translation Vehicle          — generate STF translation files")
    print("  /sf-translation Case")
    print("  /sf-translation Account")
    print()
    print("  /sf-translation-verify Vehicle   — verify translations against master sheet")
    print("  /sf-translation-verify Case")
    print()
    print("  /sf-document 'Lock Unlock Omniscript'   — generate implementation documentation")
    print("  /sf-document 'Case Transfer Flow'")
    print()
    print("  /sf-org-assessment                      — assess org health and generate HTML report")
    print()
    print("  /sf-translation-v2 Vehicle              — generate STF + custom label translations (LRP support)")
    print("  /sf-translation-v2 Case")


if __name__ == "__main__":
    main()
