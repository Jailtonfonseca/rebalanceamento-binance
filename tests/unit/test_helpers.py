import pytest
from decimal import Decimal
from app.utils.helpers import adjust_to_step_size, format_quantity_for_api


@pytest.mark.parametrize(
    "quantity, step_size, expected",
    [
        (0.12345, "0.001", 0.123),
        (153.45, "10", 150.0),
        (0.12345678, "0.000001", 0.123456),
        (10.99, "0.1", 10.9),
        (10.99, "1", 10.0),
        (0.0000009, "0.0000001", 0.0000009),
        (1, "0.001", 1.0),
        (0, "0.001", 0.0),
    ],
)
def test_adjust_to_step_size_valid(quantity, step_size, expected):
    """
    Tests that the adjust_to_step_size function works for valid inputs.
    """
    assert adjust_to_step_size(quantity, step_size) == expected


def test_adjust_to_step_size_decimal_precision():
    """
    Tests that the function handles decimal precision correctly without floating point errors.
    """
    # Using Decimals to avoid float inaccuracies in the test itself
    quantity = Decimal("0.10000000000000001")  # A common float inaccuracy
    step_size = "0.001"
    expected = 0.1
    assert adjust_to_step_size(float(quantity), step_size) == expected


def test_adjust_to_step_size_invalid_input():
    """
    Tests that the function raises ValueError for invalid inputs.
    """
    with pytest.raises(ValueError):
        adjust_to_step_size(0.123, "0")  # Zero step size
    with pytest.raises(ValueError):
        adjust_to_step_size(0.123, "-1")  # Negative step size
    with pytest.raises(ValueError):
        adjust_to_step_size("not a number", "0.1")  # Invalid quantity
    with pytest.raises(ValueError):
        adjust_to_step_size(0.123, "not a number")  # Invalid step size
    with pytest.raises(ValueError):
        adjust_to_step_size(None, "0.1")  # None quantity
    with pytest.raises(ValueError):
        adjust_to_step_size(0.1, None)  # None step size


@pytest.mark.parametrize(
    "quantity, expected_str",
    [
        (0.123, "0.123"),
        (150.0, "150"),
        (0.0000001, "0.0000001"),
        (1.00000000, "1"),
        (1.23450000, "1.2345"),
    ],
)
def test_format_quantity_for_api(quantity, expected_str):
    """
    Tests that the format_quantity_for_api function correctly formats numbers
    into plain decimal strings.
    """
    assert format_quantity_for_api(quantity) == expected_str
