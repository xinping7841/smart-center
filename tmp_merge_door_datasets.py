#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import hashlib
import json
import shutil
from pathlib import Path


def _collect_images(root: Path):
    out = []
    for split in ("train", "val"):
        for label in ("open", "closed"):
            d = root / split / label
            if not d.exists():
                continue
            for p in sorted(d.glob("*")):
                if p.is_file() and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
                    out.append((split, label, p))
    return out


def _make_short_name(src: Path, img: Path) -> str:
    ext = img.suffix.lower() or ".jpg"
    stem = img.stem[-48:]
    src_name = src.name[:24]
    digest = hashlib.sha1(str(img.resolve()).encode("utf-8")).hexdigest()[:12]
    return f"{src_name}_{digest}_{stem}{ext}"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--inputs", nargs="+", required=True)
    args = parser.parse_args()

    out_root = Path(args.output).resolve()
    out_root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val"):
        for label in ("open", "closed"):
            (out_root / split / label).mkdir(parents=True, exist_ok=True)

    summary = {
        "output": str(out_root),
        "sources": [],
        "copied": {"train": {"open": 0, "closed": 0}, "val": {"open": 0, "closed": 0}},
    }
    seen = set()
    for in_dir in args.inputs:
        src = Path(in_dir).resolve()
        copied = 0
        for split, label, img in _collect_images(src):
            key = str(img.resolve())
            if key in seen:
                continue
            seen.add(key)
            name = _make_short_name(src, img)
            dst = out_root / split / label / name
            idx = 1
            while dst.exists():
                base = name.rsplit(".", 1)
                if len(base) == 2:
                    dst = out_root / split / label / f"{base[0]}_{idx:03d}.{base[1]}"
                else:
                    dst = out_root / split / label / f"{name}_{idx:03d}"
                idx += 1
            shutil.copy2(img, dst)
            summary["copied"][split][label] += 1
            copied += 1
        summary["sources"].append({"path": str(src), "copied": copied})

    manifest = out_root / "merge_manifest.json"
    manifest.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
