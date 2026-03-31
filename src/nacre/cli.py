"""CLI for declarative branch materialization."""

import nacre.config as config_module
import nacre.materialize as materialize_module


def main() -> int:
    settings = config_module.NacreSettings()
    materialize_module.materialize_branch(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
