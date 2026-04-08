"""CLI for declarative repository branch materialization."""

import pathlib
import sys

import pydantic

import nacre.config as config_module
import nacre.repository as repository_module

YAML_FILE = "nacre.yaml"


def main() -> int:
    if len(sys.argv) <= 1 and not pathlib.Path(YAML_FILE).exists():
        config_module.NacreSettings(_cli_parse_args=["--help"])

    try:
        settings = config_module.NacreSettings()
    except pydantic.ValidationError as exc:
        missing = [str(e["loc"][0]) for e in exc.errors() if e["type"] == "missing"]
        if missing:
            print(f"nacre: missing required fields: {', '.join(missing)}", file=sys.stderr)
            print(f"Provide them via {YAML_FILE} or CLI args (see nacre --help)", file=sys.stderr)
        else:
            print(f"nacre: {exc}", file=sys.stderr)
        return 1
    repository_module.materialize_repository(settings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
