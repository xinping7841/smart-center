import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from runtime.driver_hub import build_manifest, collect_snapshot


def parse_args():
    parser = argparse.ArgumentParser(description="Node-RED driver hub bridge")
    parser.add_argument("--action", choices=["manifest", "snapshot"], default="snapshot")
    parser.add_argument("--groups", default="", help="Comma-separated groups, e.g. power,meter,light")
    parser.add_argument("--driver-id", default="", help="Filter by driver_id")
    parser.add_argument("--include-disabled", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.action == "manifest":
        payload = build_manifest(include_disabled=bool(args.include_disabled))
    else:
        payload = collect_snapshot(
            groups=args.groups,
            driver_id=args.driver_id,
            include_disabled=bool(args.include_disabled),
        )
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
