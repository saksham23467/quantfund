#!/usr/bin/env python3
import json

from quantfund.phase21.pipeline import run_phase21_recovery


def main() -> None:
    print(json.dumps(run_phase21_recovery(), indent=2, default=str))


if __name__ == "__main__":
    main()
