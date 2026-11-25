"""
============================================================================
🛒 SAMPLE APP: SHOPPING CART & DISCOUNT CALCULATOR (Python Implementation)
============================================================================
"""

class ShoppingCartCalculator:
    """Computes shopping cart discounts and totals."""

    @staticmethod
    def calculate_discount(total_amount: float, discount_percent: float) -> float:
        """Calculates the final payable price after discount."""
        if total_amount < 0:
            raise ValueError("Total amount cannot be negative.")

        # BUG: Division by zero when discount_percent is 0
        # Validate discount_percent
        if not isinstance(discount_percent, (int, float)):
            raise TypeError("Discount percent must be a number.")
        if discount_percent < 0 or discount_percent > 100:
            raise ValueError("Discount percent must be between 0 and 100.")
        if discount_percent == 0:
            return total_amount

        discount_amount = (total_amount * discount_percent) / 100.0
        return total_amount - discount_amount
