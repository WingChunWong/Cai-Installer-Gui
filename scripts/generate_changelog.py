#!/usr/bin/env python3
"""
Generate changelog from git commits since last tag.
"""

import subprocess
import sys
import re
import os

def run_git(args, check=True):
    return subprocess.run(
        ["git"] + args,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=check
    )

def get_tags():
    """Return list of tags sorted by commit date (newest first)."""
    result = run_git(["tag", "--sort=-creatordate"])
    if result.returncode != 0:
        return []
    out = result.stdout.strip()
    return [t for t in out.splitlines() if t]

def tag_exists(tag):
    """Check if a tag exists in git."""
    result = run_git(["rev-parse", "--verify", tag], check=False)
    return result.returncode == 0

def get_commits_between(start_excl, end_incl):
    """Return list of (hash, subject) commits."""
    # If end_incl does not exist, fallback to HEAD
    if not tag_exists(end_incl):
        end_incl = "HEAD"
    if start_excl and not tag_exists(start_excl):
        start_excl = None
    rev = f"{start_excl}..{end_incl}" if start_excl else end_incl
    result = run_git(["log", "--oneline", "--format=%h|%s", rev], check=False)
    if result.returncode != 0:
        # maybe no commits? fallback to empty
        return []
    out = result.stdout.strip()
    commits = []
    for line in out.splitlines():
        if "|" not in line:
            continue
        h, s = line.split("|", 1)
        commits.append((h.strip(), s.strip()))
    return commits

def main():
    if len(sys.argv) > 1:
        curr_tag = sys.argv[1]
    else:
        # Try to get current tag from environment variable GITHUB_REF_NAME
        curr_tag = os.environ.get("GITHUB_REF_NAME")
        if not curr_tag:
            print("Error: No current tag provided and GITHUB_REF_NAME not set.", file=sys.stderr)
            sys.exit(1)

    tags = get_tags()
    if curr_tag not in tags:
        # maybe it's a new tag not yet in the list
        tags.append(curr_tag)
        # sort by version (simple)
        tags.sort(key=lambda t: [int(x) for x in t.lstrip('v').split('.') if x.isdigit()], reverse=True)

    # Find previous tag (the one before curr_tag)
    prev_tag = None
    for t in tags:
        if t == curr_tag:
            continue
        prev_tag = t
        break  # because tags are newest first, the first different tag is the previous release
    # If no previous tag, we'll generate from beginning
    print(f"Previous tag: {prev_tag or 'None'}", file=sys.stderr)
    print(f"Current tag: {curr_tag}", file=sys.stderr)

    commits = get_commits_between(prev_tag, curr_tag)
    if not commits:
        print("No commits found.", file=sys.stderr)
        sys.exit(0)

    # Group by conventional commit type
    groups = {
        "feat": [],
        "fix": [],
        "docs": [],
        "style": [],
        "refactor": [],
        "perf": [],
        "test": [],
        "build": [],
        "ci": [],
        "chore": [],
        "other": []
    }
    type_pattern = re.compile(r'^(\S*\s*)?(\w+)(?:\([^)]*\))?!?:\s*(.+)$')
    for hash_, subj in commits:
        match = type_pattern.match(subj)
        if match:
            ctype = match.group(2).lower()
        else:
            ctype = "other"
        if ctype in groups:
            groups[ctype].append((hash_, subj))
        else:
            groups["other"].append((hash_, subj))

    # Generate markdown
    lines = []
    lines.append(f"## {curr_tag}")
    if prev_tag:
        lines.append(f"**Changes since {prev_tag}**\n")
    else:
        lines.append("**Initial release**\n")

    for gname, glist in groups.items():
        if not glist:
            continue
        lines.append(f"### {gname.capitalize()}")
        for hash_, subj in glist:
            lines.append(f"- {hash_}: {subj}")
        lines.append("")

    output = "\n".join(lines)
    print(output)

    # Write to file if environment variable CHANGELOG_FILE is set
    out_file = os.environ.get("CHANGELOG_FILE")
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Changelog written to {out_file}", file=sys.stderr)

if __name__ == "__main__":
    main()