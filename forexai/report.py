"""Run reporting: what happened, and whether it can be believed."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import Config
from .metrics import format_metrics
from .walkforward import WalkForwardResult


def _traded_fold_hit_rate(result: WalkForwardResult) -> float:
    """Share of profitable folds, counting only folds that actually traded.

    A fold where every signal was vetoed is not a losing fold - it is an
    abstention, and counting it as a failure would punish the risk filters.
    """
    ft = result.fold_table
    if ft.empty:
        return 0.0
    traded = ft[ft["trades"] > 0]
    if traded.empty:
        return 0.0
    return float((traded["oos_exp_r"] > 0).mean())


def verdict(result: WalkForwardResult) -> tuple[str, list[str]]:
    """Turn the numbers into a go / no-go call with the reasons spelled out."""
    m, b = result.metrics, result.bootstrap
    notes: list[str] = []
    if not m or m.get("trades", 0) == 0:
        why = max(result.signal_blocks.items(), key=lambda kv: kv[1], default=None)
        detail = f" - every bar was blocked by: {why[0]}" if why else ""
        return "NO-GO", [f"no trades were taken{detail}"]

    checks = {
        "positive out-of-sample expectancy": m.get("expectancy_r", 0.0) > 0.05,
        "expectancy is statistically credible": b.get("p_positive", 0.0) >= 0.95,
        "at least 100 out-of-sample trades": m.get("trades", 0) >= 100,
        "profit factor above 1.15": m.get("profit_factor", 0.0) >= 1.15,
        "max drawdown under 20%": m.get("max_drawdown_pct", 100.0) < 20.0,
        "majority of traded folds profitable": _traded_fold_hit_rate(result) >= 0.6,
    }
    for name, ok in checks.items():
        notes.append(f"[{'PASS' if ok else 'FAIL'}] {name}")

    passed = sum(checks.values())
    if passed == len(checks):
        label = "GO TO DEMO"
    elif passed >= 4:
        label = "NOT YET - promising, needs more evidence"
    else:
        label = "NO-GO"

    # Overfitting gap check is advisory, not part of the pass count.
    ft = result.fold_table
    traded = ft[ft["trades"] > 0] if not ft.empty else ft
    if not traded.empty:
        gap = float((traded["is_exp_r"] - traded["oos_exp_r"]).mean())
        notes.append(
            f"[INFO] folds traded: {len(traded)}/{len(ft)}  "
            f"profitable: {_traded_fold_hit_rate(result):.0%}"
        )
        notes.append(
            f"[INFO] mean in-sample minus out-of-sample expectancy: {gap:+.3f} R "
            f"({'healthy' if gap < 0.25 else 'the model is memorising'})"
        )
    return label, notes


def render(result: WalkForwardResult, cfg: Config, title: str = "FOREX AI v2") -> str:
    label, notes = verdict(result)
    lines = [
        f"{title} - walk-forward report",
        f"generated {datetime.now(timezone.utc):%Y-%m-%d %H:%M UTC}",
        "=" * 68,
        "",
        f"symbol            {cfg.instrument.symbol} @ {cfg.data.timeframe}",
        f"data source       {cfg.data.source}",
        f"risk per trade    {cfg.risk.risk_per_trade:.2%} of equity",
        f"planned R:R       1:{cfg.risk.tp_atr_mult / cfg.risk.sl_atr_mult:.1f} "
        f"(stop {cfg.risk.sl_atr_mult:.1f}xATR, target {cfg.risk.tp_atr_mult:.1f}xATR)",
        f"costs             {cfg.costs.spread_pips} pip spread, "
        f"{cfg.costs.slippage_pips} pip slippage/side, "
        f"{cfg.costs.commission_per_lot_roundturn} per lot round turn",
        f"folds             {len(result.folds)} "
        f"(train {cfg.walk_forward.train_bars} / embargo {cfg.walk_forward.embargo_bars} "
        f"/ test {cfg.walk_forward.test_bars} bars)",
        "",
        "-- per fold (out-of-sample) " + "-" * 41,
        result.fold_table.to_string(index=False) if not result.fold_table.empty else "  none",
        "",
        "-- aggregate out-of-sample " + "-" * 42,
        format_metrics(result.metrics),
        "",
        "-- expectancy confidence interval " + "-" * 35,
        f"  mean {result.bootstrap.get('mean_r', float('nan')):+.4f} R  "
        f"95% CI [{result.bootstrap.get('ci_low', float('nan')):+.4f}, "
        f"{result.bootstrap.get('ci_high', float('nan')):+.4f}]  "
        f"P(edge > 0) = {result.bootstrap.get('p_positive', float('nan')):.1%}",
        "",
        "-- top features " + "-" * 53,
    ]
    if not result.importance.empty:
        for name, value in result.importance.head(12).items():
            lines.append(f"  {name:<18} {value:.4f}")
    else:
        lines.append("  (unavailable)")

    if result.signal_blocks or result.rejections:
        lines += ["", "-- why bars were not traded " + "-" * 41]
        total_blocked = sum(result.signal_blocks.values())
        for reason, count in sorted(result.signal_blocks.items(), key=lambda kv: -kv[1]):
            share = 100.0 * count / total_blocked if total_blocked else 0.0
            lines.append(f"  signal gate  {count:>8,}  ({share:4.1f}%)  {reason}")
        for reason, count in sorted(result.rejections.items(), key=lambda kv: -kv[1]):
            lines.append(f"  risk veto    {count:>8,}            {reason}")

    lines += ["", "-- verdict " + "-" * 58, f"  {label}", ""]
    lines += [f"  {n}" for n in notes]
    lines += [
        "",
        "  Reminder: a passing walk-forward is permission to open a DEMO account,",
        "  not a live one. Trade the demo until the live curve matches this report.",
    ]
    return "\n".join(lines)


def save(
    result: WalkForwardResult,
    cfg: Config,
    out_dir: str | Path = "runs",
    name: Optional[str] = None,
) -> Path:
    stamp = name or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    path = Path(out_dir) / stamp
    path.mkdir(parents=True, exist_ok=True)

    (path / "report.txt").write_text(render(result, cfg))
    cfg.dump(path / "config.yaml")
    if not result.trades.empty:
        result.trades.to_csv(path / "trades.csv", index=False)
    if len(result.equity):
        result.equity.to_csv(path / "equity.csv")
    if not result.fold_table.empty:
        result.fold_table.to_csv(path / "folds.csv", index=False)
    label, notes = verdict(result)
    (path / "summary.json").write_text(
        json.dumps(
            {"verdict": label, "checks": notes,
             "metrics": result.metrics, "bootstrap": result.bootstrap},
            indent=2, default=str,
        )
    )
    return path
