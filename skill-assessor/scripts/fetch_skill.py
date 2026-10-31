#!/usr/bin/env python3
"""Fetch a skill into a pinned, inspectable folder. Never executes anything from it.

Usage:
  fetch_skill.py <source> --out DIR [--force]

<source> can be:
  * a GitHub URL: repo root, /tree/<ref>/<path>, or /blob/<ref>/<path>/SKILL.md
  * a local .skill or .zip file, a local folder, or a single SKILL.md file

Writes into DIR:
  skill_src/        the unpacked skill files (read-only to humans: never run them from here)
  provenance.json   who/what/when signals plus the pin (commit SHA or file hash)
  inventory.json    output of inventory.py for skill_src/
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from inventory import build_inventory  # noqa: E402

MAX_DOWNLOAD = 50 * 1024 * 1024
MAX_UNZIPPED = 150 * 1024 * 1024
MAX_FILES = 5000


class FetchError(Exception):
    pass


def http_get(url: str) -> bytes:
    headers = {"User-Agent": "skill-assessor"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
            data = r.read(MAX_DOWNLOAD + 1)
    except urllib.error.HTTPError as e:
        reason = e.headers.get("x-deny-reason")
        extra = f" (x-deny-reason: {reason})" if reason else ""
        raise FetchError(f"HTTP {e.code} for {url}{extra}")
    except urllib.error.URLError as e:
        raise FetchError(f"Cannot reach {url}: {e.reason}")
    if len(data) > MAX_DOWNLOAD:
        raise FetchError("Download exceeds the 50 MB safety limit")
    return data


def api(path: str):
    return json.loads(http_get("https://api.github.com" + path))


def days_since(iso: str):
    try:
        then = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return (dt.datetime.now(dt.timezone.utc) - then).days
    except Exception:
        return None


def parse_github(url: str):
    u = urllib.parse.urlparse(url)
    if u.netloc.lower() not in ("github.com", "www.github.com"):
        return None
    parts = [p for p in u.path.split("/") if p]
    if len(parts) < 2:
        return None
    owner, repo = parts[0], parts[1][:-4] if parts[1].endswith(".git") else parts[1]
    tail = parts[3:] if len(parts) > 2 and parts[2] in ("tree", "blob") else []
    return owner, repo, tail


def download_ref(owner, repo, tail):
    """Download the repo zip for a ref without using the (rate-limited) REST API.

    Branch names can contain slashes, so try progressively longer prefixes of the URL
    tail as the ref; whatever is left over is the path inside the repo.
    Returns (zip_bytes, ref, subpath).
    """
    if not tail:
        return http_get(f"https://codeload.github.com/{owner}/{repo}/zip/HEAD"), "HEAD", ""
    last_err = None
    for i in range(1, len(tail) + 1):
        ref = "/".join(tail[:i])
        try:
            data = http_get(f"https://codeload.github.com/{owner}/{repo}/zip/{urllib.parse.quote(ref, safe='/')}")
            return data, ref, "/".join(tail[i:])
        except FetchError as e:
            last_err = e
    raise FetchError(f"Could not resolve a branch, tag, or commit from that URL ({last_err})")


def zip_pin(zf: zipfile.ZipFile, zbytes: bytes):
    """GitHub stores the commit SHA in the zip comment; fall back to a content hash."""
    comment = zf.comment.decode("ascii", errors="ignore").strip()
    if re.fullmatch(r"[0-9a-f]{40}", comment):
        return comment, "commit"
    return hashlib.sha256(zbytes).hexdigest(), "archive-sha256"


def approx_commit_date(zf: zipfile.ZipFile):
    stamps = [dt.datetime(*i.date_time) for i in zf.infolist() if i.date_time[0] > 1980]
    return max(stamps).isoformat() + "Z" if stamps else None


def safe_extract(zf: zipfile.ZipFile, dest: Path):
    """Extract with zip-slip, size, count, and symlink protection. Returns skipped symlinks."""
    dest = dest.resolve()
    infos = zf.infolist()
    if len(infos) > MAX_FILES:
        raise FetchError(f"Archive has {len(infos)} entries (limit {MAX_FILES})")
    if sum(i.file_size for i in infos) > MAX_UNZIPPED:
        raise FetchError("Archive expands beyond the 150 MB safety limit")
    skipped = []
    for info in infos:
        target = (dest / info.filename).resolve()
        if target != dest and dest not in target.parents:
            raise FetchError(f"Unsafe path in archive: {info.filename}")
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            skipped.append(info.filename)
            continue
        if info.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(zf.read(info))
    return skipped


def strip_single_top_dir(path: Path) -> Path:
    entries = [e for e in path.iterdir()]
    return entries[0] if len(entries) == 1 and entries[0].is_dir() else path


def fetch_github(owner, repo, tail, work: Path, source_url: str = ""):
    zbytes, ref, subpath = download_ref(owner, repo, tail)
    raw = work / "_raw"
    with zipfile.ZipFile(io.BytesIO(zbytes)) as zf:
        pin, pin_kind = zip_pin(zf, zbytes)
        commit_date = approx_commit_date(zf)
        skipped = safe_extract(zf, raw)
    base = strip_single_top_dir(raw)
    root = base / subpath if subpath else base
    if not root.exists():
        listing = sorted(p.name for p in base.iterdir())
        raise FetchError(f"Path '{subpath}' not found in {ref}. Top level: {listing}")
    if root.is_file():
        root = root.parent

    # Enrichment only: the REST API allows 60 unauthenticated calls/hour per IP and is
    # often exhausted on shared networks. The assessment must still work without it.
    signals, api_error = {}, None
    try:
        meta = api(f"/repos/{owner}/{repo}")
        try:
            owner_info = api(f"/users/{owner}")
        except FetchError:
            owner_info = {}
        signals = {
            "stars": meta.get("stargazers_count"),
            "forks": meta.get("forks_count"),
            "open_issues": meta.get("open_issues_count"),
            "license": (meta.get("license") or {}).get("spdx_id"),
            "archived": meta.get("archived"),
            "is_fork": meta.get("fork"),
            "fork_of": (meta.get("parent") or {}).get("full_name"),
            "repo_age_days": days_since(meta.get("created_at", "")),
            "days_since_last_push": days_since(meta.get("pushed_at", "")),
            "owner_type": owner_info.get("type"),
            "owner_account_age_days": days_since(owner_info.get("created_at", "")),
            "owner_public_repos": owner_info.get("public_repos"),
            "owner_followers": owner_info.get("followers"),
        }
    except FetchError as e:
        api_error = str(e)

    prov = {
        "source_type": "github",
        "url": f"https://github.com/{owner}/{repo}",
        "url_as_given": source_url,
        "owner": owner,
        "repo": repo,
        "ref_requested": ref,
        "subpath": subpath or None,
        "pin": pin,
        "pin_kind": pin_kind,
        "commit_date_approx": commit_date,
        "signals": signals or None,
        "signals_unavailable_reason": api_error,
        "next_step_if_signals_missing": (
            "web_fetch the exact URL the user gave and read owner, stars, last commit, and license from the page. "
            "If that is not enough, web_search for owner/repo and fetch the repo-root URL that comes back "
            "(web_fetch refuses URLs you build yourself). Also check whether this is the original repo or a copy "
            "under another owner. Or set GITHUB_TOKEN for higher API limits."
            if api_error
            else None
        ),
        "symlinks_skipped_in_archive": skipped,
    }
    return root, prov


def fetch_local(src: Path, work: Path):
    raw = work / "_raw"
    raw.mkdir(parents=True)
    skipped = []
    if src.is_dir():
        shutil.copytree(src, raw / src.name, symlinks=True)
        root = raw / src.name
        digest = "directory (no single hash)"
    elif src.suffix.lower() in (".zip", ".skill"):
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        with zipfile.ZipFile(src) as zf:
            skipped = safe_extract(zf, raw)
        root = strip_single_top_dir(raw)
    elif src.suffix.lower() == ".md":
        digest = hashlib.sha256(src.read_bytes()).hexdigest()
        root = raw / "pasted-skill"
        root.mkdir()
        shutil.copy(src, root / "SKILL.md")
    else:
        raise FetchError(f"Unsupported local source: {src}")
    prov = {
        "source_type": "local",
        "origin": str(src),
        "pinned_sha256": digest,
        "provenance_note": "No repo history available; provenance is unverifiable without answers from the user.",
        "symlinks_skipped_in_archive": skipped,
    }
    return root, prov


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("source")
    ap.add_argument("--out", required=True)
    ap.add_argument("--force", action="store_true", help="wipe --out first if it exists")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists() and any(out.iterdir()):
        if not args.force:
            sys.exit(f"{out} is not empty; use --force to wipe it")
        # Only wipe a folder this script created, so a mistyped --out cannot delete real work.
        if not ((out / "provenance.json").exists() or (out / "skill_src").exists()):
            sys.exit(f"{out} is not empty and is not a previous assessment folder; refusing to wipe it")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)

    try:
        gh = parse_github(args.source) if args.source.startswith("http") else None
        if gh:
            root, prov = fetch_github(*gh, work=out, source_url=args.source)
        elif Path(args.source).exists():
            root, prov = fetch_local(Path(args.source), work=out)
        else:
            raise FetchError(
                "Not a GitHub URL or an existing local path. For other hosts, download the file and upload it."
            )
    except FetchError as e:
        sys.exit(f"FETCH FAILED: {e}")
    except zipfile.BadZipFile:
        sys.exit("FETCH FAILED: file is not a valid zip/.skill archive")

    final = out / "skill_src"
    shutil.move(str(root), str(final))
    shutil.rmtree(out / "_raw", ignore_errors=True)

    inv = build_inventory(final)
    (out / "provenance.json").write_text(json.dumps(prov, indent=2), encoding="utf-8")
    (out / "inventory.json").write_text(json.dumps(inv, indent=2), encoding="utf-8")

    print(f"Fetched into {final}")
    pin = prov.get("pin") or prov.get("pinned_sha256")
    print(f"Pinned: {pin} ({prov.get('pin_kind', 'file hash')})")
    if prov.get("signals_unavailable_reason"):
        print("NOTE: repo signals unavailable ->", prov["signals_unavailable_reason"])
    print(f"Skills found: {inv['skill_count']}")
    for s in inv["skills"]:
        t = s["tokens"]
        print(
            f"  - {s['name'] or '(no name)'} [{s['dir']}] "
            f"metadata~{t['always_loaded_metadata']}t body~{t['loaded_on_trigger_body']}t "
            f"on-demand~{t['on_demand_referenced_files']}t scripts~{t['script_files_if_read']}t "
            f"(shipped but never loaded~{t['shipped_but_not_loaded']}t)"
        )
    if inv["plugin_style_components"]:
        print("Plugin-style components (hooks/MCP/commands/agents):", inv["plugin_style_components"])
    print(f"Wrote {out/'provenance.json'} and {out/'inventory.json'}")


if __name__ == "__main__":
    main()
