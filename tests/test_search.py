"""Strategy search: the space, the rules, and the defences against luck."""

import numpy as np
import pandas as pd
import pytest

from forexai.config import Config
from forexai.data.synthetic import generate_ohlcv
from forexai.search import (
    DEFAULT_GRID,
    ENTRY_FILTERS,
    EXIT_STYLES,
    FAMILIES,
    IndicatorCache,
    StrategySpec,
    _trade_sharpe,
    deflated_sharpe,
    expected_max_sharpe_under_null,
    generate_specs,
    grid_size,
    robust_std,
    rule_signal,
    search_strategies,
)


def test_the_space_is_large():
    """Hundreds of millions of rule sets, generated rather than collected."""
    assert grid_size(DEFAULT_GRID) > 100_000_000
    assert len(FAMILIES) >= 11


def test_generated_specs_are_valid():
    specs = generate_specs(300, seed=3)
    assert len(specs) == 300
    for spec in specs:
        assert spec.fast < spec.slow, "a fast average must be faster than the slow one"
        assert spec.reward_risk >= 1.5, "the risk mandate must hold for every candidate"
        assert spec.family in set(FAMILIES)
        assert spec.entry_filter in set(ENTRY_FILTERS)
        assert spec.exit_style in set(EXIT_STYLES)


def test_generation_is_reproducible():
    assert generate_specs(50, seed=7) == generate_specs(50, seed=7)
    assert generate_specs(50, seed=7) != generate_specs(50, seed=8)


@pytest.mark.parametrize("family", FAMILIES)
@pytest.mark.parametrize("entry_filter", ENTRY_FILTERS)
def test_rules_are_causal(family, entry_filter):
    """Truncating the future must not change a past signal."""
    bars = generate_ohlcv(900, seed=17)
    spec = StrategySpec(family=family, entry_filter=entry_filter)

    full = rule_signal(spec, IndicatorCache(bars))
    truncated = rule_signal(spec, IndicatorCache(bars.iloc[:700]))
    pd.testing.assert_series_equal(full.loc[truncated.index], truncated)


@pytest.mark.parametrize("family", FAMILIES)
def test_rules_produce_both_directions(family):
    bars = generate_ohlcv(12_000, seed=23)
    signal = rule_signal(StrategySpec(family=family, adx_min=15.0), IndicatorCache(bars))
    assert (signal == 1).any(), f"{family} never goes long"
    assert (signal == -1).any(), f"{family} never goes short"
    assert (signal == 0).mean() > 0.2, "a rule that is always in the market is a bug"


@pytest.mark.parametrize("exit_style", list(EXIT_STYLES))
def test_every_exit_style_reaches_the_risk_config(exit_style):
    from forexai.search import spec_config

    cfg = spec_config(StrategySpec(exit_style=exit_style), Config())
    expected = EXIT_STYLES[exit_style]
    assert cfg.risk.breakeven_at_r == expected["breakeven_at_r"]
    assert cfg.risk.trail_atr_mult == expected["trail_atr_mult"]


def test_entry_filters_only_ever_remove_signals():
    """A filter must narrow a family's entries, never invent new ones."""
    bars = generate_ohlcv(6_000, seed=41)
    cache = IndicatorCache(bars)
    base = rule_signal(StrategySpec(family="trend", entry_filter="none"), cache)
    for entry_filter in ("htf", "vol", "both"):
        filtered = rule_signal(
            StrategySpec(family="trend", entry_filter=entry_filter), cache
        )
        added = ((filtered != 0) & (base == 0)).sum()
        assert added == 0, f"{entry_filter} created signals the family did not have"
        assert (filtered != base).any(), f"{entry_filter} changed nothing"


def test_degenerate_trade_sharpe_is_neutralised():
    """Every trade identical means no dispersion, not an infinite Sharpe."""
    identical = pd.Series([-0.9] * 40)
    assert _trade_sharpe(identical) == 0.0

    normal = pd.Series([2.0, -1.0, -1.0, 2.0, -1.0] * 8)
    assert 0.0 < abs(_trade_sharpe(normal)) < 3.0


def test_robust_std_ignores_a_broken_trial():
    clean = pd.Series(np.linspace(-0.3, 0.3, 99))
    poisoned = pd.concat([clean, pd.Series([-33.0])], ignore_index=True)
    assert robust_std(poisoned) == pytest.approx(robust_std(clean), rel=0.1)
    assert poisoned.std(ddof=1) > 3 * robust_std(poisoned)


def test_luck_threshold_grows_with_the_number_of_trials():
    """The more strategies you try, the better the best fluke looks."""
    few = expected_max_sharpe_under_null(10, 0.2)
    many = expected_max_sharpe_under_null(10_000, 0.2)
    assert 0 < few < many


def test_a_mediocre_winner_of_many_trials_is_called_luck():
    result = deflated_sharpe(
        observed_sharpe=0.15, n_trades=60, n_trials=5_000, sharpe_std=0.2
    )
    assert not result["beats_luck"]


def test_a_strong_winner_of_few_trials_beats_luck():
    result = deflated_sharpe(
        observed_sharpe=0.55, n_trades=400, n_trials=20, sharpe_std=0.1
    )
    assert result["beats_luck"]


def test_deflation_handles_too_few_trades():
    result = deflated_sharpe(observed_sharpe=2.0, n_trades=2, n_trials=100, sharpe_std=0.2)
    assert result["dsr"] == 0.0 and not result["beats_luck"]


def test_search_keeps_the_holdout_untouched():
    bars = generate_ohlcv(12_000, seed=29)
    cfg = Config()
    result = search_strategies(
        bars, cfg, n_specs=40, top_k=3, holdout_fraction=0.35,
        min_trades=10, jobs=1, progress=False,
    )
    assert result.search_span[1] < result.holdout_span[0], "the windows overlap"
    gap = result.holdout_span[0] - result.search_span[1]
    assert gap >= pd.Timedelta(hours=cfg.labels.max_holding_bars), "embargo too short"
    assert result.n_tested == 40

    if not result.finalists.empty:
        # Holdout columns exist and are genuinely a second, separate evaluation.
        assert "holdout_expectancy_r" in result.finalists
        assert not result.finalists["holdout_trades"].equals(result.finalists["trades"])
