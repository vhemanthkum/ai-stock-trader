"""
Sentiment overlay and position sizing.

Implements the MMI → position multiplier logic from the blueprint:
- VIX > 22 → 0.5× (halve positions — high fear environment)
- MMI < 30 → 1.5× (Extreme Fear — contrarian long, bigger size)
- MMI < 50 → 1.25× (Fear — increase size)
- MMI < 70 → 1.0× (Neutral — standard size)
- MMI < 85 → 0.75× (Greed — reduce size)
- MMI ≥ 85 → 0.5× (Extreme Greed — minimal size, longs only)

This is the direct translation of Hyperliquid findings to Indian equities.
"""

from config import (
    MMI_EXTREME_FEAR,
    MMI_FEAR,
    MMI_NEUTRAL,
    MMI_GREED,
    VIX_REDUCE_THRESHOLD,
    RISK_PER_TRADE,
    DEFAULT_STOP_LOSS_PCT,
)


def get_position_multiplier(mmi_score: float, india_vix: float) -> float:
    """
    Calculate position size multiplier based on market sentiment.
    
    From the blueprint's sentiment gating rule:
    - During fear: increase long sizing (contrarian)
    - During greed: reduce positions
    - High VIX overrides everything → reduce
    
    Args:
        mmi_score: Market Mood Index (0–100)
        india_vix: Current India VIX value
    
    Returns:
        Position multiplier (0.5 to 1.5)
    """
    # VIX override — high volatility reduces all positions
    if india_vix > VIX_REDUCE_THRESHOLD:
        return 0.5  # Halve all positions — high fear environment

    # MMI-based sizing
    if mmi_score < MMI_EXTREME_FEAR:
        return 1.5   # Extreme Fear — contrarian long, 1.5× size
    elif mmi_score < MMI_FEAR:
        return 1.25  # Fear — increase size
    elif mmi_score < MMI_NEUTRAL:
        return 1.0   # Neutral — standard size
    elif mmi_score < MMI_GREED:
        return 0.75  # Greed — reduce size
    else:
        return 0.5   # Extreme Greed — minimal size, longs only


def calculate_position_size(
    portfolio_value: float,
    stop_loss_pct: float,
    risk_per_trade: float = RISK_PER_TRADE,
    multiplier: float = 1.0,
) -> dict:
    """
    Calculate position size based on risk management rules.
    
    From the blueprint:
    Position size = (risk_per_trade × portfolio) ÷ stop_loss_pct
    
    Example: 7% SL on a ₹10L portfolio with 0.5% risk per trade
    = (0.005 × 1,000,000) ÷ 0.07
    = ₹5,000 ÷ 0.07
    = ₹71,428 position size
    
    Args:
        portfolio_value: Total portfolio value in ₹
        stop_loss_pct: Stop-loss percentage (e.g., 7.0 for 7%)
        risk_per_trade: Fraction of portfolio risked per trade (default 0.5%)
        multiplier: Sentiment-based position multiplier
    
    Returns:
        Dict with position_size, risk_amount, shares_if_price
    """
    if stop_loss_pct <= 0:
        stop_loss_pct = DEFAULT_STOP_LOSS_PCT

    risk_amount = portfolio_value * risk_per_trade
    base_position = risk_amount / (stop_loss_pct / 100)
    adjusted_position = base_position * multiplier

    return {
        "position_size": round(adjusted_position, 2),
        "risk_amount": round(risk_amount, 2),
        "stop_loss_pct": stop_loss_pct,
        "multiplier": multiplier,
        "max_loss": round(risk_amount, 2),
    }


def get_sentiment_label(mmi_score: float) -> str:
    """Get human-readable sentiment label from MMI score."""
    if mmi_score < MMI_EXTREME_FEAR:
        return "Extreme Fear 😰"
    elif mmi_score < MMI_FEAR:
        return "Fear 😟"
    elif mmi_score < MMI_NEUTRAL:
        return "Neutral 😐"
    elif mmi_score < MMI_GREED:
        return "Greed 😏"
    else:
        return "Extreme Greed 🤑"


def should_trade(india_vix: float, mmi_score: float, macro_regime: str) -> tuple[bool, str]:
    """
    Macro regime gate — should we trade at all today?
    
    From the blueprint:
    'Before I look at a single stock, I check 5 macro signals.
     If 3+ are red, I stay in cash.'
    
    Returns (should_trade, reason)
    """
    red_signals = 0
    reasons = []

    if india_vix > 22:
        red_signals += 1
        reasons.append(f"India VIX is {india_vix} (> 22)")

    if mmi_score < 25:
        red_signals += 1
        reasons.append(f"MMI at {mmi_score} (Extreme Fear)")

    if macro_regime == "Bear":
        red_signals += 1
        reasons.append("Market regime is Bear")

    if mmi_score > 90:
        red_signals += 1
        reasons.append(f"MMI at {mmi_score} (Extreme Greed — caution)")

    if red_signals >= 3:
        return False, f"STAY CASH — {red_signals} red signals: {'; '.join(reasons)}"

    if red_signals >= 2:
        return True, f"CAUTION — {red_signals} red signals: {'; '.join(reasons)}. Reduce position sizes."

    return True, "Market conditions OK for trading."


# ── CLI entry point for testing ─────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("  Sentiment & Position Sizing — Testing")
    print("=" * 60)

    # Test position multiplier
    test_cases = [
        (25, 14),   # Extreme Fear, low VIX
        (40, 16),   # Fear, normal VIX
        (55, 15),   # Neutral
        (75, 18),   # Greed
        (90, 20),   # Extreme Greed
        (50, 25),   # VIX override
    ]

    for mmi, vix in test_cases:
        mult = get_position_multiplier(mmi, vix)
        label = get_sentiment_label(mmi)
        print(f"  MMI={mmi:>3} VIX={vix:>4} → {mult}× ({label})")

    # Test position sizing
    print("\n  Position sizing for ₹10,00,000 portfolio:")
    for sl in [5.0, 6.2, 7.0]:
        result = calculate_position_size(1_000_000, sl, multiplier=1.25)
        print(f"  SL={sl}%, Mult=1.25× → Position: ₹{result['position_size']:,.0f}, Max loss: ₹{result['max_loss']:,.0f}")
