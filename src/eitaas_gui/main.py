"""Console entry point for ``eitaas-gui``.

``--version`` is answered before any toolkit import so packaging checks can
run it without a display or GTK installed.
"""

from __future__ import annotations

import sys

from eitaas import __version__


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv if argv is None else argv)
    if "--version" in arguments[1:]:
        print(f"eitaas-gui {__version__}")
        return 0
    from .app import run

    return run(arguments)


if __name__ == "__main__":
    raise SystemExit(main())
