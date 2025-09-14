from decimal import Decimal


def adjust_to_step_size(quantity: float, step_size: str) -> float:
    """Adjusts a quantity to the specified step size using Decimal precision.

    Rounds down to the nearest multiple of the step size.

    For example:
    - adjust_to_step_size(0.12345, "0.001") -> 0.123
    - adjust_to_step_size(153.45, "10") -> 150.0
    - adjust_to_step_size(0.12345678, "0.000001") -> 0.123456

    Args:
        quantity: The quantity to adjust.
        step_size: The step size to which the quantity is adjusted.

    Returns:
        The adjusted quantity as a float.
    """
    if not isinstance(quantity, (float, int)) or not isinstance(step_size, str):
        raise ValueError("Invalid input types for adjust_to_step_size")

    try:
        quantity_dec = Decimal(str(quantity))
        step_size_dec = Decimal(step_size)
    except Exception as e:
        raise ValueError("Invalid number format for quantity or step_size") from e

    if step_size_dec <= 0:
        raise ValueError("Step size must be positive.")

    # Truncate the quantity to the specified step size
    adjusted_quantity = (quantity_dec // step_size_dec) * step_size_dec

    return float(adjusted_quantity)


def format_quantity_for_api(quantity: float) -> str:
    """Formats a quantity into a plain decimal string for API requests.

    This prevents scientific notation which is rejected by some exchanges.

    Args:
        quantity: The numeric quantity to format.

    Returns:
        A plain decimal string.
    """
    # Use Decimal to handle floating point intricacies and format correctly
    d = Decimal(str(quantity))
    # 'f' format specifier prevents scientific notation.
    # The string is normalized to remove trailing zeros.
    return (
        format(d, "f").rstrip("0").rstrip(".")
        if "." in format(d, "f")
        else format(d, "f")
    )
