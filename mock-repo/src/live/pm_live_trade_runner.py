#!/usr/bin/env python3
"""
Dry-run stub for pm_live_trade_runner.py
Simulates order placement and return expected JSON schema.
"""
import argparse
import json
import time
import random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--market-slug', default='')
    ap.add_argument('--force-side', default='UP', choices=['UP', 'DOWN'])
    ap.add_argument('--start-equity', type=float, default=100)
    ap.add_argument('--risk-frac', type=float, default=0.05)
    ap.add_argument('--max-notional-usd', type=float, default=5)
    ap.add_argument('--execute', action='store_true')
    ap.add_argument('--close-token-id', default=None)
    ap.add_argument('--close-shares', type=float, default=0)
    ap.add_argument('--close-limit-price', type=float, default=None)
    args = ap.parse_args()

    if args.close_token_id:
        # Close order
        shares = args.close_shares
        limit_px = args.close_limit_price or 0.50
        close_usdc = round(shares * limit_px, 6)
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
        # Simulate a price between 0.70 and 0.95
        simulated_price = round(random.uniform(0.70, 0.95), 4)
        shares = round(stake / simulated_price, 8)
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
            "entry_price": simulated_price
        }

    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
