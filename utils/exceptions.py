"""
Custom exceptions for the Indian Stock AI Council Engine.

DESIGN RULE: The system must FAIL LOUDLY.
If data cannot be fetched or an agent fails, the stock is DROPPED.
No silent degradation to neutral — that's worse than no output.
"""


class DataCollectionError(Exception):
    """
    Raised when data cannot be fetched for a stock.

    Triggers: Screener.in 404, yfinance empty DataFrame, NSE API timeout.
    Effect:   The stock is removed from the day's run entirely.
    """

    def __init__(self, ticker: str, source: str, reason: str):
        self.ticker = ticker
        self.source = source
        self.reason = reason
        super().__init__(
            f"[{source}] Failed to collect data for {ticker}: {reason}"
        )


class AgentFailureError(Exception):
    """
    Raised when ALL LLM providers fail for an agent.

    Triggers: Primary + fallback both exhausted retries.
    Effect:   The stock is dropped from the day's run.
    """

    def __init__(self, agent_name: str, ticker: str = "", reason: str = ""):
        self.agent_name = agent_name
        self.ticker = ticker
        self.reason = reason
        super().__init__(
            f"[{agent_name}] All providers failed for {ticker}: {reason}"
        )


class RateLimitExhaustedError(Exception):
    """
    Raised when a provider hits its daily token bucket limit.
    
    Triggers: Provider limits in AsyncTokenBucketLimiter are exceeded.
    Effect:   Agent immediately breaks retry loop and tries fallback provider.
    """

    def __init__(self, provider: str, limit: int):
        self.provider = provider
        self.limit = limit
        super().__init__(
            f"[{provider}] Daily rate limit exhausted ({limit} calls/day)"
        )
