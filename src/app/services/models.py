from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProposedTrade(BaseModel):
    """
    Represents a single trade calculated by the rebalancing engine,
    validated against exchange rules.
    """

    symbol: str = Field(description="The trading pair, e.g., 'BTCUSDT'.")
    asset: str = Field(description="The asset being traded, e.g., 'BTC'.")
    side: Literal["BUY", "SELL"]
    quantity: float = Field(description="The final, adjusted quantity to be traded.")
    estimated_value_usd: float = Field(
        description="The estimated value of the trade in the base currency."
    )
    reason: str = Field(description="Explanation for why this trade is proposed.")


class RebalanceResult(BaseModel):
    """
    Represents the outcome of a rebalancing execution.
    """

    run_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    status: Literal["DRY_RUN", "SUCCESS", "PARTIAL_SUCCESS", "FAILED"]
    message: str = Field(description="A summary of the rebalancing run.")
    trades: List[ProposedTrade] = Field(
        description="A list of trades that were simulated or executed."
    )
    errors: Optional[List[str]] = Field(
        None, description="Any errors that occurred during execution."
    )
