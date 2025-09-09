"""Pydantic models for data structures used within the application's services.

This module defines the data transfer objects (DTOs) that are used to pass
structured data between different components of the rebalancing service layer,
such as the rebalancing engine and the executor.
"""
from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class ProposedTrade(BaseModel):
    """Represents a single trade calculated by the rebalancing engine.

    This model contains all the necessary information for executing a trade,
    including the symbol, side, and quantity, which has already been validated
    against the exchange's trading rules (e.g., step size).

    Attributes:
        symbol: The trading pair, e.g., 'BTCUSDT'.
        asset: The asset being traded, e.g., 'BTC'.
        side: The order side, either 'BUY' or 'SELL'.
        quantity: The final, adjusted quantity to be traded.
        estimated_value_usd: The estimated value of the trade in USD.
        reason: An explanation for why this trade is proposed.
    """

    symbol: str = Field(description="The trading pair, e.g., 'BTCUSDT'.")
    asset: str = Field(description="The asset being traded, e.g., 'BTC'.")
    side: Literal["BUY", "SELL"]
    quantity: float = Field(description="The final, adjusted quantity to be traded.")
    estimated_value_usd: float = Field(
        description="The estimated value of the trade in the base currency."
    )
    reason: str = Field(description="Explanation for why this trade is proposed.")
    fee_cost_usd: float = Field(
        0.0, description="The estimated cost of the trade fee in USD."
    )


class RebalanceResult(BaseModel):
    """Represents the outcome of a rebalancing execution.

    This model captures all relevant information about a completed rebalancing
    run, including its status, a summary message, and lists of executed
ator
simulated trades and any errors encountered.

    Attributes:
        run_id: A unique identifier for the rebalancing run.
        timestamp: The UTC timestamp when the run was initiated.
        status: The final status of the run.
        message: A human-readable summary of the run's outcome.
        trades: A list of trades that were simulated or executed.
        errors: A list of any errors that occurred during execution.
        total_fees_usd: The total estimated cost of all trade fees in USD.
        projected_balances: A dictionary of what the new balances would be
                           after the rebalance.
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
    total_fees_usd: float = Field(
        0.0, description="The total estimated cost of all trade fees in USD."
    )
    projected_balances: Optional[dict] = Field(
        None, description="The projected balances after the rebalance."
    )
