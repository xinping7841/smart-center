#!/usr/bin/env python3
import json
import os
import subprocess


def main() -> None:
    payload = {
        "brace": "{1,2,3}",
        "pipe": "a|b|c",
        "quote": "a'b\"c",
        "unicode": "\u4e2d\u6587",
    }
    print("PY_SMOKE_START")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print(f"cwd={os.getcwd()}")
    try:
        is_bare = subprocess.check_output(
            ["git", "rev-parse", "--is-bare-repository"],
            text=True,
        ).strip()
    except Exception as exc:
        is_bare = f"git-check-failed:{exc}"
    print(is_bare)
    print("PY_SMOKE_DONE")


if __name__ == "__main__":
    main()
