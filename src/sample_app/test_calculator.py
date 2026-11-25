import unittest
from src.sample_app.calculator import ShoppingCartCalculator


class TestShoppingCartCalculator(unittest.TestCase):
    def test_standard_discount(self):
        result = ShoppingCartCalculator.calculate_discount(100.0, 10.0)
        self.assertEqual(result, 90.0)

    def test_zero_discount(self):
        result = ShoppingCartCalculator.calculate_discount(150.0, 0.0)
        self.assertEqual(result, 150.0)

    def test_full_discount(self):
        result = ShoppingCartCalculator.calculate_discount(200.0, 100.0)
        self.assertEqual(result, 0.0)

    def test_negative_amount_raises(self):
        with self.assertRaises(ValueError):
            ShoppingCartCalculator.calculate_discount(-50.0, 10.0)


if __name__ == '__main__':
    unittest.main()
