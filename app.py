#!/usr/bin/env python3
"""
BTC 5m Polymarket Dry-Run Bot - Render Deployment
Flask server with background trading bot + live dashboard.
"""
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, Response

app = Flask(__name__)

STATE_DIR = os.path.join(os.path.dirname(__file__), "runtime")
STATE_FILE = os.path.join(STATE_DIR, "live_state.json")

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
    entry_timeout = os.environ.get("BTC5M_ENTRY_TIMEOUT_MIN", "4")

    bot_state["status"] = "running"
    bot_state["started_at"] = utc_now()

    while True:
        try:
            # Wait until next 5-minute window starts
            now = time.time()
            next_bucket = now - (now % 300) + 300
            wait = max(0, next_bucket - now + 2)  # +2sn safety margin
            if wait > 0:
                time.sleep(wait)

            cmd = [
                sys.executable,
                runner,
                "--repo", repo,
                "--profile", profile,
                "--entry-timeout-min", entry_timeout,
                "--poll-sec", poll_sec,
                "--once",
            ]

            bot_process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={**os.environ, "BTC5M_REPO": repo, "BTC5M_STATE_FILE": STATE_FILE},
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
                    if len(bot_state["trades"]) > 50:
                        bot_state["trades"] = bot_state["trades"][-50:]
                except json.JSONDecodeError:
                    pass

            if stderr and "error" in stderr.lower():
                bot_state["errors"].append({"at": utc_now(), "msg": stderr[:500]})
                if len(bot_state["errors"]) > 10:
                    bot_state["errors"] = bot_state["errors"][-10:]

        except Exception as e:
            bot_state["errors"].append({"at": utc_now(), "msg": str(e)[:500]})
            bot_state["status"] = "error"

        time.sleep(5)


def read_state():
    """Read live state from file written by trading script."""
    try:
        if os.path.exists(STATE_FILE):
            mtime = os.path.getmtime(STATE_FILE)
            if time.time() - mtime < 30:  # fresh within 30 sec
                with open(STATE_FILE, 'r') as f:
                    return json.load(f)
    except Exception:
        pass
    return None


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="tr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BTC 5m Polymarket Bot</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; background: #0a0e17; color: #e1e4e8; min-height: 100vh; }

  .header { background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%); border-bottom: 1px solid #21262d; padding: 20px 30px; display: flex; justify-content: space-between; align-items: center; }
  .header h1 { font-size: 22px; font-weight: 600; color: #f0f6fc; }
  .header h1 span { color: #58a6ff; }
  .header-right { display: flex; align-items: center; gap: 16px; }
  .badge { padding: 5px 14px; border-radius: 20px; font-size: 12px; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; }
  .badge-running { background: #0d2818; color: #3fb950; border: 1px solid #238636; }
  .badge-stopped { background: #2d1b1b; color: #f85149; border: 1px solid #da3633; }
  .badge-starting { background: #2d2518; color: #d29922; border: 1px solid #9e6a03; }
  .badge-error { background: #2d1b1b; color: #f85149; border: 1px solid #da3633; }
  .clock { color: #8b949e; font-size: 13px; font-variant-numeric: tabular-nums; }

  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }

  .stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
  .stat-card { background: #161b22; border: 1px solid #21262d; border-radius: 12px; padding: 20px; }
  .stat-label { font-size: 12px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.8px; margin-bottom: 8px; }
  .stat-value { font-size: 28px; font-weight: 700; font-variant-numeric: tabular-nums; }
  .stat-sub { font-size: 12px; color: #8b949e; margin-top: 4px; }
  .green { color: #3fb950; }
  .red { color: #f85149; }
  .yellow { color: #d29922; }
  .blue { color: #58a6ff; }

  .panel { background: #161b22; border: 1px solid #21262d; border-radius: 12px; margin-bottom: 24px; overflow: hidden; }
  .panel-header { padding: 16px 20px; border-bottom: 1px solid #21262d; display: flex; justify-content: space-between; align-items: center; }
  .panel-title { font-size: 15px; font-weight: 600; color: #f0f6fc; }
  .panel-body { padding: 0; }

  .active-position { padding: 20px; }
  .position-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; }
  .pos-item { }
  .pos-label { font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
  .pos-value { font-size: 16px; font-weight: 600; }
  .no-position { padding: 40px; text-align: center; color: #484f58; font-size: 14px; }

  table { width: 100%; border-collapse: collapse; }
  th { text-align: left; padding: 12px 16px; font-size: 11px; color: #8b949e; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; border-bottom: 1px solid #21262d; background: #0d1117; position: sticky; top: 0; }
  td { padding: 12px 16px; font-size: 13px; border-bottom: 1px solid #21262d; font-variant-numeric: tabular-nums; }
  tr:hover td { background: #1c2028; }
  .trade-row { transition: background 0.15s; }
  .pnl-positive { color: #3fb950; font-weight: 600; }
  .pnl-negative { color: #f85149; font-weight: 600; }
  .side-up { color: #3fb950; font-weight: 600; }
  .side-down { color: #f85149; font-weight: 600; }
  .result-badge { padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 600; }
  .result-done { background: #0d2818; color: #3fb950; }
  .result-timeout { background: #2d2518; color: #d29922; }

  .log-box { padding: 16px 20px; max-height: 200px; overflow-y: auto; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 12px; line-height: 1.8; color: #8b949e; }
  .log-entry { }
  .log-ts { color: #484f58; }
  .log-msg { color: #f85149; }

  .pulse { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; animation: pulse 2s infinite; }
  .pulse-green { background: #3fb950; }
  @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

  .refresh-bar { position: fixed; bottom: 0; left: 0; right: 0; height: 3px; background: #21262d; z-index: 100; }
  .refresh-progress { height: 100%; background: linear-gradient(90deg, #58a6ff, #3fb950); transition: width 0.3s; width: 0%; }

  @media (max-width: 768px) {
    .container { padding: 12px; }
    .stats-grid { grid-template-columns: repeat(2, 1fr); }
    .stat-value { font-size: 22px; }
    th, td { padding: 8px 10px; font-size: 12px; }
  }
</style>
</head>
<body>

<div class="header">
  <h1><span>BTC 5m</span> Polymarket Bot <span style="color:#484f58;font-size:13px;font-weight:400">Dry-Run</span></h1>
  <div class="header-right">
    <span class="clock" id="clock"></span>
    <span class="badge" id="status-badge">LOADING</span>
  </div>
</div>

<div class="container">
  <div class="stats-grid">
    <div class="stat-card">
      <div class="stat-label">Toplam Islem</div>
      <div class="stat-value blue" id="total-trades">0</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Toplam PnL</div>
      <div class="stat-value" id="total-pnl">$0.00</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Basari Orani</div>
      <div class="stat-value green" id="win-rate">0%</div>
      <div class="stat-sub" id="win-detail">0W / 0L</div>
    </div>
    <div class="stat-card">
      <div class="stat-label">Profil</div>
      <div class="stat-value yellow" id="profile">-</div>
      <div class="stat-sub" id="uptime"></div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <span class="panel-title"><span class="pulse pulse-green"></span> Aktif Pozisyon</span>
    </div>
    <div class="panel-body">
      <div class="active-position" id="active-position">
        <div class="no-position">Acik pozisyon yok - siradaki firsat bekleniyor...</div>
      </div>
    </div>
  </div>

  <div class="panel">
    <div class="panel-header">
      <span class="panel-title">Islem Gecmisi</span>
      <span style="color:#484f58;font-size:12px" id="trade-count"></span>
    </div>
    <div class="panel-body" style="max-height: 400px; overflow-y: auto;">
      <table>
        <thead>
          <tr>
            <th>#</th>
            <th>Zaman (UTC)</th>
            <th>Piyasa</th>
            <th>Taraf</th>
            <th>Giris</th>
            <th>Kapanis</th>
            <th>Maliyet</th>
            <th>Kapanis</th>
            <th>PnL</th>
            <th>Durum</th>
          </tr>
        </thead>
        <tbody id="trades-body">
          <tr><td colspan="10" style="text-align:center;padding:40px;color:#484f58">Henuz islem yok...</td></tr>
        </tbody>
      </table>
    </div>
  </div>

  <div class="panel" id="errors-panel" style="display:none">
    <div class="panel-header">
      <span class="panel-title" style="color:#f85149">Hatalar</span>
    </div>
    <div class="panel-body">
      <div class="log-box" id="errors-box"></div>
    </div>
  </div>
</div>

<div class="refresh-bar"><div class="refresh-progress" id="refresh-bar"></div></div>

<script>
const API = '';
let refreshTimer = null;
let progressTimer = null;

function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent = now.toUTCString().slice(0, -4);
}

function fmtTime(iso) {
  if (!iso) return '-';
  const d = new Date(iso);
  return d.toISOString().slice(11, 19);
}

function fmtMoney(v) {
  if (v == null) return '-';
  const n = parseFloat(v);
  const cls = n >= 0 ? 'pnl-positive' : 'pnl-negative';
  const sign = n >= 0 ? '+' : '';
  return '<span class="' + cls + '">' + sign + '$' + n.toFixed(4) + '</span>';
}

function fmtPrice(v) {
  if (v == null) return '-';
  return parseFloat(v).toFixed(4);
}

function renderDashboard(data) {
  // Status badge
  const badge = document.getElementById('status-badge');
  const st = data.status || 'unknown';
  badge.textContent = st.toUpperCase();
  badge.className = 'badge badge-' + (st === 'running' ? 'running' : st === 'error' ? 'error' : st === 'starting' ? 'starting' : 'stopped');

  // Profile
  document.getElementById('profile').textContent = (data.profile || '-').toUpperCase();

  // Uptime
  if (data.started_at) {
    const diff = Math.floor((Date.now() - new Date(data.started_at).getTime()) / 1000);
    const h = Math.floor(diff / 3600);
    const m = Math.floor((diff % 3600) / 60);
    document.getElementById('uptime').textContent = 'uptime: ' + h + 'sa ' + m + 'dk';
  }

  // Stats
  const trades = data.trades || [];
  document.getElementById('total-trades').textContent = data.total_trades || 0;

  let totalPnl = 0;
  let wins = 0;
  let losses = 0;
  trades.forEach(t => {
    if (t.pnl != null) {
      totalPnl += parseFloat(t.pnl);
      if (parseFloat(t.pnl) >= 0) wins++; else losses++;
    }
  });

  const pnlEl = document.getElementById('total-pnl');
  pnlEl.innerHTML = fmtMoney(totalPnl);

  const wrEl = document.getElementById('win-rate');
  const wr = trades.length > 0 ? Math.round((wins / trades.length) * 100) : 0;
  wrEl.textContent = wr + '%';
  document.getElementById('win-detail').textContent = wins + 'W / ' + losses + 'L';

  // Active position - use live data from state file
  const posEl = document.getElementById('active-position');
  const live = data._live || {};
  const livePos = live.position || {};
  const isLive = live.status === 'position_open' || live.status === 'position_live';

  if (isLive && livePos.market_slug) {
    const o = livePos;
    const livePx = live.live_price != null ? fmtPrice(live.live_price) : '-';
    const sl = live.stop_loss != null ? fmtPrice(live.stop_loss) : '-';
    const secLeft = live.seconds_left != null ? Math.round(live.seconds_left) : '-';
    const pnlLive = (live.live_price && o.entry_price) ? (parseFloat(live.live_price) - parseFloat(o.entry_price)) * parseFloat(o.shares) : null;
    const pnlHtml = pnlLive != null ? fmtMoney(pnlLive) : '-';
    posEl.innerHTML = '<div class="position-grid">' +
      '<div class="pos-item"><div class="pos-label">Piyasa</div><div class="pos-value">' + (o.market_slug||'-') + '</div></div>' +
      '<div class="pos-item"><div class="pos-label">Taraf</div><div class="pos-value ' + (o.side === 'UP' ? 'side-up' : 'side-down') + '">' + (o.side||'-') + '</div></div>' +
      '<div class="pos-item"><div class="pos-label">Giris Fiyati</div><div class="pos-value">' + fmtPrice(o.entry_price) + '</div></div>' +
      '<div class="pos-item"><div class="pos-label">Canli Fiyat</div><div class="pos-value blue">' + livePx + '</div></div>' +
      '<div class="pos-item"><div class="pos-label">Anlik PnL</div><div class="pos-value">' + pnlHtml + '</div></div>' +
      '<div class="pos-item"><div class="pos-label">Stop-Loss</div><div class="pos-value red">' + sl + '</div></div>' +
      '<div class="pos-item"><div class="pos-label">Kalan Sure</div><div class="pos-value yellow">' + secLeft + 's</div></div>' +
      '<div class="pos-item"><div class="pos-label">Pay / Maliyet</div><div class="pos-value">' + parseFloat(o.shares||0).toFixed(2) + ' / $' + parseFloat(o.cost_usdc||0).toFixed(2) + '</div></div>' +
      '</div>' +
      '<div style="margin-top:12px;padding:10px;background:#0d1117;border-radius:8px;font-size:12px;color:#8b949e">' +
      '<span class="pulse pulse-green"></span> CANLI - ' + (live.ts || '') + '</div>';
  } else {
    posEl.innerHTML = '<div class="no-position"><span class="pulse pulse-green"></span> Acik pozisyon yok - siradaki firsat bekleniyor...</div>';
  }

  // Trades table
  const tbody = document.getElementById('trades-body');
  if (trades.length === 0) {
    tbody.innerHTML = '<tr><td colspan="10" style="text-align:center;padding:40px;color:#484f58">Henuz islem yok...</td></tr>';
  } else {
    let html = '';
    for (let i = trades.length - 1; i >= 0; i--) {
      const t = trades[i];
      const o = t.opened || {};
      const c = t.closed || {};
      const sideClass = o.side === 'UP' ? 'side-up' : 'side-down';
      const resultClass = t.result === 'done' ? 'result-done' : 'result-timeout';
      html += '<tr class="trade-row">' +
        '<td style="color:#484f58">' + (i + 1) + '</td>' +
        '<td>' + fmtTime(t.at) + '</td>' +
        '<td style="font-size:11px;color:#8b949e">' + (o.market_slug || '-') + '</td>' +
        '<td class="' + sideClass + '">' + (o.side || '-') + '</td>' +
        '<td>' + fmtPrice(o.entry_price) + '</td>' +
        '<td>' + fmtPrice(c.close_shares ? (parseFloat(c.close_usdc) / parseFloat(c.close_shares)) : null) + '</td>' +
        '<td>$' + parseFloat(o.cost_usdc || 0).toFixed(2) + '</td>' +
        '<td>$' + parseFloat(c.close_usdc || 0).toFixed(2) + '</td>' +
        '<td>' + fmtMoney(t.pnl) + '</td>' +
        '<td><span class="result-badge ' + resultClass + '">' + (c.close_reason || t.result || '-') + '</td>' +
        '</tr>';
    }
    tbody.innerHTML = html;
  }

  document.getElementById('trade-count').textContent = trades.length + ' islem';

  // Errors
  const errPanel = document.getElementById('errors-panel');
  const errBox = document.getElementById('errors-box');
  if (data.errors && data.errors.length > 0) {
    errPanel.style.display = 'block';
    let errHtml = '';
    data.errors.forEach(e => {
      errHtml += '<div class="log-entry"><span class="log-ts">' + fmtTime(e.at) + '</span> <span class="log-msg">' + (e.msg||'') + '</span></div>';
    });
    errBox.innerHTML = errHtml;
  } else {
    errPanel.style.display = 'none';
  }
}

async function refresh() {
  try {
    const [rStatus, rLive] = await Promise.all([
      fetch(API + '/api/status'),
      fetch(API + '/api/live')
    ]);
    const data = await rStatus.json();
    const live = await rLive.json();
    data._live = live;
    renderDashboard(data);
  } catch (e) {
    document.getElementById('status-badge').textContent = 'OFFLINE';
    document.getElementById('status-badge').className = 'badge badge-error';
  }
  document.getElementById('refresh-bar').style.width = '100%';
  setTimeout(() => { document.getElementById('refresh-bar').style.width = '0%'; }, 300);
}

function startAutoRefresh() {
  refresh();
  refreshTimer = setInterval(refresh, 5000);
}

updateClock();
setInterval(updateClock, 1000);
startAutoRefresh();
</script>
</body>
</html>"""


# --- Routes ---

@app.route("/")
def dashboard():
    return Response(DASHBOARD_HTML, content_type="text/html; charset=utf-8")


@app.route("/health")
@app.route("/api/v1/ping")
def health():
    return jsonify({"status": "ok", "ts": utc_now()}), 200


@app.route("/api/status")
def api_status():
    return jsonify(bot_state)


@app.route("/api/trades")
def api_trades():
    return jsonify({"total": bot_state["total_trades"], "trades": bot_state["trades"]})


@app.route("/api/live")
def api_live():
    """Live position state from trading script."""
    state = read_state()
    return jsonify(state or {"status": "idle"})


# Legacy endpoints
@app.route("/status")
def status_legacy():
    return jsonify(bot_state)

@app.route("/trades")
def trades_legacy():
    return jsonify({"total": bot_state["total_trades"], "trades": bot_state["trades"]})


if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=False)
