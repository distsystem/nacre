"""CLI for declarative branch materialization."""

import argparse
import pathlib

import nacre.config as config_module
import nacre.materialize as materialize_module


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a branch from a base ref plus ordered layers."
    )
    parser.add_argument("config", type=pathlib.Path, help="Path to YAML config")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    settings = config_module.load_settings(args.config)
    materialize_module.materialize_branch(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
