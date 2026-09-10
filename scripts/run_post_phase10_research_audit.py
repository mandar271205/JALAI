"""One-command flood/risk audit; never trains or opens rainfall event stores."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from jalrakshak_ml.research.post_physics import run_audit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-only', action='store_true', help='Write reports only; no array exports')
    parser.add_argument('--benchmark', action='store_true', help='Repeat measured CPU inference timings')
    parser.add_argument('--strict', action='store_true', help='Exit 2 if scientific readiness gates remain closed')
    parser.add_argument('--output-dir', type=Path, default=ROOT / 'reports')
    args = parser.parse_args()
    return run_audit(ROOT, args.output_dir.resolve(), audit_only=args.audit_only,
                     benchmark=args.benchmark, strict=args.strict)


if __name__ == '__main__':
    raise SystemExit(main())
