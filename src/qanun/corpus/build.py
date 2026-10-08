"""CLI: convert the source PDF into structured JSON (one record per article)."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from qanun.corpus.parse import build_records
from qanun.corpus.pdf_text import extract_lines
from qanun.corpus.validate import validate_records

log = logging.getLogger(__name__)


def build_corpus(pdf: Path, out: Path, report_path: Path | None = None) -> list[dict]:
    en_lines, ar_lines = extract_lines(pdf)
    records, report = build_records(en_lines, ar_lines)
    problems = validate_records(records, known_issues=report["source_issues"])
    report["validation_errors"] = problems
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    if report_path:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("wrote %d records to %s (%d validation errors)", len(records), out, len(problems))
    return records


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--pdf", type=Path, default=Path("data/raw/egyptian_civil_code.pdf"))
    ap.add_argument("--out", type=Path, default=Path("data/processed/civil_code.json"))
    ap.add_argument("--report", type=Path, default=Path("data/processed/extraction_report.json"))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    records = build_corpus(args.pdf, args.out, args.report)
    errs = json.loads(args.report.read_text(encoding="utf-8"))["validation_errors"]
    if errs:
        raise SystemExit("validation failed:\n  " + "\n  ".join(errs[:20]))
    print(f"OK: {len(records)} articles")


if __name__ == "__main__":
    main()
