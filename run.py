#!/usr/bin/env python3
"""
Algo Monitor — Quick launcher.

Usage:
    python run.py              # Start the full application
    python run.py --dashboard  # Dashboard only (no data feeds)

PAPER TRADING ONLY.
"""

import sys


def main():
    from algo_monitor.main import main as app_main
    app_main()


if __name__ == "__main__":
    main()
