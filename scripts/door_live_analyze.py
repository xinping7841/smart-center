#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv
import sys
from collections import Counter


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: door_live_analyze.py <monitor_csv>")
        return 2
    path = sys.argv[1]
    rows = []
    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("stable") == "ERR":
                continue
            rows.append(row)

    print(f"rows={len(rows)}")
    print(f"stable={dict(Counter(r.get('stable') for r in rows))}")
    print(f"candidate={dict(Counter(r.get('candidate') for r in rows))}")
    print(f"door_status={dict(Counter(r.get('door_status') for r in rows))}")

    transitions = []
    last = None
    for r in rows:
        s = r.get("stable")
        if s != last:
            transitions.append(
                {
                    "ts": r.get("ts"),
                    "stable": s,
                    "main": r.get("main"),
                    "main_conf": r.get("main_conf"),
                    "aux": r.get("aux"),
                    "aux_conf": r.get("aux_conf"),
                    "confidence": r.get("confidence"),
                }
            )
            last = s

    print(f"transitions={len(transitions)}")
    for item in transitions[-20:]:
        print(
            f"{item['ts']} stable={item['stable']} "
            f"main={item['main']}({item['main_conf']}) "
            f"aux={item['aux']}({item['aux_conf']}) fusion_conf={item['confidence']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
