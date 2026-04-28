#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import shutil
import tempfile
from pathlib import Path

from ultralytics import YOLO


def _count_images(root: Path, split: str, label: str) -> int:
    d = root / split / label
    if not d.exists():
        return 0
    return sum(1 for p in d.glob("*") if p.is_file())


def _prepare_dataset(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    for split in ("train", "val"):
        for label in ("open", "closed"):
            src_dir = src / split / label
            dst_dir = dst / split / label
            dst_dir.mkdir(parents=True, exist_ok=True)
            if not src_dir.exists():
                continue
            for p in src_dir.glob("*"):
                if p.is_file():
                    shutil.copy2(p, dst_dir / p.name)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--run-name", required=True)
    parser.add_argument("--epochs", type=int, default=24)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=24)
    parser.add_argument("--device", default="0")
    args = parser.parse_args()

    src = Path(args.dataset_root).resolve()
    out_path = Path(args.output).resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    run_root = Path("/srv/smart-center-data/runtime/door_retrain_runs") / args.run_name
    run_root.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="door_cls_train_") as tmp:
        ds = Path(tmp) / "dataset"
        _prepare_dataset(src, ds)

        stats = {
            "train_open": _count_images(ds, "train", "open"),
            "train_closed": _count_images(ds, "train", "closed"),
            "val_open": _count_images(ds, "val", "open"),
            "val_closed": _count_images(ds, "val", "closed"),
        }
        if min(stats.values()) < 20:
            print(json.dumps({"status": "error", "reason": "dataset_too_small", **stats}, ensure_ascii=False))
            return 2

        base_model = "/srv/smart-center/models/yolo11n-cls.pt"
        if not Path(base_model).exists():
            base_model = "yolo11n-cls.pt"
        model = YOLO(base_model)
        results = model.train(
            data=str(ds),
            epochs=max(1, int(args.epochs)),
            imgsz=max(96, int(args.imgsz)),
            batch=max(4, int(args.batch)),
            device=args.device,
            amp=True,
            project=str(run_root),
            name="door_state_cls",
            exist_ok=True,
            pretrained=True,
            cache=False,
            verbose=False,
        )
        best = Path(getattr(results, "save_dir", run_root / "door_state_cls")) / "weights" / "best.pt"
        if not best.exists():
            print(json.dumps({"status": "error", "reason": "best_not_found", "best": str(best)}, ensure_ascii=False))
            return 3
        shutil.copy2(best, out_path)
        print(
            json.dumps(
                {
                    "status": "ok",
                    "output": str(out_path),
                    "run_root": str(run_root),
                    **stats,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
