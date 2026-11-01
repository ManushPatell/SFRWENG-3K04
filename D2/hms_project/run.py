"""Start the local Hospital Monitoring System desktop application."""

import argparse
from pathlib import Path

from hms.service import HMS
from hms.storage import Store
from hms.simulator import Simulator


def build_parser():
    """Create the command-line options needed for the local demo."""

    parser = argparse.ArgumentParser(
        description="Hospital Monitoring System desktop prototype"
    )
    parser.add_argument(
        "--database",
        default=str(Path(__file__).parent / "data" / "hms.sqlite3"),
        help="SQLite file used to persist the demo records",
    )
    parser.add_argument(
        "--no-simulator",
        action="store_true",
        help="Start without the built-in simulated cabinets",
    )
    return parser


def main():
    """Build the application and hand control to the PyQt5 event loop."""

    args = build_parser().parse_args()
    application = HMS(Store(args.database))

    simulator = None
    if not args.no_simulator:
        simulator = Simulator(application)

    application.tick()
    if simulator:
        simulator.tick()

    from hms.desktop import run_desktop

    return run_desktop(application, simulator)


if __name__ == "__main__":
    main()
