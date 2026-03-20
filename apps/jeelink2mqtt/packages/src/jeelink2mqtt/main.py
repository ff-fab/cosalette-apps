"""CLI entrypoint for jeelink2mqtt.

Creates the cosalette application via the composition root and
delegates to the framework's CLI (Typer-based), which provides
``--dry-run``, ``--version``, ``--log-level``, and ``--env-file``
flags automatically.
"""

from __future__ import annotations

from jeelink2mqtt.app import create_app


def main() -> None:
    """Run the jeelink2mqtt application."""
    app = create_app()
    app.cli()


if __name__ == "__main__":
    main()
