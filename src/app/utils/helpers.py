import math
from decimal import Decimal, ROUND_DOWN


def adjust_to_step_size(quantity: float, step_size: str) -> float:
    """Adjusts a quantity to the specified step size.

    Rounds down to the nearest multiple of the step size.

    For example:
    - adjust_to_step_size(0.12345, "0.001") -> 0.123
    - adjust_to_step_size(153.45, "10") -> 150.0
    - adjust_to_step_size(0.12345678, "0.000001") -> 0.123456

    Args:
        quantity: The quantity to adjust.
        step_size: The step size to which the quantity is adjusted.

    Returns:
        The adjusted quantity.
    """
    if not isinstance(quantity, (float, int)) or not isinstance(step_size, str):
        raise ValueError("Invalid input types for adjust_to_step_size")

    try:
        step_size_float = float(step_size)
        if step_size_float <= 0:
            raise ValueError("Step size must be positive.")
    except ValueError as e:
        raise ValueError(f"Invalid step_size format: {step_size}") from e

    # Use Decimal for precision with fractional step sizes
    if step_size_float < 1.0:
        quantity_dec = Decimal(str(quantity))
        step_size_dec = Decimal(step_size)
        adjusted_quantity = quantity_dec.quantize(step_size_dec, rounding=ROUND_DOWN)
        return float(adjusted_quantity)
    else:
        # Use floating point math for whole number step sizes
        step_size_val = int(step_size_float)
        adjusted_quantity = math.floor(quantity / step_size_val) * step_size_val
        return float(adjusted_quantity)
