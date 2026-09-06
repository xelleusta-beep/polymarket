#!/usr/bin/env python3
"""
Dry-run stub for pm_live_trade_runner.py
Simulates realistic price movement for testing.
"""
import argparse
import json
import random
import os
import time

STATE_DIR = os.environ.get('BTC5M_STATE_DIR', '/tmp/btc5m_state')


def _save_entry(slug, entry_price, side):
    """Save entry price for close simulation."""
    try:
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(os.path.join(STATE_DIR, f'{slug}.json'), 'w') as f:
            json.dump({'entry': entry_price, 'side': side, 'ts': time.time()}, f)
    except Exception:
        pass


def _load_entry(slug):
    """Load entry price for close simulation."""
    try:
        path = os.path.join(STATE_DIR, f'{slug}.json')
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)
    except Exception:
        pass
    return None


def _simulate_movement(entry_price, side):
    """Simulate realistic 5-min market movement."""
    # Random walk: -8% to +8% (typical 5-min BTC volatility)
    change_pct = random.gauss(0, 0.04)  # mean=0, std=4%
    # Small chance of big move (5%)
    if random.random() < 0.05:
        change_pct = random.uniform(-0.12, 0.12)

    if side == 'UP':
        close_price = entry_price * (1 + change_pct)
    else:
        close_price = entry_price * (1 - change_pct)

    # Clamp between 0.05 and 0.95
    close_price = max(0.05, min(0.95, close_price))
    return round(close_price, 4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--market-slug', default='')
    ap.add_argument('--force-side', default='UP', choices=['UP', 'DOWN'])
    ap.add_argument('--start-equity', type=float, default=100)
    ap.add_argument('--risk-frac', type=float, default=0.05)
    ap.add_argument('--max-notional-usd', type=float, default=5)
    ap.add_argument('--entry-price', type=float, default=None)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--close-token-id', default=None)
    ap.add_argument('--close-shares', type=float, default=0)
    ap.add_argument('--close-limit-price', type=float, default=None)
    args = ap.parse_args()

    if args.close_token_id:
        # Close order - simulate price movement from entry
        shares = args.close_shares
        state = _load_entry(args.market_slug)
        if state and state.get('entry'):
            close_px = _simulate_movement(state['entry'], state.get('side', 'UP'))
        elif args.close_limit_price and args.close_limit_price > 0:
            close_px = _simulate_movement(args.close_limit_price, 'UP')
        else:
            close_px = round(random.uniform(0.40, 0.80), 4)

        close_usdc = round(shares * close_px, 6)
        result = {
            "order_post_result": {
                "success": True,
                "status": "matched",
                "makingAmount": str(round(shares, 8)),
                "takingAmount": str(close_usdc),
                "orderID": f"dry-run-close-{random.randint(1000,9999)}",
                "transactionsHashes": []
            },
            "close_skipped": None
        }
    else:
        # Open order
        side = args.force_side
        stake = args.max_notional_usd

        if args.entry_price is not None and args.entry_price > 0:
            entry_price = round(args.entry_price, 4)
        else:
            entry_price = round(random.uniform(0.70, 0.95), 4)

        # Save for close simulation
        _save_entry(args.market_slug, entry_price, side)

        shares = round(stake / entry_price, 8)
        result = {
            "order_post_result": {
                "success": True,
                "status": "matched",
                "takingAmount": str(shares),
                "makingAmount": str(stake),
                "orderID": f"dry-run-open-{random.randint(1000,9999)}",
                "transactionsHashes": []
            },
            "token_id": f"dry-run-token-{side.lower()}",
            "entry_price": entry_price
        }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
