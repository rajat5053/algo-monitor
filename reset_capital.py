#!/usr/bin/env python3
"""
Algo Monitor — Capital Reset Utility.

Allows resetting the paper trading balance to a specific capital amount,
with options to clear previous paper trades or preserve trade history.
Safe: Preserves historical candle data and Upstox auth tokens.

Usage:
    python reset_capital.py                    # Reset to PAPER_TRADING_BALANCE in .env (default: 20,000)
    python reset_capital.py --capital 50000    # Reset to custom amount (e.g. ₹50,000)
    python reset_capital.py --keep-trades      # Update balance only, keep previous trades
"""

from __future__ import annotations

import argparse
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


def update_env_file(env_path: Path, new_capital: float) -> bool:
    """Update PAPER_TRADING_BALANCE and INDIAN_MARKET_CAPITAL in .env file if it exists."""
    if not env_path.exists():
        return False

    content = env_path.read_text(encoding="utf-8")
    val_str = str(int(new_capital) if new_capital.is_integer() else new_capital)
    pattern_bal = r"^(PAPER_TRADING_BALANCE\s*=\s*)(.*)$"
    pattern_ind = r"^(INDIAN_MARKET_CAPITAL\s*=\s*)(.*)$"

    if re.search(pattern_bal, content, flags=re.MULTILINE):
        content = re.sub(pattern_bal, f"PAPER_TRADING_BALANCE={val_str}", content, flags=re.MULTILINE)
    else:
        content = content.rstrip() + f"\nPAPER_TRADING_BALANCE={val_str}\n"

    if re.search(pattern_ind, content, flags=re.MULTILINE):
        content = re.sub(pattern_ind, f"INDIAN_MARKET_CAPITAL={val_str}", content, flags=re.MULTILINE)
    else:
        content = content.rstrip() + f"\nINDIAN_MARKET_CAPITAL={val_str}\n"

    env_path.write_text(content, encoding="utf-8")
    return True


def get_default_env_capital(env_path: Path) -> float:
    """Read INDIAN_MARKET_CAPITAL or PAPER_TRADING_BALANCE from .env or return 20000.0."""
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for line in lines:
            line = line.strip()
            if line.startswith("INDIAN_MARKET_CAPITAL="):
                try:
                    return float(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
        for line in lines:
            line = line.strip()
            if line.startswith("PAPER_TRADING_BALANCE="):
                try:
                    return float(line.split("=", 1)[1].strip())
                except ValueError:
                    pass
    return 20000.0


def reset_capital(
    db_path: Path,
    capital: float,
    clear_trades: bool = True,
    update_env: bool = True,
    env_path: Path | None = None,
) -> None:
    """Reset simulated paper trading capital in SQLite database."""
    if not db_path.exists():
        print(f"[!] Database file not found at {db_path}. Run the application first to initialise.")
        return

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 1. Fetch current balance
    cursor.execute("SELECT value FROM system_state WHERE key = 'paper_balance'")
    row = cursor.fetchone()
    old_balance = float(row["value"]) if row else None

    # Count existing data
    cursor.execute("SELECT COUNT(*) FROM trades")
    trade_count = cursor.fetchone()[0]

    cursor.execute("SELECT COUNT(*) FROM daily_pnl")
    pnl_count = cursor.fetchone()[0]

    print("\n" + "=" * 60)
    print("  Algo Monitor — Capital & State Reset")
    print("=" * 60)
    print(f"[*] Target Database:     {db_path.resolve()}")
    print(f"[*] Previous Balance:    ₹{old_balance:,.2f}" if old_balance is not None else "[*] Previous Balance:    Not set")
    print(f"[*] New Capital:         ₹{capital:,.2f}")
    print(f"[*] Trade Records:       {trade_count} trades")
    print("-" * 60)

    now_iso = datetime.now(timezone.utc).isoformat()

    # 2. Update paper_balance in system_state
    cursor.execute(
        """
        INSERT INTO system_state (key, value, updated_at)
        VALUES ('paper_balance', ?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at
        """,
        (str(capital), now_iso),
    )

    # 3. Handle trades and PnL
    if clear_trades:
        cursor.execute("DELETE FROM trade_management")
        cursor.execute("DELETE FROM trades")
        cursor.execute("DELETE FROM daily_pnl")
        # Reset signal trade flags
        cursor.execute("UPDATE signals SET was_traded = 0")
        print("[+] Cleared past paper trades, trade evaluations, and daily P&L.")
    else:
        print("[i] Keeping existing trade records (--keep-trades specified).")

    conn.commit()
    conn.close()

    # 4. Update .env file
    if update_env and env_path and env_path.exists():
        if update_env_file(env_path, capital):
            print(f"[+] Updated PAPER_TRADING_BALANCE={capital:,.0f} in .env")

    print("[+] Capital successfully updated to: ₹{:,.2f}".format(capital))
    print("=" * 60)
    print("Note: Candle history (OHLCV) and Upstox auth tokens were safely preserved.")
    print("Restart your application (`python run.py`) to trade with the new capital.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Reset Algo Monitor paper trading capital and simulated state."
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=None,
        help="New capital amount in INR (e.g. 15000, 50000). Defaults to PAPER_TRADING_BALANCE in .env",
    )
    parser.add_argument(
        "--keep-trades",
        action="store_true",
        help="Preserve existing trade records and daily P&L history (only updates balance)",
    )
    parser.add_argument(
        "--no-env-update",
        action="store_true",
        help="Do not update PAPER_TRADING_BALANCE in .env file",
    )
    parser.add_argument(
        "--db",
        type=str,
        default="./algo_monitor.db",
        help="Path to SQLite database file (default: ./algo_monitor.db)",
    )

    args = parser.parse_args()

    project_root = Path(__file__).resolve().parent
    env_path = project_root / ".env"
    db_path = Path(args.db).resolve()

    capital = args.capital
    if capital is None:
        capital = get_default_env_capital(env_path)

    if capital <= 0:
        print(f"[!] Invalid capital amount: {capital}. Must be positive.")
        sys.exit(1)

    reset_capital(
        db_path=db_path,
        capital=capital,
        clear_trades=not args.keep_trades,
        update_env=not args.no_env_update,
        env_path=env_path,
    )


if __name__ == "__main__":
    main()
