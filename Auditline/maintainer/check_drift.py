"""Report checklist sections whose CodeWriter source changed after they were distilled.

Maintainer tool, not shipped. Standard library only.

    python maintainer/check_drift.py            # list stale sections; exit 1 if any
    python maintainer/check_drift.py --warn     # list them but always exit 0
    python maintainer/check_drift.py --update   # re-record SHAs after reviewing the changes

Each section of refs/lang/*-checklist.md carries
``<!-- provenance: CodeWriter/<lang>/refs/<file>.md @ <sha> -->``. The recorded sha is compared
with ``git log -1 --format=%H -- <file>``. When CodeWriter is not next to this skill (an
installed copy), the check prints a notice and exits 0.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = (
    ROOT.parent
)  # the directory that holds CodeWriter/ when both are checked out
PROVENANCE = re.compile(
    r"<!-- provenance: (CodeWriter/\S+\.md) @ ([0-9a-f]{40}|unknown) -->"
)
HEADING = re.compile(r"^## (.+)$")


@dataclass(frozen=True)
class Section:
    checklist: Path
    heading: str
    source: str
    recorded: str


def git(*args: str) -> str:
    exe = shutil.which("git")
    if exe is None:
        raise RuntimeError("git is not installed")
    done = subprocess.run(  # noqa: S603 - fixed arguments, no shell
        [exe, *args], cwd=WORKSPACE, capture_output=True, text=True, check=False
    )
    return done.stdout.strip()


def sections() -> list[Section]:
    found: list[Section] = []
    for path in sorted((ROOT / "refs" / "lang").glob("*-checklist.md")):
        heading = ""
        for line in path.read_text(encoding="utf-8").splitlines():
            if m := HEADING.match(line):
                heading = m.group(1)
            elif m := PROVENANCE.search(line):
                found.append(Section(path, heading, m.group(1), m.group(2)))
    return found


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--warn", action="store_true", help="always exit 0")
    ap.add_argument(
        "--update",
        action="store_true",
        help="rewrite recorded shas to the current ones",
    )
    args = ap.parse_args()

    if not (WORKSPACE / "CodeWriter").is_dir():
        print("notice: CodeWriter/ is not next to this skill; nothing to compare")
        return 0

    stale: list[tuple[Section, str, str]] = []
    missing: list[Section] = []
    for sec in sections():
        if not (WORKSPACE / sec.source).exists():
            missing.append(sec)
            continue
        current = git("log", "-1", "--format=%H", "--", sec.source)
        if current and current != sec.recorded:
            stale.append((sec, current, sec.recorded))

    for sec in missing:
        print(
            f"missing source: {sec.source} (section '{sec.heading}' in {sec.checklist.name})"
        )
    for sec, current, recorded in stale:
        print(f"STALE: {sec.checklist.name} section '{sec.heading}'")
        print(f"  source {sec.source}")
        print(f"  recorded {recorded[:12]}, now {current[:12]}")
        changes = git("log", "--oneline", f"{recorded}..{current}", "--", sec.source)
        for ln in changes.splitlines()[:5]:
            print(f"  {ln}")

    if args.update and stale:
        for checklist in {s.checklist for s, _, _ in stale}:
            text = checklist.read_text(encoding="utf-8")
            for sec, current, recorded in stale:
                if sec.checklist == checklist:
                    text = text.replace(
                        f"{sec.source} @ {recorded}", f"{sec.source} @ {current}"
                    )
            checklist.write_text(text, encoding="utf-8")
        print(f"updated {len(stale)} recorded shas; review the sections first")
        return 0

    total = len(sections())
    print(
        f"{total} sections checked, {len(stale)} stale, {len(missing)} missing source"
    )
    return 1 if stale and not args.warn else 0


if __name__ == "__main__":
    sys.exit(main())
