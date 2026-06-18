#!/opt/venv/bin/python
"""Backward-compatible Context7 skill entrypoint."""

from run import main


if __name__ == "__main__":
    raise SystemExit(main())
