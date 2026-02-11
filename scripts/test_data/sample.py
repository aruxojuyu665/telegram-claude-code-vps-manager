"""Sample Python file for JARVIS file handling test.

This file tests the extraction of Python source code.
"""

from typing import Any


def greet(name: str = "World") -> str:
    """Return a greeting message.

    Args:
        name: The name to greet.

    Returns:
        A greeting string.
    """
    return f"Hello, {name}!"


class Calculator:
    """Simple calculator for testing."""

    def add(self, a: int, b: int) -> int:
        """Add two numbers."""
        return a + b

    def multiply(self, a: int, b: int) -> int:
        """Multiply two numbers."""
        return a * b


def main() -> None:
    """Main entry point."""
    print(greet("JARVIS"))
    calc = Calculator()
    print(f"2 + 3 = {calc.add(2, 3)}")
    print(f"4 * 5 = {calc.multiply(4, 5)}")


if __name__ == "__main__":
    main()
