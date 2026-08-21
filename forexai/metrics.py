"""Performance statistics.

Expectancy is reported in R (risk units), because that is the only figure that
survives a change of account size. A system with 40% win rate and +0.20R
expectancy is a business; one with 70% win rate and -0.05R expectancy is a slow
way to go broke.
"""

from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd

BARS_PER_YEAR = 24 * 252  # hourly FX bars
TRADING_SECONDS_PER_YEAR = 252 * 24 * 3600


def infer_bars_per_year(index: pd.DatetimeIndex) -> int:
    """Annualisation factor read off the bar spacing.

    Hard-coding hourly bars would inflate the Sharpe of a daily system by a
    factor of five, so the timeframe is measured instead of assumed.
    """
    if index is None or len(index) < 3:
        return BARS_PER_YEAR
    step = pd.Series(index).diff().dropna().median()
    if pd.isna(step) or step.total_seconds() <= 0:
        return BARS_PER_YEAR
    return max(1, int(round(TRADING_SECONDS_PER_YEAR / step.total_seconds())))


def max_drawdown(equity: pd.Series) -> tuple[float, float]:
    """Return (max drawdown fraction, max drawdown in currency)."""
    if equity.empty:
        return 0.0, 0.0
    peak = equity.cummax()
    dd = equity - peak
    frac = (dd / peak.replace(0.0, np.nan)).min()
    return float(abs(frac) if frac == frac else 0.0), float(abs(dd.min()))


def compute_metrics(
    trades: pd.DataFrame,
    equity: pd.Series,
    initial_equity: float,
    bars_per_year: int = BARS_PER_YEAR,
) -> Dict[str, float]:
    n = len(trades)
    final = float(equity.iloc[-1]) if len(equity) else initial_equity
    dd_frac, dd_abs = max_drawdown(equity)

    out: Dict[str, float] = {
        "trades": n,
        "initial_equity": round(initial_equity, 2),
        "final_equity": round(final, 2),
        "total_return_pct": round(100.0 * (final / initial_equity - 1.0), 2),
        "max_drawdown_pct": round(100.0 * dd_frac, 2),
        "max_drawdown_abs": round(dd_abs, 2),
    }
    if n == 0:
        out.update(
            {
                "win_rate_pct": 0.0, "expectancy_r": 0.0, "profit_factor": 0.0,
                "avg_win_r": 0.0, "avg_loss_r": 0.0, "sharpe": 0.0, "sortino": 0.0,
                "calmar": 0.0, "best_r": 0.0, "worst_r": 0.0,
                "avg_bars_held": 0.0, "exposure_pct": 0.0,
            }
        )
        return out

    pnl = trades["pnl"].astype(float)
    r = trades["r_multiple"].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
    wins, losses = pnl[pnl > 0], pnl[pnl <= 0]
    gross_win, gross_loss = wins.sum(), abs(losses.sum())

    out["win_rate_pct"] = round(100.0 * len(wins) / n, 2)
    out["expectancy_r"] = round(float(r.mean()), 4) if len(r) else 0.0
    out["expectancy_currency"] = round(float(pnl.mean()), 2)
    out["profit_factor"] = round(float(gross_win / gross_loss), 3) if gross_loss > 0 else float("inf")
    out["avg_win_r"] = round(float(r[r > 0].mean()), 3) if (r > 0).any() else 0.0
    out["avg_loss_r"] = round(float(r[r <= 0].mean()), 3) if (r <= 0).any() else 0.0
    out["best_r"] = round(float(r.max()), 3) if len(r) else 0.0
    out["worst_r"] = round(float(r.min()), 3) if len(r) else 0.0
    out["avg_bars_held"] = round(float(trades["bars_held"].mean()), 2)

    # Friction attributable to each trade, as a share of the risk taken. It is
    # reported, never added back to build a "gross expectancy": stops and
    # targets are placed relative to the executed entry, so the spread does not
    # shrink a winning trade - it makes winning less likely by moving the
    # levels. The only honest frictionless figure comes from re-running the
    # whole walk-forward with the costs set to zero (see README).
    if "cost_r" in trades.columns:
        cost_r = trades["cost_r"].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
        if len(cost_r):
            out["cost_r_per_trade"] = round(float(cost_r.mean()), 4)
            out["cost_currency_per_trade"] = round(
                float(trades["cost"].astype(float).mean()), 2
            )

    # Bar-level risk-adjusted return on the equity curve.
    rets = equity.pct_change().dropna()
    if len(rets) > 2 and rets.std(ddof=0) > 0:
        ann = np.sqrt(bars_per_year)
        out["sharpe"] = round(float(rets.mean() / rets.std(ddof=0) * ann), 3)
        downside = rets[rets < 0].std(ddof=0)
        out["sortino"] = round(float(rets.mean() / downside * ann), 3) if downside > 0 else 0.0
    else:
        out["sharpe"] = out["sortino"] = 0.0

    years = max(len(equity) / bars_per_year, 1e-9)
    cagr = (final / initial_equity) ** (1.0 / years) - 1.0 if final > 0 else -1.0
    out["cagr_pct"] = round(100.0 * cagr, 2)
    out["calmar"] = round(float(cagr / dd_frac), 3) if dd_frac > 0 else 0.0
    out["exposure_pct"] = round(100.0 * float(trades["bars_held"].sum()) / max(len(equity), 1), 2)

    by_reason = trades["exit_reason"].value_counts(normalize=True) * 100.0
    for reason in ("target", "stop", "timeout"):
        out[f"exit_{reason}_pct"] = round(float(by_reason.get(reason, 0.0)), 2)
    return out


def format_metrics(m: Dict[str, float]) -> str:
    if not m:
        return "  (no results)"
    lines = [
        f"  trades              {m['trades']}",
        f"  win rate            {m.get('win_rate_pct', 0):.2f} %",
        f"  expectancy          {m.get('expectancy_r', 0):+.4f} R  "
        f"({m.get('expectancy_currency', 0):+.2f} per trade)",
        f"  broker friction     {m.get('cost_r_per_trade', float('nan')):.4f} R per trade  "
        f"({m.get('cost_currency_per_trade', float('nan')):.2f} per trade)",
        f"  profit factor       {m.get('profit_factor', 0):.3f}",
        f"  avg win / avg loss  {m.get('avg_win_r', 0):+.2f} R / {m.get('avg_loss_r', 0):+.2f} R",
        f"  total return        {m.get('total_return_pct', 0):+.2f} %",
        f"  CAGR                {m.get('cagr_pct', 0):+.2f} %",
        f"  max drawdown        {m.get('max_drawdown_pct', 0):.2f} %",
        f"  sharpe / sortino    {m.get('sharpe', 0):.2f} / {m.get('sortino', 0):.2f}",
        f"  exits tgt/stop/to   {m.get('exit_target_pct', 0):.0f}% / "
        f"{m.get('exit_stop_pct', 0):.0f}% / {m.get('exit_timeout_pct', 0):.0f}%",
        f"  equity              {m.get('initial_equity', 0):,.0f} -> {m.get('final_equity', 0):,.0f}",
    ]
    return "\n".join(lines)


def bootstrap_expectancy(trades: pd.DataFrame, n_boot: int = 2000, seed: int = 0) -> Dict[str, float]:
    """Confidence interval on expectancy - the antidote to a lucky backtest."""
    r = trades["r_multiple"].astype(float).replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
    if len(r) < 20:
        return {"n": len(r), "mean_r": float(r.mean()) if len(r) else 0.0,
                "ci_low": float("nan"), "ci_high": float("nan"), "p_positive": float("nan")}
    rng = np.random.default_rng(seed)
    means = rng.choice(r, size=(n_boot, len(r)), replace=True).mean(axis=1)
    return {
        "n": int(len(r)),
        "mean_r": round(float(r.mean()), 4),
        "ci_low": round(float(np.percentile(means, 2.5)), 4),
        "ci_high": round(float(np.percentile(means, 97.5)), 4),
        "p_positive": round(float((means > 0).mean()), 4),
    }
