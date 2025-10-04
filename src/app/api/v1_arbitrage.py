from fastapi import APIRouter, Depends, HTTPException
import logging
from typing import List, Dict

from app.services.arbitrage_service import ArbitrageService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/arbitrage/opportunities", response_model=List[Dict])
async def get_arbitrage_opportunities():
    """
    Scans for and returns a list of potential triangular arbitrage opportunities.
    """
    try:
        service = ArbitrageService()
        opportunities = await service.find_opportunities()
        return opportunities
    except Exception as e:
        logger.error(f"Error fetching arbitrage opportunities: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred while scanning for arbitrage opportunities."
        )