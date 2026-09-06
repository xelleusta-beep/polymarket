#!/usr/bin/env python3
"""
Dry-run stub for pm_live_trade_runner.py
Uses real entry price from main script, simulates realistic fill.
"""
import argparse
import json
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--market-slug', default='')
    ap.add_argument('--force-side', default='UP', choices=['UP', 'DOWN'])
    ap.add_argument('--start-equity', type=float, default=100)
    ap.add_argument('--risk-frac', type=float, default=0.05)
    ap.add_argument('--max-notional-usd', type=float, default=5)
    ap.add_argument('--entry-price', type=float, default=None, help='Real CLOB ask price from main script')
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--close-token-id', default=None)
    ap.add_argument('--close-shares', type=float, default=0)
    ap.add_argument('--close-limit-price', type=float, default=None)
    args = ap.parse_args()

    if args.close_token_id:
        # Close order - use Gamma API price if available, else entry price
        shares = args.close_shares
        close_px = args.close_limit_price
        if close_px is None or close_px <= 0:
            # Fetch real price from Gamma API
            close_px = _fetch_close_price(args.market_slug)
        if close_px is None or close_px <= 0:
            close_px = 0.50  # absolute fallback
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
        # Open order - use real entry price from main script
        side = args.force_side
        stake = args.max_notional_usd

        if args.entry_price is not None and args.entry_price > 0:
            # Use real CLOB ask price with tiny slippage simulation
            slippage = random.uniform(-0.005, 0.005)
            entry_price = round(min(0.99, max(0.01, args.entry_price + slippage)), 4)
        else:
            entry_price = round(random.uniform(0.70, 0.95), 4)

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


def _fetch_close_price(slug):
    """Fetch current side price from Gamma API for realistic close."""
    try:
        import requests
        import time
        r = requests.get(
            'https://gamma-api.polymarket.com/events',
            params={'slug': slug},
            timeout=8
        )
        data = r.json()
        if not data:
            return None
        mkts = data[0].get('markets', [])
        if not mkts:
            return None
        m = mkts[0]
        outcomes = m.get('outcomes')
        prices = m.get('outcomePrices')
        if not outcomes or not prices:
            return None
        # Parse outcomes and find average price as close estimate
        import json as _json
        if isinstance(outcomes, str):
            outcomes = _json.loads(outcomes)
        if isinstance(prices, str):
            prices = _json.loads(prices)
        # Return average of both sides as realistic close price
        avg = sum(float(p) for p in prices) / len(prices)
        return round(avg, 4)
    except Exception:
        return None


if __name__ == '__main__':
    main()
