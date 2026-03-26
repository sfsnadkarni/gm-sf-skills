#!/usr/bin/env python3
"""
Installs the sf-translation skill to ~/.claude/skills/sf-translation/.

Usage:
  python3 install.py
"""
import os
import shutil
import subprocess
import sys

SKILL_NAME = "sf-translation"
INSTALL_DIR = os.path.expanduser(f"~/.claude/skills/{SKILL_NAME}")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def run(cmd, check=True):
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"ERROR: {result.stderr or result.stdout}")
        sys.exit(1)
    return result


def main():
    print(f"Installing {SKILL_NAME} to {INSTALL_DIR} ...")

    # Create destination
    os.makedirs(INSTALL_DIR, exist_ok=True)

    # Copy all skill files
    files_to_copy = ["SKILL.md", "requirements.txt", "README.md"]
    for filename in files_to_copy:
        src = os.path.join(SCRIPT_DIR, filename)
        dst = os.path.join(INSTALL_DIR, filename)
        if os.path.isfile(src):
            shutil.copy2(src, dst)
            print(f"  Copied {filename}")
        else:
            print(f"  Skipping {filename} (not found)")

    # Copy scripts directory
    scripts_src = os.path.join(SCRIPT_DIR, "scripts")
    scripts_dst = os.path.join(INSTALL_DIR, "scripts")
    if os.path.isdir(scripts_src):
        if os.path.exists(scripts_dst):
            shutil.rmtree(scripts_dst)
        shutil.copytree(scripts_src, scripts_dst)
        print(f"  Copied scripts/")

    # Install Python dependencies
    print("\nInstalling Python dependencies...")
    req_file = os.path.join(INSTALL_DIR, "requirements.txt")
    result = run(f'pip3 install -r "{req_file}" -q', check=False)
    if result.returncode != 0:
        print(f"  WARNING: pip3 install failed: {result.stderr[:200]}")
        print("  Run manually: pip3 install pandas openpyxl")
    else:
        print("  Dependencies installed.")

    print(f"\nInstallation complete.")
    print(f"Usage: /sf-translation Vehicle")
    print(f"       /sf-translation Case")
    print(f"       /sf-translation Account")


if __name__ == "__main__":
    main()
