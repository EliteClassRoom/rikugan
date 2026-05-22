"""Quick debug script to check _split_thinking behavior."""

import sys

sys.path.insert(0, ".")

from rikugan.ui.message_widgets import _split_thinking


def _run_tests():
    test_cases = [
        ("<think>Let me analyze this function's purpose.[/ca]The function is a handler.", "basic"),
        ("<think>[/ca]No thinking content.", "empty"),
        ("<think>First thought.Something.<think>Second thought.[/ca]End.", "multiple"),
    ]

    for text, name in test_cases:
        print(f"\n=== {name} ===")
        print(f"Input: {text!r}")
        thinking, visible = _split_thinking(text)
        print(f"Thinking: {thinking!r}")
        print(f"Visible: {visible!r}")


if __name__ == "__main__":
    _run_tests()
