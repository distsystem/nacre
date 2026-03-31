"""CLI for declarative branch materialization."""

import argparse
import pathlib

from branch_materializer.config import load_spec
from branch_materializer.materialize import materialize_branch


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a branch from a base ref plus ordered layers."
    )
    parser.add_argument("config", type=pathlib.Path, help="Path to TOML config")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    spec = load_spec(args.config)
    materialize_branch(spec)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
