"""
Deterministic Math Engine for the Indian Stock AI Council.

ALL price targets, stop-losses, entry ranges, and risk-reward ratios
are computed HERE in pure Python. The LLM never calculates a number.

ARCHITECTURAL RULE:
  The Chairman LLM outputs a classification (BUY/HOLD/AVOID) and reasoning.
  This module computes the exact entry, SL, T1, T2 from technical data.
  Numbers are IMMUTABLE once computed — the LLM cannot override them.
"""

import math
from typing import Optional


def compute_stop_loss(
    current_price: float,
    atr_14: float,
    atr_multiplier: float = 2.0,
    hard_stop_pct: float = 7.0,
) -> float:
    """
    Compute stop-loss percentage — the TIGHTER of ATR-based and hard stop.

    ATR-based SL = (2 × ATR / current_price) × 100
    Hard SL = 7% (no exceptions)

    Returns the tighter (smaller) of the two as a percentage.
    """
    if current_price <= 0:
        return hard_stop_pct

    atr_stop_pct = (atr_14 * atr_multiplier / current_price) * 100

    # Use the tighter stop
    result = min(atr_stop_pct, hard_stop_pct)

    # Floor at 1% — anything less is unrealistic for Indian equities
    return round(max(result, 1.0), 2)


def compute_entry_range(
    current_price: float,
    dma_20: float,
    support_levels: Optional[list[float]] = None,
    buffer_pct: float = 1.5,
) -> tuple[float, float]:
    """
    Compute a realistic entry range near support.

    Logic:
    - Entry low = nearest support level (or 20DMA, or 1.5% below current)
    - Entry high = current price (you wouldn't buy above current)

    Returns (entry_low, entry_high) as floats.
    """
    if current_price <= 0:
        return (0.0, 0.0)

    # Candidate low prices
    candidates = []

    # 20DMA as natural support
    if dma_20 > 0 and dma_20 < current_price:
        candidates.append(dma_20)

    # Explicit support levels from technical analysis
    if support_levels:
        for s in support_levels:
            if 0 < s < current_price:
                candidates.append(s)

    # Buffer below current price as fallback
    buffer_price = current_price * (1 - buffer_pct / 100)
    candidates.append(buffer_price)

    # Pick the highest support that's still below current price
    # (closest realistic entry point)
    valid_supports = [c for c in candidates if 0 < c <= current_price]
    entry_low = max(valid_supports) if valid_supports else buffer_price

    # Entry high = current price (don't chase above)
    entry_high = current_price

    return (round(entry_low, 2), round(entry_high, 2))


def compute_targets(
    entry_low: float,
    entry_high: float,
    stop_loss_pct: float,
    t1_multiplier: float = 1.5,
    t2_multiplier: float = 2.5,
) -> tuple[float, float]:
    """
    Compute Target 1 and Target 2 deterministically.

    Target 1 = Entry midpoint + (risk_distance × 1.5)  → minimum 2:1 R:R
    Target 2 = Entry midpoint + (risk_distance × 2.5)  → stretch target

    Risk distance = entry_midpoint × (stop_loss_pct / 100)
    """
    if entry_low <= 0 or entry_high <= 0 or stop_loss_pct <= 0:
        return (0.0, 0.0)

    midpoint = (entry_low + entry_high) / 2
    risk_distance = midpoint * (stop_loss_pct / 100)

    target_1 = midpoint + (risk_distance * t1_multiplier)
    target_2 = midpoint + (risk_distance * t2_multiplier)

    return (round(target_1, 2), round(target_2, 2))


def compute_risk_reward(
    entry_price: float,
    target_price: float,
    stop_loss_pct: float,
) -> float:
    """
    Compute risk-to-reward ratio.

    R:R = (Target - Entry) / (Entry × SL%)
    A ratio >= 2.0 is the minimum for a BUY.
    """
    if entry_price <= 0 or stop_loss_pct <= 0:
        return 0.0

    risk = entry_price * (stop_loss_pct / 100)
    reward = target_price - entry_price

    if risk <= 0:
        return 0.0

    return round(reward / risk, 2)


def inject_math_into_result(
    chairman_result: dict,
    technical_data: dict,
) -> dict:
    """
    Master function: inject all Python-computed math into the Chairman's output.

    The Chairman only provides: action, confidence, reasoning.
    This function fills in: entry_range, stop_loss, targets.

    Args:
        chairman_result: Raw Chairman LLM output (action, confidence, reasoning)
        technical_data:  StockPriceData dict with current_price, atr_14, dma_20, etc.

    Returns:
        Complete result dict with all numbers computed deterministically.
    """
    current_price = technical_data.get("current_price", 0)
    atr_14 = technical_data.get("atr_14", 0)
    dma_20 = technical_data.get("dma_20", 0)
    support_levels = technical_data.get("support_levels", [])

    # 1. Stop-loss (tighter of ATR and 7%)
    stop_loss_pct = compute_stop_loss(current_price, atr_14)

    # 2. Entry range (near support)
    entry_low, entry_high = compute_entry_range(
        current_price, dma_20, support_levels
    )

    # 3. Targets (deterministic from risk distance)
    target_1, target_2 = compute_targets(entry_low, entry_high, stop_loss_pct)

    # 4. Risk-reward ratio
    midpoint = (entry_low + entry_high) / 2 if entry_low > 0 else current_price
    rr_ratio = compute_risk_reward(midpoint, target_1, stop_loss_pct)

    # Inject into result
    chairman_result["entry_range_low"] = entry_low
    chairman_result["entry_range_high"] = entry_high
    chairman_result["stop_loss_pct"] = stop_loss_pct
    chairman_result["target_1"] = target_1
    chairman_result["target_2"] = target_2
    chairman_result["risk_reward_ratio"] = rr_ratio

    # Safety: if R:R is below 1.5 on a BUY, downgrade to HOLD
    if chairman_result.get("action") == "BUY" and rr_ratio < 1.5:
        chairman_result["action"] = "HOLD"
        chairman_result["reasoning"] = (
            chairman_result.get("reasoning", "")
            + f" [Auto-downgraded: R:R ratio {rr_ratio} < 1.5 minimum]"
        )

    return chairman_result
