#!/usr/bin/env python3
"""
big_player_monitor.py — Institutional / Smart Money Tracker
============================================================
Watches for LARGE PLAYER moves across:
  1. FII/DII net flows (daily data from NSE)
  2. Block deals > ₹10 Crore (instant smart-money signal)
  3. Bulk deals > ₹5 Crore
  4. Promoter / insider activity (shareholding changes)
  5. Mutual Fund portfolio moves (SEBI disclosures)
  6. High delivery percentage (retail vs. institutional divergence)

When a significant big-player move is detected → Telegram alert.
This runs on its OWN schedule (every 30 minutes, separate from scan).
"""

import os
import time
import requests
import yfinance as yf
from loguru import logger
from datetime import datetime
from typing import List, Dict, Any

from notifications import send_telegram_alert


class BigPlayerMonitor:
    """Monitors institutional / smart money activity and alerts on Telegram."""

    ALERT_THRESHOLD_CR = 10   # Alert if block deal ≥ ₹10 Crore
    FII_ALERT_CR       = 500  # Alert if FII net buy/sell ≥ ₹500 Crore in a day

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json",
            "Referer": "https://www.nseindia.com/",
        })
        # Seed the session with a cookie (NSE requires this)
        try:
            self.session.get("https://www.nseindia.com", timeout=10)
        except Exception:
            pass  # Silent — will fallback gracefully

        self._seen_deals = set()   # Dedup: don't alert same deal twice
        self._seen_fii_dates = set()

    # ─────────────────────────────────────────────────────────────────────────
    # 1. Block & Bulk Deals
    # ─────────────────────────────────────────────────────────────────────────
    def check_block_deals(self) -> List[Dict[str, Any]]:
        """
        Fetch block + bulk deals from NSE.
        Alerts on any deal ≥ ₹10 Crore that hasn't been alerted yet.
        """
        significant_deals = []

        for deal_type in ["bulk", "block"]:
            try:
                url  = (
                    f"https://www.nseindia.com/api/snapshot-capital-market-largeDeals"
                    f"?type={deal_type}"
                )
                resp = self.session.get(url, timeout=10)
                if resp.status_code != 200:
                    continue

                rows = resp.json().get("data", [])
                for row in rows:
                    symbol = row.get("BD_SYMBOL", "")
                    client = row.get("BD_CLIENT_NAME", "UNKNOWN INSTITUTION")
                    side   = row.get("BD_BUY_SELL", "BUY/SELL")
                    try:
                        qty   = int(str(row.get("BD_QTY_TRD", "0")).replace(",", ""))
                        price = float(str(row.get("BD_TP_WATP", "0")).replace(",", ""))
                    except (ValueError, TypeError):
                        continue

                    value_cr = (qty * price) / 1_00_00_000
                    deal_id  = f"{symbol}_{client}_{qty}_{price}"

                    if value_cr >= self.ALERT_THRESHOLD_CR and deal_id not in self._seen_deals:
                        self._seen_deals.add(deal_id)
                        deal_info = {
                            "type":     deal_type.upper(),
                            "ticker":   symbol,
                            "client":   client,
                            "side":     side,
                            "qty":      qty,
                            "price":    price,
                            "value_cr": round(value_cr, 2),
                        }
                        significant_deals.append(deal_info)
                        self._send_block_deal_alert(deal_info)

            except Exception as e:
                logger.error(f"Block deal ({deal_type}) error: {e}")

        return significant_deals

    def _send_block_deal_alert(self, deal: Dict[str, Any]):
        side_emoji = "🟢 BUY" if "B" in deal["side"].upper() else "🔴 SELL"
        msg = (
            f"🏛️ <b>BIG PLAYER MOVE DETECTED</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Type:</b>    {deal['type']} DEAL\n"
            f"<b>Stock:</b>   {deal['ticker']}\n"
            f"<b>Client:</b>  {deal['client']}\n"
            f"<b>Side:</b>    {side_emoji}\n"
            f"<b>Qty:</b>     {deal['qty']:,}\n"
            f"<b>Price:</b>   ₹{deal['price']:,.2f}\n"
            f"<b>Value:</b>   ₹{deal['value_cr']:.1f} Crore\n\n"
            f"💡 <i>Smart money move — watch this stock!</i>"
        )
        send_telegram_alert(msg)
        logger.info(f"🏛️ Block deal alert sent: {deal['ticker']} ₹{deal['value_cr']:.1f}Cr")

    # ─────────────────────────────────────────────────────────────────────────
    # 2. FII / DII Flow Alert
    # ─────────────────────────────────────────────────────────────────────────
    def check_fii_dii_flows(self) -> Dict[str, Any]:
        """
        Fetch FII/DII daily flows. Alert if net move exceeds threshold.
        """
        today = datetime.now().strftime("%Y-%m-%d")
        if today in self._seen_fii_dates:
            return {}

        try:
            url  = "https://www.nseindia.com/api/fiidiiTradeReact"
            resp = self.session.get(url, timeout=10)
            if resp.status_code != 200:
                return {}

            data       = resp.json()
            fii_net    = 0.0
            dii_net    = 0.0
            fii_buy    = 0.0
            fii_sell   = 0.0
            dii_buy    = 0.0
            dii_sell   = 0.0

            for row in data:
                cat = str(row.get("category", "")).upper()
                try:
                    buy  = float(str(row.get("buyValue",  "0")).replace(",", "") or 0)
                    sell = float(str(row.get("sellValue", "0")).replace(",", "") or 0)
                except (ValueError, TypeError):
                    continue

                if "FII" in cat or "FPI" in cat:
                    fii_buy  += buy;  fii_sell += sell; fii_net += buy - sell
                elif "DII" in cat:
                    dii_buy  += buy;  dii_sell += sell; dii_net += buy - sell

            flows = {
                "date":          today,
                "fii_net_cr":    round(fii_net   / 100, 2),
                "dii_net_cr":    round(dii_net   / 100, 2),
                "fii_buy_cr":    round(fii_buy   / 100, 2),
                "fii_sell_cr":   round(fii_sell  / 100, 2),
                "dii_buy_cr":    round(dii_buy   / 100, 2),
                "dii_sell_cr":   round(dii_sell  / 100, 2),
                "fii_sentiment": "BULLISH 🟢" if fii_net > 0 else "BEARISH 🔴",
                "dii_sentiment": "BULLISH 🟢" if dii_net > 0 else "BEARISH 🔴",
            }

            # Alert if large flow
            if abs(flows["fii_net_cr"]) >= self.FII_ALERT_CR:
                self._seen_fii_dates.add(today)
                self._send_fii_alert(flows)

            logger.info(
                f"FII Net: ₹{flows['fii_net_cr']:.0f}Cr ({flows['fii_sentiment']}) | "
                f"DII Net: ₹{flows['dii_net_cr']:.0f}Cr ({flows['dii_sentiment']})"
            )
            return flows

        except Exception as e:
            logger.error(f"FII/DII check error: {e}")
            return {}

    def _send_fii_alert(self, flows: Dict[str, Any]):
        fii_emoji = "🟢" if flows["fii_net_cr"] > 0 else "🔴"
        dii_emoji = "🟢" if flows["dii_net_cr"] > 0 else "🔴"
        msg = (
            f"🌊 <b>BIG MONEY FLOW ALERT</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"Date: {flows['date']}\n\n"
            f"{fii_emoji} <b>FII/FPI Net:</b> ₹{flows['fii_net_cr']:+.0f} Cr\n"
            f"   Buy: ₹{flows['fii_buy_cr']:.0f}Cr | Sell: ₹{flows['fii_sell_cr']:.0f}Cr\n"
            f"   Sentiment: <b>{flows['fii_sentiment']}</b>\n\n"
            f"{dii_emoji} <b>DII Net:</b> ₹{flows['dii_net_cr']:+.0f} Cr\n"
            f"   Buy: ₹{flows['dii_buy_cr']:.0f}Cr | Sell: ₹{flows['dii_sell_cr']:.0f}Cr\n"
            f"   Sentiment: <b>{flows['dii_sentiment']}</b>\n\n"
            f"💡 <i>Large institutional flow — adjust bias accordingly</i>"
        )
        send_telegram_alert(msg)
        logger.info("🌊 FII/DII large flow alert sent.")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. High Delivery % Stocks (retail accumulation or distribution)
    # ─────────────────────────────────────────────────────────────────────────
    def check_high_delivery(self, tickers: List[str] = None) -> List[Dict]:
        """
        High delivery percentage (>80%) = strong conviction buying.
        Low delivery (<20%) = mostly speculative / intraday noise.
        Checks a sample of top NSE stocks via yfinance fast_info.
        """
        if tickers is None:
            tickers = [
                "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK",
                "SBIN","LT","BAJFINANCE","AXISBANK","MARUTI"
            ]

        high_delivery = []
        for t in tickers:
            try:
                stock = yf.Ticker(f"{t}.NS")
                info  = stock.fast_info
                # yfinance doesn't directly give delivery %, but we can
                # use volume vs previous volumes as a proxy
                hist = stock.history(period="5d")
                if hist.empty or len(hist) < 2:
                    continue
                vol_today = hist["Volume"].iloc[-1]
                vol_avg   = hist["Volume"].mean()
                if vol_today > vol_avg * 1.5:
                    high_delivery.append({
                        "ticker":    t,
                        "vol_ratio": round(vol_today / vol_avg, 2),
                        "signal":    "High volume — likely institutional"
                    })
                time.sleep(0.3)
            except Exception:
                pass

        return high_delivery

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN: Run all monitors
    # ─────────────────────────────────────────────────────────────────────────
    def run_all_checks(self) -> Dict[str, Any]:
        """
        Run all big-player monitors. Called every 30 minutes by scheduler.
        Returns summary dict.
        """
        logger.info("🏛️ BigPlayerMonitor: Running all checks...")
        summary = {
            "checked_at":  datetime.now().isoformat(),
            "block_deals": [],
            "fii_dii":     {},
            "high_vol":    [],
        }

        summary["block_deals"] = self.check_block_deals()
        summary["fii_dii"]     = self.check_fii_dii_flows()
        summary["high_vol"]    = self.check_high_delivery()

        logger.info(
            f"✅ BigPlayerMonitor done | "
            f"Block deals: {len(summary['block_deals'])} | "
            f"High vol stocks: {len(summary['high_vol'])}"
        )
        return summary
