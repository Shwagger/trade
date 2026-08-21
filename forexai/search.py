"""Strategy search: test thousands of rule sets, and survive the test.

Testing thousands of strategies on the same data is not free. If you try 5 000
random rule sets on a coin-flip market, the best one will look excellent - that
is arithmetic, not skill. Two defences are built into this module and neither
is optional:

1. **A holdout the search never sees.** The data is cut in two before the first
   strategy is generated. Every candidate is ranked on the search segment; only
   the finalists are then run, once, on the holdout. The gap between the two is
   the honest measure.

2. **A deflated Sharpe ratio.** Knowing how many candidates were tried and how
   much their results varied, we can compute what the *best of N* would score
   with no edge at all. A winner that does not clear that bar is noise with a
   good haircut.

The search space is deliberately made of classic, explainable rules - trend,
mean reversion, breakout, momentum - with their parameters and exits. A rule
that works can be read, argued with and traded by hand. A black box that works
cannot be debugged when it stops working.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import asdict, dataclass, replace
from typing import Dict, Iterable, List, Optional, Sequence

import numpy as np
import pandas as pd
from scipy import stats

from . import indicators as ind
from .backtest import Backtester
from .config import Config
from .metrics import compute_metrics
from .risk import RiskManager

EULER_GAMMA = 0.5772156649015329

SESSION_SETS: Dict[str, tuple] = {
    "all": (),
    "active": ("london", "overlap", "newyork"),
    "overlap": ("overlap",),
    "europe": ("london", "overlap"),
}

# Eleven rule families. Between them they cover the overwhelming majority of
# what published FX strategies actually do - the vocabulary is small even when
# the marketing is not. Combined with the filters, exits and parameter ranges
# below, the space is large enough that no human could have written it all down.
FAMILIES = (
    "trend", "revert", "breakout", "momentum",
    "macd_cross", "stoch_cross", "channel_fade", "session_breakout",
    "pullback", "squeeze", "engulfing",
)

# Entry filters, applied on top of any family.
ENTRY_FILTERS = ("none", "htf", "vol", "both")

# Exit styles. "fixed" is stop and target only; the others manage the stop.
EXIT_STYLES: Dict[str, Dict[str, float]] = {
    "fixed": {"breakeven_at_r": 0.0, "trail_atr_mult": 0.0},
    "breakeven": {"breakeven_at_r": 1.0, "trail_atr_mult": 0.0},
    "trail": {"breakeven_at_r": 0.0, "trail_atr_mult": 2.0},
    "be_trail": {"breakeven_at_r": 1.0, "trail_atr_mult": 2.5},
}


@dataclass(frozen=True)
class StrategySpec:
    """One point in the search space. Frozen so it can key a cache."""

    family: str = "trend"
    fast: int = 12
    slow: int = 50
    rsi_period: int = 14
    rsi_band: int = 15
    donchian: int = 20
    adx_min: float = 20.0
    bb_period: int = 20
    bb_mult: float = 2.0
    sl_atr: float = 1.5
    tp_atr: float = 3.0
    hold: int = 48
    sessions: str = "active"
    entry_filter: str = "none"
    exit_style: str = "fixed"

    @property
    def name(self) -> str:
        return (
            f"{self.family}:f{self.fast}/s{self.slow}/rsi{self.rsi_period}"
            f"±{self.rsi_band}/dc{self.donchian}/adx{self.adx_min:g}"
            f"/bb{self.bb_period}x{self.bb_mult:g}"
            f"/sl{self.sl_atr:g}tp{self.tp_atr:g}h{self.hold}"
            f"/{self.sessions}/{self.entry_filter}/{self.exit_style}"
        )

    @property
    def reward_risk(self) -> float:
        return self.tp_atr / self.sl_atr if self.sl_atr > 0 else 0.0


# ----------------------------------------------------------------------
# indicator cache - computed once, reused by every strategy that needs it
# ----------------------------------------------------------------------
class IndicatorCache:
    """Memoises indicator series per (kind, parameters) across the search."""

    def __init__(self, bars: pd.DataFrame, atr_period: int = 14):
        self.bars = bars
        self.close = bars["close"]
        self.atr = ind.atr(bars, atr_period)
        self._ema: Dict[int, pd.Series] = {}
        self._rsi: Dict[int, pd.Series] = {}
        self._adx: Dict[int, pd.Series] = {}
        self._donchian: Dict[int, tuple] = {}
        self._bollinger: Dict[tuple, tuple] = {}
        self._macd: Optional[tuple] = None
        self._stoch: Optional[tuple] = None

    def ema(self, period: int) -> pd.Series:
        if period not in self._ema:
            self._ema[period] = ind.ema(self.close, period)
        return self._ema[period]

    def rsi(self, period: int) -> pd.Series:
        if period not in self._rsi:
            self._rsi[period] = ind.rsi(self.close, period)
        return self._rsi[period]

    def adx(self, period: int = 14) -> pd.Series:
        if period not in self._adx:
            self._adx[period] = ind.adx(self.bars, period)[0]
        return self._adx[period]

    def donchian(self, period: int):
        if period not in self._donchian:
            self._donchian[period] = ind.donchian(self.bars, period)
        return self._donchian[period]

    def macd(self):
        if self._macd is None:
            self._macd = ind.macd(self.close)
        return self._macd

    def stochastic(self):
        if self._stoch is None:
            self._stoch = ind.stochastic(self.bars)
        return self._stoch

    def bollinger(self, period: int, mult: float):
        key = (period, mult)
        if key not in self._bollinger:
            self._bollinger[key] = ind.bollinger(self.close, period, mult)
        return self._bollinger[key]


# ----------------------------------------------------------------------
# rules
# ----------------------------------------------------------------------
def rule_signal(spec: StrategySpec, cache: IndicatorCache) -> pd.Series:
    """Vectorised +1 / -1 / 0 signal. Uses closed-bar values only."""
    close = cache.close
    adx = cache.adx(14)
    trending = adx >= spec.adx_min

    if spec.family == "trend":
        fast, slow = cache.ema(spec.fast), cache.ema(spec.slow)
        long_ = (fast > slow) & (close > slow) & trending
        short = (fast < slow) & (close < slow) & trending

    elif spec.family == "revert":
        _, upper, lower, _, _ = cache.bollinger(spec.bb_period, spec.bb_mult)
        rsi = cache.rsi(spec.rsi_period)
        calm = adx < spec.adx_min                 # fade only when there is no trend
        long_ = (close < lower) & (rsi < 50 - spec.rsi_band) & calm
        short = (close > upper) & (rsi > 50 + spec.rsi_band) & calm

    elif spec.family == "breakout":
        upper, lower, _ = cache.donchian(spec.donchian)
        long_ = (close > upper) & trending
        short = (close < lower) & trending

    elif spec.family == "momentum":
        rsi = cache.rsi(spec.rsi_period)
        rising = rsi.diff(3) > 0
        slow = cache.ema(spec.slow)
        long_ = (rsi > 50 + spec.rsi_band) & rising & (close > slow)
        short = (rsi < 50 - spec.rsi_band) & (~rising) & (close < slow)

    elif spec.family == "macd_cross":
        line, sig, _ = cache.macd()
        crossed_up = (line > sig) & (line.shift(1) <= sig.shift(1))
        crossed_down = (line < sig) & (line.shift(1) >= sig.shift(1))
        slow = cache.ema(spec.slow)
        long_ = crossed_up & (close > slow)
        short = crossed_down & (close < slow)

    elif spec.family == "stoch_cross":
        k, d = cache.stochastic()
        crossed_up = (k > d) & (k.shift(1) <= d.shift(1))
        crossed_down = (k < d) & (k.shift(1) >= d.shift(1))
        long_ = crossed_up & (k < 50 - spec.rsi_band / 2)     # cross from oversold
        short = crossed_down & (k > 50 + spec.rsi_band / 2)

    elif spec.family == "channel_fade":
        upper, lower, _ = cache.donchian(spec.donchian)
        calm = adx < spec.adx_min
        long_ = (close <= lower) & calm
        short = (close >= upper) & calm

    elif spec.family == "session_breakout":
        # Break of the recent range, taken only as the European session opens.
        upper, lower, _ = cache.donchian(spec.donchian)
        hour = pd.Series(close.index.hour, index=close.index)
        opening = hour.between(7, 10)
        long_ = (close > upper) & opening
        short = (close < lower) & opening

    elif spec.family == "pullback":
        # Trend intact, momentum dipped and turned back: buy the retracement.
        slow = cache.ema(spec.slow)
        fast = cache.ema(spec.fast)
        rsi = cache.rsi(spec.rsi_period)
        turning_up = (rsi > rsi.shift(1)) & (rsi.shift(1) <= 50)
        turning_down = (rsi < rsi.shift(1)) & (rsi.shift(1) >= 50)
        long_ = (fast > slow) & (close > slow) & turning_up
        short = (fast < slow) & (close < slow) & turning_down

    elif spec.family == "squeeze":
        # Volatility compressed, then released directionally.
        _, upper, lower, width, _ = cache.bollinger(spec.bb_period, spec.bb_mult)
        compressed = width.shift(1) <= width.shift(1).rolling(100, min_periods=50).quantile(0.25)
        long_ = compressed & (close > upper)
        short = compressed & (close < lower)

    elif spec.family == "engulfing":
        # Forex-adapted engulfing. The textbook pattern needs the open to gap
        # past the previous close, which practically never happens on intraday
        # FX bars: each bar opens where the last one closed. The condition that
        # carries the same meaning here is a body that swallows the previous
        # body and is decisively larger.
        open_ = cache.bars["open"]
        body = close - open_
        prev_body = body.shift(1)
        bigger = body.abs() > prev_body.abs()
        engulf_up = (
            (body > 0) & (prev_body < 0) & bigger
            & (close >= open_.shift(1)) & (open_ <= close.shift(1))
        )
        engulf_down = (
            (body < 0) & (prev_body > 0) & bigger
            & (close <= open_.shift(1)) & (open_ >= close.shift(1))
        )
        slow = cache.ema(spec.slow)
        long_ = engulf_up & (close > slow)
        short = engulf_down & (close < slow)

    else:
        raise ValueError(f"unknown strategy family: {spec.family}")

    long_, short = _apply_entry_filter(spec, cache, long_, short)

    signal = pd.Series(0, index=close.index, dtype=int)
    signal[long_.fillna(False)] = 1
    signal[short.fillna(False)] = -1
    return signal


def _apply_entry_filter(spec: StrategySpec, cache: IndicatorCache, long_, short):
    """Context filters layered on top of a family's raw entry condition."""
    if spec.entry_filter == "none":
        return long_, short

    close = cache.close
    if spec.entry_filter in ("htf", "both"):
        # Higher-timeframe agreement: four times the slow average.
        htf = cache.ema(min(spec.slow * 4, 400))
        long_ = long_ & (close > htf)
        short = short & (close < htf)

    if spec.entry_filter in ("vol", "both"):
        # Skip dead markets and volatility spikes alike.
        atr_ratio = cache.atr / cache.atr.rolling(100, min_periods=50).mean()
        tradable = atr_ratio.between(0.7, 1.6)
        long_ = long_ & tradable
        short = short & tradable

    return long_, short


def signal_frame(spec: StrategySpec, cache: IndicatorCache) -> pd.DataFrame:
    direction = rule_signal(spec, cache)
    return pd.DataFrame(
        {
            "direction": direction,
            "score": direction.astype(float),
            "confidence": (direction != 0).astype(float),
            "ml_score": 0.0,
            "ta_score": direction.astype(float),
            "reason": "rule",
        },
        index=direction.index,
    )


# ----------------------------------------------------------------------
# evaluation
# ----------------------------------------------------------------------
def spec_config(spec: StrategySpec, base: Config) -> Config:
    cfg = Config.from_dict(base.to_dict())
    cfg.risk.sl_atr_mult = spec.sl_atr
    cfg.risk.tp_atr_mult = spec.tp_atr
    cfg.risk.min_reward_risk = min(cfg.risk.min_reward_risk, spec.reward_risk)
    cfg.risk.allowed_sessions = SESSION_SETS[spec.sessions]
    cfg.labels.max_holding_bars = spec.hold
    exit_rules = EXIT_STYLES[spec.exit_style]
    cfg.risk.breakeven_at_r = exit_rules["breakeven_at_r"]
    cfg.risk.trail_atr_mult = exit_rules["trail_atr_mult"]
    return cfg


def evaluate_spec(
    spec: StrategySpec,
    bars: pd.DataFrame,
    cache: IndicatorCache,
    base: Config,
    bars_per_year: int,
) -> Dict[str, float]:
    """Backtest one strategy under the full risk manager and cost model."""
    cfg = spec_config(spec, base)
    signals = signal_frame(spec, cache)
    rm = RiskManager(cfg.risk, cfg.instrument, cfg.costs, cfg.initial_equity)
    result = Backtester(cfg, rm).run(bars, signals, cache.atr)
    metrics = compute_metrics(
        result.trades, result.equity, cfg.initial_equity, bars_per_year=bars_per_year
    )

    r = (
        result.trades["r_multiple"].astype(float).replace([np.inf, -np.inf], np.nan).dropna()
        if not result.trades.empty
        else pd.Series(dtype=float)
    )
    metrics["name"] = spec.name
    metrics["family"] = spec.family
    # Per-trade Sharpe: the quantity the deflation maths below is defined on.
    # A strategy whose trades are all identical (every one a stop-out, say) has
    # near-zero dispersion and would score a Sharpe of -33, which is not
    # information - it is a division by almost nothing. Such trials are clamped
    # so they cannot dominate the cross-sectional spread the deflation uses.
    metrics["trade_sharpe"] = _trade_sharpe(r)
    metrics["t_stat"] = metrics["trade_sharpe"] * math.sqrt(max(len(r), 1))
    metrics["r_skew"] = float(stats.skew(r)) if len(r) > 3 else 0.0
    metrics["r_kurtosis"] = float(stats.kurtosis(r, fisher=False)) if len(r) > 3 else 3.0
    return metrics


MIN_R_DISPERSION = 0.05      # below this, the trade distribution is degenerate
MAX_TRADE_SHARPE = 3.0       # a real per-trade Sharpe above 0.5 is already rare


def _trade_sharpe(r: pd.Series) -> float:
    """Per-trade Sharpe, clamped so degenerate trials cannot poison the search."""
    if len(r) < 3:
        return 0.0
    dispersion = float(r.std(ddof=1))
    if not np.isfinite(dispersion) or dispersion < MIN_R_DISPERSION:
        return 0.0
    return float(np.clip(r.mean() / dispersion, -MAX_TRADE_SHARPE, MAX_TRADE_SHARPE))


def robust_std(values: pd.Series) -> float:
    """Median-absolute-deviation spread, immune to a handful of broken trials."""
    clean = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    if len(clean) < 3:
        return 0.0
    mad = float(np.median(np.abs(clean - clean.median())))
    scaled = 1.4826 * mad
    if scaled > 0:
        return scaled
    return float(clean.std(ddof=1)) if clean.std(ddof=1) > 0 else 0.0


def _evaluate_chunk(
    specs: Sequence[StrategySpec],
    bars: pd.DataFrame,
    config_dict: dict,
    bars_per_year: int,
) -> List[Dict[str, float]]:
    """Worker entry point: one indicator cache shared by the whole chunk."""
    base = Config.from_dict(config_dict)
    cache = IndicatorCache(bars, base.labels.atr_period)
    out = []
    for spec in specs:
        row = evaluate_spec(spec, bars, cache, base, bars_per_year)
        row["spec"] = spec
        out.append(row)
    return out


# ----------------------------------------------------------------------
# the space
# ----------------------------------------------------------------------
DEFAULT_GRID: Dict[str, Sequence] = {
    "family": FAMILIES,
    "fast": (8, 12, 20, 34),
    "slow": (50, 80, 120, 200),
    "rsi_period": (7, 14, 21),
    "rsi_band": (10, 15, 20, 25),
    "donchian": (15, 20, 40, 55),
    "adx_min": (15.0, 20.0, 25.0, 30.0),
    "bb_period": (14, 20, 30),
    "bb_mult": (1.8, 2.0, 2.5),
    "sl_atr": (1.0, 1.5, 2.0),
    "tp_atr": (2.0, 3.0, 4.0, 5.0),
    "hold": (24, 48, 96),
    "sessions": ("all", "active", "overlap", "europe"),
    "entry_filter": ENTRY_FILTERS,
    "exit_style": tuple(EXIT_STYLES),
}


def grid_size(grid: Dict[str, Sequence] = DEFAULT_GRID) -> int:
    total = 1
    for values in grid.values():
        total *= len(values)
    return total


def generate_specs(
    n: Optional[int] = 2_000,
    seed: int = 0,
    grid: Dict[str, Sequence] = DEFAULT_GRID,
    min_reward_risk: float = 1.5,
) -> List[StrategySpec]:
    """Sample the space, dropping combinations that make no sense.

    Random sampling beats a truncated grid: an exhaustive grid explores the
    first parameters thoroughly and never reaches the last ones.
    """
    keys = list(grid)
    combos: Iterable

    if n is None or n >= grid_size(grid):
        combos = itertools.product(*(grid[k] for k in keys))
    else:
        rng = np.random.default_rng(seed)
        seen = set()
        combos = []
        # Oversample: invalid draws are discarded below.
        for _ in range(n * 8):
            if len(combos) >= n * 2:
                break
            draw = tuple(grid[k][rng.integers(len(grid[k]))] for k in keys)
            if draw not in seen:
                seen.add(draw)
                combos.append(draw)

    specs: List[StrategySpec] = []
    for values in combos:
        spec = StrategySpec(**dict(zip(keys, values)))
        if spec.fast >= spec.slow:                     # a fast EMA must be faster
            continue
        if spec.reward_risk < min_reward_risk:         # respect the risk mandate
            continue
        specs.append(spec)
        if n is not None and len(specs) >= n:
            break
    return specs


# ----------------------------------------------------------------------
# multiple-testing correction
# ----------------------------------------------------------------------
def expected_max_sharpe_under_null(n_trials: int, sharpe_std: float) -> float:
    """What the best of ``n_trials`` worthless strategies scores by luck alone.

    Bailey & Lopez de Prado's expected maximum of ``n`` draws from a normal
    distribution of trial Sharpes. With 2 000 trials and a typical spread, this
    is far from zero - which is exactly why an unadjusted "best backtest" means
    nothing.
    """
    if n_trials < 2 or sharpe_std <= 0:
        return 0.0
    a = stats.norm.ppf(1.0 - 1.0 / n_trials)
    b = stats.norm.ppf(1.0 - 1.0 / (n_trials * math.e))
    return float(sharpe_std * ((1.0 - EULER_GAMMA) * a + EULER_GAMMA * b))


def deflated_sharpe(
    observed_sharpe: float,
    n_trades: int,
    n_trials: int,
    sharpe_std: float,
    skew: float = 0.0,
    kurtosis: float = 3.0,
) -> Dict[str, float]:
    """Probability the winner's Sharpe is real rather than the best of N flukes."""
    threshold = expected_max_sharpe_under_null(n_trials, sharpe_std)
    if n_trades < 4:
        return {"threshold": threshold, "dsr": 0.0, "beats_luck": False}

    variance = (
        1.0 - skew * observed_sharpe + 0.25 * (kurtosis - 1.0) * observed_sharpe**2
    ) / (n_trades - 1)
    if variance <= 0:
        return {"threshold": threshold, "dsr": 0.0, "beats_luck": False}

    dsr = float(stats.norm.cdf((observed_sharpe - threshold) / math.sqrt(variance)))
    return {"threshold": threshold, "dsr": dsr, "beats_luck": dsr >= 0.95}


# ----------------------------------------------------------------------
# the search itself
# ----------------------------------------------------------------------
@dataclass
class SearchResult:
    table: pd.DataFrame          # every candidate, ranked, with holdout columns
    finalists: pd.DataFrame      # the top-K, with holdout results filled in
    n_tested: int
    search_span: tuple
    holdout_span: tuple
    deflation: Dict[str, float]
    winner: Optional[StrategySpec] = None


def search_strategies(
    bars: pd.DataFrame,
    cfg: Config,
    n_specs: int = 2_000,
    top_k: int = 10,
    holdout_fraction: float = 0.35,
    min_trades: int = 30,
    seed: int = 0,
    jobs: int = 1,
    progress: bool = True,
) -> SearchResult:
    from .metrics import infer_bars_per_year

    split = int(len(bars) * (1.0 - holdout_fraction))
    embargo = max(cfg.walk_forward.embargo_bars, cfg.labels.max_holding_bars)
    search_bars = bars.iloc[:split]
    holdout_bars = bars.iloc[split + embargo :]
    bars_per_year = infer_bars_per_year(bars.index)

    specs = generate_specs(n_specs, seed=seed)
    if progress:
        print(
            f"space: {grid_size():,} combinations, sampling {len(specs):,}\n"
            f"search  {search_bars.index[0]:%Y-%m-%d} -> {search_bars.index[-1]:%Y-%m-%d} "
            f"({len(search_bars):,} bars)\n"
            f"holdout {holdout_bars.index[0]:%Y-%m-%d} -> {holdout_bars.index[-1]:%Y-%m-%d} "
            f"({len(holdout_bars):,} bars, untouched until the finalists are chosen)"
        )

    rows = _run_evaluation(specs, search_bars, cfg, bars_per_year, jobs, progress)
    table = pd.DataFrame(rows)

    eligible = table[table["trades"] >= min_trades].copy()
    if eligible.empty:
        return SearchResult(
            table=table.sort_values("trade_sharpe", ascending=False),
            finalists=pd.DataFrame(),
            n_tested=len(specs),
            search_span=(search_bars.index[0], search_bars.index[-1]),
            holdout_span=(holdout_bars.index[0], holdout_bars.index[-1]),
            deflation={"threshold": 0.0, "dsr": 0.0, "beats_luck": False},
        )

    eligible = eligible.sort_values("trade_sharpe", ascending=False)
    best = eligible.iloc[0]
    deflation = deflated_sharpe(
        observed_sharpe=float(best["trade_sharpe"]),
        n_trades=int(best["trades"]),
        n_trials=len(eligible),
        sharpe_std=robust_std(eligible["trade_sharpe"]),
        skew=float(best["r_skew"]),
        kurtosis=float(best["r_kurtosis"]),
    )

    # --- the holdout is opened here, and only here ----------------------
    finalists = eligible.head(top_k).copy()
    holdout_rows = _run_evaluation(
        list(finalists["spec"]), holdout_bars, cfg, bars_per_year, jobs, progress=False
    )
    holdout = pd.DataFrame(holdout_rows)
    for column in ("trades", "expectancy_r", "trade_sharpe", "profit_factor",
                   "win_rate_pct", "total_return_pct", "max_drawdown_pct"):
        finalists[f"holdout_{column}"] = holdout[column].to_numpy()

    winner = None
    survivors = finalists[
        (finalists["holdout_expectancy_r"] > 0) & (finalists["holdout_trades"] >= 10)
    ]
    if not survivors.empty and deflation["beats_luck"]:
        winner = survivors.iloc[0]["spec"]

    return SearchResult(
        table=eligible,
        finalists=finalists,
        n_tested=len(specs),
        search_span=(search_bars.index[0], search_bars.index[-1]),
        holdout_span=(holdout_bars.index[0], holdout_bars.index[-1]),
        deflation=deflation,
        winner=winner,
    )


def _run_evaluation(specs, bars, cfg, bars_per_year, jobs, progress):
    config_dict = cfg.to_dict()
    if jobs == 1 or len(specs) < 50:
        cache = IndicatorCache(bars, cfg.labels.atr_period)
        rows = []
        for i, spec in enumerate(specs, 1):
            row = evaluate_spec(spec, bars, cache, cfg, bars_per_year)
            row["spec"] = spec
            rows.append(row)
            if progress and i % 250 == 0:
                print(f"  evaluated {i:,}/{len(specs):,}")
        return rows

    from joblib import Parallel, delayed

    chunks = [specs[i::jobs * 4] for i in range(jobs * 4)]
    chunks = [c for c in chunks if c]
    results = Parallel(n_jobs=jobs, verbose=5 if progress else 0)(
        delayed(_evaluate_chunk)(chunk, bars, config_dict, bars_per_year)
        for chunk in chunks
    )
    return [row for chunk in results for row in chunk]


def format_search(result: SearchResult) -> str:
    d = result.deflation
    lines = [
        "-- strategy search " + "-" * 50,
        f"  candidates tested   {result.n_tested:,}",
        f"  search window       {result.search_span[0]:%Y-%m-%d} -> {result.search_span[1]:%Y-%m-%d}",
        f"  holdout window      {result.holdout_span[0]:%Y-%m-%d} -> {result.holdout_span[1]:%Y-%m-%d}",
        "",
        f"  best-of-N by luck   {d['threshold']:.4f} Sharpe per trade",
        f"  deflated Sharpe     {d['dsr']:.1%}  -> "
        f"{'beats luck' if d['beats_luck'] else 'INDISTINGUISHABLE FROM LUCK'}",
        "",
    ]
    if result.finalists.empty:
        lines.append("  no candidate reached the minimum trade count.")
        return "\n".join(lines)

    view = result.finalists[
        ["name", "trades", "expectancy_r", "trade_sharpe", "profit_factor",
         "holdout_trades", "holdout_expectancy_r", "holdout_trade_sharpe"]
    ].copy()
    view.columns = ["strategy", "trades", "exp_R", "sharpe", "pf",
                    "ho_trades", "ho_exp_R", "ho_sharpe"]
    view["strategy"] = view["strategy"].str.slice(0, 58)
    lines.append(view.to_string(index=False, float_format=lambda v: f"{v:.3f}"))

    kept = int(((result.finalists["holdout_expectancy_r"] > 0)).sum())
    lines += [
        "",
        f"  finalists still positive on the holdout: {kept}/{len(result.finalists)}",
    ]
    if result.winner is not None:
        lines.append(f"  WINNER: {result.winner.name}")
        lines.append("  Next step is walk-forward on this spec, then demo. Not live.")
    else:
        lines.append(
            "  No winner. Either the deflated Sharpe says luck, or the finalists\n"
            "  died on the holdout. This is the normal outcome and it saved you money."
        )
    return "\n".join(lines)
