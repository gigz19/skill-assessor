#!/usr/bin/env python3
"""Static pattern scan of a skill folder. Produces LEADS for a human-style review.

Usage: scan.py <folder> [--pretty]

A hit is not a verdict: `pip install requests` in a docs skill is normal, while
the same line in a skill that claims to format text is suspicious. The reviewer
must read each hit in context and compare it with what the skill says it does.
Nothing in the scanned folder is executed or imported.
"""
import json
import os
import re
import sys
from collections import defaultdict
from pathlib import Path

SKIP_DIRS = {".git", "node_modules", "__pycache__"}
MAX_FILE_BYTES = 2 * 1024 * 1024

# (category, severity_hint, regex, label)
PATTERNS = [
    # Text aimed at the AI doing the reviewing or at hiding behaviour from the user
    ("injection", "high", r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|rules|guidelines)", "tells the model to ignore earlier instructions"),
    ("injection", "high", r"(do not|don'?t|never) (tell|inform|mention|reveal|show)[^.\n]{0,50}\b(user|human|person)\b", "asks to hide something from the user"),
    ("injection", "medium", r"without (asking|telling|informing|notifying|confirm)", "acts without user knowledge or consent"),
    ("injection", "high", r"(mark|report|rate|label|call)[^.\n]{0,40}\b(safe|secure|trusted|approved)\b", "tries to steer a reviewer's verdict"),
    ("injection", "medium", r"you are now|new instructions:|system override|developer mode|disregard", "role or instruction override phrasing"),
    ("injection", "medium", r"(reveal|print|output|repeat)[^.\n]{0,30}(system prompt|hidden instructions)", "tries to extract system prompt"),
    # Running things
    ("exec", "high", r"(curl|wget)[^\n|]*\|\s*(sudo\s+)?(ba|z)?sh", "pipes a download into a shell"),
    ("exec", "high", r"\b(eval|exec)\s*\(|Invoke-Expression|\biex\b\s", "dynamic code execution"),
    ("exec", "medium", r"os\.system|subprocess\.|shell\s*=\s*True|child_process|Runtime\.getRuntime", "spawns shell or processes"),
    ("exec", "medium", r"\brm\s+-rf\b|\bchmod\s+(\+x|[0-7]{3,4})\b|\bsudo\b|\bmkfs\b|\bdd\s+if=", "destructive or privileged command"),
    ("exec", "low", r"pip3? install|npm (i|install)|npx |yarn add|cargo install|apt(-get)? install|brew install", "installs software"),
    # Credentials and private data
    ("secrets", "high", r"\.ssh|id_rsa|id_ed25519|\.aws/|\.gnupg|\.netrc|keychain|\.kube/config|wallet\.dat", "touches credential locations"),
    ("secrets", "medium", r"os\.environ|process\.env|getenv|printenv|\benv\b\s*\|", "reads environment variables"),
    ("secrets", "medium", r"api[_-]?key|secret|password|passwd|bearer|auth[_-]?token|cookie|session[_-]?id", "mentions credentials or tokens"),
    ("secrets", "low", r"\.env\b|credentials|\.npmrc|\.pypirc", "mentions config files that often hold secrets"),
    # Leaving the machine
    ("network", "high", r"webhook|ngrok|pastebin|transfer\.sh|requestbin|discord(app)?\.com/api|telegram\.org/bot|burpcollaborator|interact\.sh", "known exfiltration-style endpoints"),
    ("network", "medium", r"requests\.(get|post|put)|urllib|httpx|aiohttp|fetch\(|XMLHttpRequest|axios|socket\.|websocket|\bnc\s+-|\bscp\b|\brsync\b", "makes network calls"),
    ("network", "low", r"https?://", "contains a URL"),
    # Obfuscation
    ("obfuscation", "high", r"base64\s+(-d|--decode)|b64decode|atob\(|fromCharCode|marshal\.loads|pickle\.loads|zlib\.decompress|codecs\.decode\([^)]*rot", "decodes or deserializes hidden payloads"),
    ("obfuscation", "medium", r"(\\x[0-9a-fA-F]{2}){8,}|(\\u[0-9a-fA-F]{4}){6,}", "long escaped byte/unicode sequence"),
    # Reaching outside its own task: persistence and agent configuration
    ("persistence", "high", r"crontab|\.bashrc|\.zshrc|\.profile|launchctl|systemctl|schtasks|authorized_keys|LD_PRELOAD", "persistence mechanism"),
    ("persistence", "high", r"CLAUDE\.md|\.claude/|settings\.json|\.cursorrules|AGENTS\.md|\.mcp\.json|mcpServers", "edits agent configuration or memory"),
    ("persistence", "medium", r"git (config|push|remote add)|--global|--no-verify", "alters git config or pushes code"),
]
COMPILED = [(c, s, re.compile(p, re.I), label) for c, s, p, label in PATTERNS]

# Invisible or direction-changing characters can hide text from human reviewers.
SUSPICIOUS_CHARS = [
    (0x200B, 0x200F), (0x202A, 0x202E), (0x2060, 0x2064), (0x2066, 0x2069),
    (0xFEFF, 0xFEFF), (0xE0000, 0xE007F),
]
URL_RE = re.compile(r"https?://[^\s)\]\"'>`]+")
BLOB_RE = re.compile(r"[A-Za-z0-9+/=]{200,}")


def is_suspicious_char(ch: str) -> bool:
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in SUSPICIOUS_CHARS)


def scan_file(path: Path, rel: str, findings, domains):
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            findings["oversize_files"].append(rel)
            return
        with open(path, "rb") as f:
            raw = f.read()
    except OSError:
        return
    if b"\0" in raw[:8000]:
        findings["binary_files"].append(rel)
        return
    text = raw.decode("utf-8", errors="replace")
    for ln, line in enumerate(text.splitlines(), 1):
        snippet = line.strip()[:160]
        for cat, sev, rx, label in COMPILED:
            if rx.search(line):
                if cat == "network" and sev == "low":
                    for url in URL_RE.findall(line):
                        host = re.sub(r"^https?://", "", url).split("/")[0].lower()
                        domains[host].add(rel)
                    continue  # domains are summarised separately
                findings["hits"].append(
                    {"file": rel, "line": ln, "category": cat, "severity_hint": sev, "why": label, "text": snippet}
                )
        if any(is_suspicious_char(ch) for ch in line):
            findings["hits"].append(
                {"file": rel, "line": ln, "category": "obfuscation", "severity_hint": "high",
                 "why": "invisible/bidirectional unicode characters (can hide text)", "text": snippet}
            )
        if BLOB_RE.search(line):
            findings["hits"].append(
                {"file": rel, "line": ln, "category": "obfuscation", "severity_hint": "medium",
                 "why": "very long base64-like blob", "text": snippet[:80] + "..."}
            )


def scan(root) -> dict:
    root = Path(root).resolve()
    findings = {"hits": [], "binary_files": [], "oversize_files": [], "symlinks": []}
    domains = defaultdict(set)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            p = Path(dirpath) / fn
            rel = str(p.relative_to(root))
            if p.is_symlink():
                findings["symlinks"].append(rel)
                continue
            scan_file(p, rel, findings, domains)
    order = {"high": 0, "medium": 1, "low": 2}
    findings["hits"].sort(key=lambda h: (order[h["severity_hint"]], h["file"], h["line"]))
    by_cat = defaultdict(int)
    for h in findings["hits"]:
        by_cat[f"{h['category']}:{h['severity_hint']}"] += 1
    return {
        "root": str(root),
        "reminder": "Hits are leads, not verdicts. Read each in context against the skill's stated purpose.",
        "summary": dict(sorted(by_cat.items())),
        "hits": findings["hits"],
        "domains_mentioned": {d: sorted(f) for d, f in sorted(domains.items())},
        "binary_files": findings["binary_files"],
        "oversize_files_not_scanned": findings["oversize_files"],
        "symlinks": findings["symlinks"],
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    print(json.dumps(scan(sys.argv[1]), indent=2 if "--pretty" in sys.argv else None))
