import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "deploy" / "driver_hub_bundle"
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def main() -> None:
    parser = argparse.ArgumentParser(description="Export driver hub manifest and snapshot.")
    parser.add_argument("--include-disabled", action="store_true")
    parser.add_argument("--groups", default="")
    args = parser.parse_args()

    from runtime.driver_hub import build_manifest, collect_snapshot

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    manifest = build_manifest(include_disabled=bool(args.include_disabled))
    snapshot = collect_snapshot(groups=args.groups, include_disabled=bool(args.include_disabled))

    (OUTPUT_DIR / "drivers_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUTPUT_DIR / "drivers_snapshot.json").write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(str(OUTPUT_DIR))


if __name__ == "__main__":
    main()
