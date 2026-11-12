"""Build an isolated bundle for evaluating Auditline on the seeded-defect corpus.

Maintainer tool, not shipped. Standard library only.

    python maintainer/prepare_eval.py --out /tmp/auditline-eval [--node-modules DIR]

Creates, under --out:

    skill/auditline/     the shipped skill (SKILL.md, refs/, tooling/, validate_report.py), as an install has it:
                         no corpus, scorer or maintainer/, so a reviewer cannot read ground truth
    inputs/<language>/   a project root per language holding only the corpus source files, with
                         a tsconfig.json for TypeScript and, when --node-modules is given, a
                         symlinked node_modules so eslint and tsc can run
    truth/               expected.json per language, outside both of the above

Reviewers are pointed at skill/auditline and inputs/<language>; scoring uses truth/.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHIPPED = ("SKILL.md", "README.md", "refs", "tooling")
LANGS = {"python": ".py", "node": ".mjs", "typescript": ".tsx"}
# Corpus files get neutral, shuffled names in the bundle so that a reviewer is not told which file
# is clean. The map is written to the truth directory; scoring translates names back.
NEUTRAL = {
    "sample_bad_1": "module_c",
    "sample_good_1": "module_a",
    "sample_bad_2": "module_e",
    "sample_good_2": "module_b",
    "sample_bad_3_tests": "module_e.test",
}
TSCONFIG = {
    "compilerOptions": {
        "target": "ES2022",
        "module": "ESNext",
        "moduleResolution": "Bundler",
        "jsx": "react-jsx",
        "strict": True,
        "noEmit": True,
        "skipLibCheck": True,
        "types": [],
    },
    "include": ["*.tsx", "*.ts"],
}


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument(
        "--truth-out",
        type=Path,
        help="where to put expected.json files (default: OUT/truth); keep it outside OUT "
        "when reviewers are given OUT",
    )
    ap.add_argument(
        "--keep-names",
        action="store_true",
        help="keep the sample_bad_*/sample_good_* names (a reviewer can then tell them apart)",
    )
    ap.add_argument(
        "--no-skill",
        action="store_true",
        help="leave the skill out, for the no-skill baseline",
    )
    ap.add_argument(
        "--node-modules",
        type=Path,
        help="existing node_modules to symlink into node/typescript",
    )
    args = ap.parse_args()
    out: Path = args.out.resolve()
    if out.exists():
        shutil.rmtree(out)
    skill = out / "skill" / "auditline"
    out.mkdir(parents=True)
    if not args.no_skill:
        skill.mkdir(parents=True)
    for name in () if args.no_skill else SHIPPED:
        src = ROOT / name
        if src.is_dir():
            shutil.copytree(
                src, skill / name, ignore=shutil.ignore_patterns("__pycache__")
            )
        elif src.exists():
            shutil.copy2(src, skill / name)
    if not args.no_skill:
        # the final gate in SKILL.md runs this; it holds no ground truth, unlike verification/
        (skill / "verification").mkdir()
        shutil.copy2(
            ROOT / "verification" / "validate_report.py", skill / "verification"
        )
    truth = (args.truth_out or out / "truth").resolve()
    truth.mkdir(parents=True, exist_ok=True)
    for lang, ext in LANGS.items():
        corpus = ROOT / "verification" / lang
        dest = out / "inputs" / lang
        dest.mkdir(parents=True)
        names: dict[str, str] = {}
        for src in sorted(corpus.glob(f"sample_*{ext}")):
            stem = src.name[: -len(ext)]
            neutral = NEUTRAL[stem]
            if ext == ".py" and neutral.endswith(".test"):
                neutral = "test_" + neutral.removesuffix(".test")  # pytest naming
            target = src.name if args.keep_names else neutral + ext
            text = src.read_text(encoding="utf-8")
            if not args.keep_names:
                for old_stem, new_stem in NEUTRAL.items():
                    if "." not in new_stem:  # only modules are imported, never tests
                        text = text.replace(old_stem, new_stem)
            (dest / target).write_text(text, encoding="utf-8")
            names[target] = src.name
        (truth / f"{lang}_names.json").write_text(
            json.dumps(names, indent=2), encoding="utf-8"
        )
        shutil.copy2(corpus / "expected.json", truth / f"{lang}.json")
        if lang == "typescript":
            (dest / "tsconfig.json").write_text(
                json.dumps(TSCONFIG, indent=2), encoding="utf-8"
            )
        if args.node_modules and lang in {"node", "typescript"}:
            (dest / "node_modules").symlink_to(
                args.node_modules.resolve(), target_is_directory=True
            )
        print(f"{lang}: {len(names)} files")
    leaked = [
        p for p in (out / "skill").rglob("*") if p.name in {"expected.json", "baseline"}
    ]
    if leaked:
        print(f"ground truth leaked into the bundle: {leaked}", file=sys.stderr)
        return 1
    print(f"bundle ready: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
