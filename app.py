#!/usr/bin/env python3
"""
BTC 5m Polymarket Dry-Run Bot - Render Deployment
Flask server with background trading bot for keep-alive.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify

app = Flask(__name__)

# --- Bot State ---
bot_state = {
    "status": "starting",
    "started_at": None,
    "last_trade": None,
    "total_trades": 0,
    "trades": [],
    "pid": None,
    "profile": os.environ.get("BTC5M_PROFILE", "conservative"),
    "errors": [],
}

bot_thread = None
bot_process = None


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_bot():
    """Run the trading bot as a subprocess in a loop."""
    global bot_process

    repo = os.environ.get("BTC5M_REPO", "/app/mock-repo")
    runner = str(Path(__file__).parent / "scripts" / "test_btc_5m_session_exit_sl.py")
    profile = bot_state["profile"]
    poll_sec = os.environ.get("BTC5M_POLL_SEC", "3")
    entry_timeout = os.environ.get("BTC5M_ENTRY_TIMEOUT_MIN", "10")

    bot_state["status"] = "running"
    bot_state["started_at"] = utc_now()

    while True:
        try:
            cmd = [
                sys.executable,
                runner,
                "--repo", repo,
                "--profile", profile,
                "--entry-timeout-min", entry_timeout,
                "--poll-sec", poll_sec,
            ]
            # Dry-run: no --execute flag

            bot_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "BTC5M_REPO": repo},
            )
            bot_state["pid"] = bot_process.pid

            stdout, stderr = bot_process.communicate()

            if stdout:
                try:
                    result = json.loads(stdout)
                    bot_state["last_trade"] = {
                        "at": utc_now(),
                        "result": result.get("result"),
                        "opened": result.get("opened"),
                        "closed": result.get("closed"),
                        "pnl": result.get("realized_cashflow_pnl_usdc"),
                    }
                    bot_state["total_trades"] += 1
                    bot_state["trades"].append(bot_state["last_trade"])
                    # Keep only last 20 trades in memory
                    if len(bot_state["trades"]) > 20:
                        bot_state["trades"] = bot_state["trades"][-20:]
                except json.JSONDecodeError:
                    pass

            if stderr and "error" in stderr.lower():
                bot_state["errors"].append({
                    "at": utc_now(),
                    "msg": stderr[:500],
                })
                if len(bot_state["errors"]) > 10:
                    bot_state["errors"] = bot_state["errors"][-10:]

        except Exception as e:
            bot_state["errors"].append({
                "at": utc_now(),
                "msg": str(e)[:500],
            })
            bot_state["status"] = "error"

        # Wait before next cycle
        time.sleep(5)


@app.route("/")
def index():
    return jsonify({
        "service": "BTC 5m Polymarket Dry-Run Bot",
        "status": bot_state["status"],
        "profile": bot_state["profile"],
        "uptime_since": bot_state["started_at"],
    })


@app.route("/health")
def health():
    """Health endpoint - keeps Render free tier alive."""
    return jsonify({"status": "ok", "ts": utc_now()}), 200


@app.route("/status")
def status():
    """Detailed bot status."""
    return jsonify(bot_state)


@app.route("/trades")
def trades():
    """List recent trades."""
    return jsonify({
        "total": bot_state["total_trades"],
        "trades": bot_state["trades"],
    })


if __name__ == "__main__":
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()

    # Run Flask server
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
