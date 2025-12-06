#!/usr/bin/env python3
"""
自动生成变更日志脚本
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
    # 处理标签不存在的情况
    if not tag_exists(end_incl):
        end_incl = "HEAD"
    if start_excl and not tag_exists(start_excl):
        start_excl = None
    rev = f"{start_excl}..{end_incl}" if start_excl else end_incl
    result = run_git(["log", "--oneline", "--format=%h|%s", rev], check=False)
    if result.returncode != 0:
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
        curr_tag = os.environ.get("GITHUB_REF_NAME")
        if not curr_tag:
            print("Error: No current tag provided", file=sys.stderr)
            sys.exit(1)

    # 获取hotfix标识（环境变量传递）
    is_hotfix = os.environ.get("IS_HOTFIX", "false").lower() == "true"

    tags = get_tags()
    if curr_tag not in tags:
        tags.append(curr_tag)
        tags.sort(key=lambda t: [int(x) for x in t.lstrip('v').split('.') if x.isdigit()], reverse=True)

    # 确定提交范围（hotfix版本特殊处理）
    if is_hotfix:
        # hotfix: 对比当前标签与最新提交（HEAD）的差异
        start_excl = curr_tag
        end_incl = "HEAD"
        display_tag = f"{curr_tag}_hotfix"
    else:
        # 正常版本: 对比当前标签与上一个标签的差异
        prev_tag = None
        for t in tags:
            if t == curr_tag:
                continue
            prev_tag = t
            break
        start_excl = prev_tag
        end_incl = curr_tag
        display_tag = curr_tag

    print(f"Previous reference: {start_excl or 'None'}", file=sys.stderr)
    print(f"Current reference: {end_incl}", file=sys.stderr)

    commits = get_commits_between(start_excl, end_incl)
    if not commits:
        print("No commits found.", file=sys.stderr)
        sys.exit(0)

    gitmoji = {
        "feat": "✨",
        "fix": "🐛",
        "docs": "📝",
        "style": "🎨",
        "refactor": "♻️",
        "perf": "⚡",
        "test": "✅",
        "build": "📦",
        "ci": "👷",
        "chore": "🔧",
        "other": "🚀",
    }
    groups = {k: [] for k in gitmoji.keys()}

    type_pattern = re.compile(r'^(\S*\s*)?(\w+)(?:\([^)]*\))?!?:\s*(.+)$')
    for hash_, subj in commits:
        match = type_pattern.match(subj)
        ctype = match.group(2).lower() if match else "other"
        groups[ctype].append((hash_, subj))

    lines = []
    lines.append("# What's Change:")
    lines.append("")
    lines.append(f"## {display_tag}")
    if start_excl:
        lines.append(f"**Changes since {start_excl}**\n")
    else:
        lines.append("**Initial release**\n")

    for gname, glist in groups.items():
        if not glist:
            continue
        emoji = gitmoji[gname]
        lines.append(f"### {emoji} {gname.capitalize()}")
        for hash_, subj in glist:
            lines.append(f"- {hash_}: {subj}")
        lines.append("")

    output = "\n".join(lines)
    sys.stdout.buffer.write(output.encode('utf-8'))

    out_file = os.environ.get("CHANGELOG_FILE")
    if out_file:
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(output)

if __name__ == "__main__":
    main()