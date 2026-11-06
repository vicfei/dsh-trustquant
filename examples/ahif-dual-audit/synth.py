"""Deterministic synthetic market for the ahif x TrustQuant dual-audit demo.

Implements aihf's `DataClient` protocol (hedge_fund/data/protocol.py: "Any
class with these methods can be used as a data provider") so the REAL aihf
engine — pipeline, paper broker, hash-chain ledger — runs end to end with no
network, no API key and no LLM (the mandate is pead-only, a quant model).

Everything here is SYNTHETIC and labeled as such: tickers are DEMO*, bars are
a seeded geometric walk, earnings are fabricated 8-K BEAT/MISS rows. The demo's
claim is about the two audit chains, never about the market data.

Determinism: one seed fixes the whole market, so `run_demo.py` reproduces the
same ledger hashes and the same trustquant digests on every run.
"""

from __future__ import annotations

import hashlib
import math
from datetime import date, timedelta

from hedge_fund.data.models import EarningsData, EarningsRecord, Price

SEED = 20260106
FIRST_SESSION = date(2025, 3, 3)    # Monday
LAST_SESSION = date(2025, 6, 12)    # Thursday, inside the second filing window

BENCHMARK = "DEMOBENCH"
UNIVERSE = ["DEMOA", "DEMOB", "DEMOD", "DEMOE"]

# (ticker, report_period, filing_date, eps_surprise) — filed dates are sessions.
# Wave 1 (2025-04-10) and wave 2 (2025-06-09) each mix BEAT and MISS so the
# pead pod holds both winners and flat names at the end of the window.
EARNINGS_EVENTS = [
    ("DEMOA", "2025-03-31", "2025-04-10", "BEAT"),
    ("DEMOB", "2025-03-31", "2025-04-10", "MISS"),
    ("DEMOD", "2025-03-31", "2025-04-10", "BEAT"),
    ("DEMOE", "2025-03-31", "2025-04-10", "BEAT"),
    ("DEMOA", "2025-05-31", "2025-06-09", "MISS"),
    ("DEMOB", "2025-05-31", "2025-06-09", "BEAT"),
    ("DEMOD", "2025-05-31", "2025-06-09", "BEAT"),
    ("DEMOE", "2025-05-31", "2025-06-09", "MISS"),
]

# Per-ticker walk parameters (annualized drift mu, vol sigma).
_WALK = {
    "DEMOA": (0.10, 0.30),
    "DEMOB": (0.18, 0.35),
    "DEMOD": (0.06, 0.25),
    "DEMOE": (0.24, 0.40),
    BENCHMARK: (0.08, 0.12),
}
_START_PRICE = {"DEMOA": 40.0, "DEMOB": 80.0, "DEMOD": 25.0, "DEMOE": 120.0, BENCHMARK: 500.0}


def sessions() -> list[date]:
    """Every weekday in the demo window — the synthetic market's calendar."""
    out, d = [], FIRST_SESSION
    while d <= LAST_SESSION:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _z_stream(ticker: str, n: int) -> list[float]:
    """Deterministic standard-normal draws per ticker (Box-Muller over a
    sha256 counter stream — same seed, same numbers, forever)."""
    out, i = [], 0
    while len(out) < n:
        digest = hashlib.sha256(f"{SEED}|{ticker}|{i}".encode()).digest()
        for j in range(0, 32, 8):
            if len(out) == n:
                break
            u1 = (int.from_bytes(digest[j:j + 4], "big") + 1) / 2**33
            u2 = (int.from_bytes(digest[j + 4:j + 8], "big") + 1) / 2**33
            out.append(math.sqrt(-2.0 * math.log(u1)) * math.cos(2 * math.pi * u2))
        i += 1
    return out


class SyntheticMarket:
    """The seeded market itself: bars for every session, plus the earnings calendar."""

    def __init__(self) -> None:
        self.dates = sessions()
        self.bars: dict[str, dict[str, Price]] = {}
        for ticker, (mu, sigma) in _WALK.items():
            zs = _z_stream(ticker, len(self.dates))
            price = _START_PRICE[ticker]
            bars = {}
            volume = 1_000_000 + (int(hashlib.sha256(f"{SEED}|{ticker}|vol".encode()).hexdigest()[:6], 16) % 7) * 100_000
            for d, z in zip(self.dates, zs):
                dt_ = 1.0 / 252.0
                price *= math.exp((mu - 0.5 * sigma * sigma) * dt_ + sigma * math.sqrt(dt_) * z)
                o = price * math.exp(0.002 * z)
                hi = max(o, price) * (1 + 0.003 * abs(z))
                lo = min(o, price) * (1 - 0.003 * abs(z))
                bars[d.isoformat()] = Price(
                    open=round(o, 4), close=round(price, 4),
                    high=round(hi, 4), low=round(lo, 4),
                    volume=volume + (len(d.isoformat()) % 5) * 10_000,
                    time=d.isoformat(),
                )
            self.bars[ticker] = bars

    def closes_csv(self, path) -> int:
        """Write the fund's pricing source of truth as a trustquant market CSV
        (date,ticker,close — ascending, deduped; ADR-0005 rules)."""
        rows = 0
        with open(path, "w") as fh:
            fh.write("date,ticker,close\n")
            for d in self.dates:
                for t in UNIVERSE:
                    fh.write(f"{d.isoformat()},{t},{self.bars[t][d.isoformat()].close}\n")
                    rows += 1
        return rows


class SyntheticDataClient:
    """aihf DataClient protocol over the SyntheticMarket. Fail-loud on an
    unknown ticker (protocol contract); infrastructure never returns empty."""

    def __init__(self, market: SyntheticMarket) -> None:
        self.market = market

    # -- prices --------------------------------------------------------------

    def get_prices(self, ticker, start_date, end_date, interval="day", interval_multiplier=1):
        if interval != "day" or interval_multiplier != 1:
            raise ValueError(f"synthetic market has daily bars only (got {interval} x{interval_multiplier})")
        bars = self.market.bars.get(ticker)
        if bars is None:
            raise ValueError(f"unknown synthetic ticker {ticker!r}")
        return [bars[d] for d in sorted(bars) if start_date <= d <= end_date]

    def get_snapshot(self, ticker):
        return None  # daily cadence never asks for a live quote

    # -- earnings ------------------------------------------------------------

    def get_earnings_history(self, ticker, limit=12):
        bars = self.market.bars.get(ticker)
        if bars is None:
            raise ValueError(f"unknown synthetic ticker {ticker!r}")
        rows = [
            EarningsRecord(
                ticker=ticker,
                report_period=report,
                source_type="8-K",
                filing_date=filed,
                quarterly=EarningsData(
                    eps_surprise=surprise,
                    estimated_earnings_per_share=1.00,
                    earnings_per_share=1.10 if surprise == "BEAT" else 0.90,
                ),
            )
            for (t, report, filed, surprise) in EARNINGS_EVENTS
            if t == ticker
        ]
        return sorted(rows, key=lambda r: r.filing_date, reverse=True)[:limit]

    # -- everything else: the pead pod never asks; LLM agents would --------

    def get_financial_metrics(self, ticker, end_date, period="ttm", limit=10):
        return []

    def get_news(self, ticker, end_date, start_date=None, limit=1000):
        return []

    def get_insider_trades(self, ticker, end_date, start_date=None, limit=1000):
        return []

    def get_company_facts(self, ticker):
        return None

    def get_earnings(self, ticker):
        return None

    def get_market_cap(self, ticker, end_date):
        return None
