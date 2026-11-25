"""
============================================================================
🚀 OMNIDEV AUTONOMOUS BUG FIX RUNNER (Python Entrypoint)
============================================================================

🧠 WHAT DOES THIS SCRIPT DEMONSTRATE?
1. Resets `calculator.py` to its original BUGGY state.
2. Runs the unpatched Python code to prove the ZeroDivisionError crash.
3. Initializes our Python AgentExecutor.
4. Dispatches the autonomous bug-fixing task to the AI agent.
5. Watches the agent search files, inspect code lines, and patch the file live!
6. Re-runs the test suite to verify the code is 100% repaired!
"""

import sys
import importlib
from pathlib import Path
from src.agent.llm_provider import LLMProvider
from src.agent.agent_executor import AgentExecutor


def reset_calculator_to_buggy_state():
    """Restores the sample calculator file to its buggy state for demonstration."""
    buggy_code = '''"""
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
        if discount_percent == 0:
            return total_amount / 0

        discount_amount = (total_amount * discount_percent) / 100.0
        return total_amount - discount_amount
'''
    Path("src/sample_app/calculator.py").write_text(buggy_code, encoding='utf-8')


def main():
    print("=" * 65)
    print("🤖 OmniDev: Autonomous Bug-Fixing Demonstration (Python)")
    print("=" * 65 + "\n")

    # STEP 0: Reset file to known buggy state
    reset_calculator_to_buggy_state()

    # STEP 1: Demonstrate the bug in the raw Python code
    print("1️⃣ Step 1: Running unpatched calculator with 0% discount...")
    import src.sample_app.calculator as calc_module
    importlib.reload(calc_module)

    try:
        calc_module.ShoppingCartCalculator.calculate_discount(150.0, 0.0)
        print("   Unexpected: Code did not fail.")
    except ZeroDivisionError as e:
        print(f"   ❌ BUG CONFIRMED: Raised {type(e).__name__}: {e}\n")

    # STEP 2: Initialize our Agent
    print("2️⃣ Step 2: Initializing OmniDev Autonomous Engineering Agent...")
    llm = LLMProvider()
    agent = AgentExecutor(llm, max_iterations=6)

    # STEP 3: Dispatch Task
    print("3️⃣ Step 3: Dispatching Bug Fix Task to the Agent...")
    task = (
        "A bug was reported in calculate_discount: When discount_percent is 0, "
        "the function crashes with ZeroDivisionError. Find the bug, inspect the code, "
        "and apply an exact patch so that 0% discount returns total_amount untouched."
    )

    agent.run(task)

    # STEP 4: Verification
    print("\n" + "=" * 65)
    print("4️⃣ Step 4: Verifying the fix in the actual Python application...")
    print("=" * 65)

    # Reload the module to pick up the newly written patch on disk
    importlib.reload(calc_module)

    fixed_result = calc_module.ShoppingCartCalculator.calculate_discount(150.0, 0.0)
    print(f"   Cart Total: $150.0 | Discount: 0% | Result: ${fixed_result}")

    if fixed_result == 150.0:
        print("\n🎉 VERIFICATION PASSED: The Python Autonomous Agent repaired the bug with zero human intervention!")
    else:
        print(f"\n⚠️ Unexpected calculation result: {fixed_result}")


if __name__ == '__main__':
    main()
