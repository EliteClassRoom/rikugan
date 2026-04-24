"""Quick debug script to check _split_thinking behavior."""
import sys
sys.path.insert(0, '.')

from ui.message_widgets import _split_thinking

test_cases = [
    ("<think>Let me analyze this function's purpose.[/ca]The function is a handler.", "basic"),
    ("<think>[/ca]No thinking content.", "empty"),
    ("<think>First thought.Something.<think>Second thought.[/ca]End.", "multiple"),
]

for text, name in test_cases:
    print(f"\n=== {name} ===")
    print(f"Input: {repr(text)}")
    thinking, visible = _split_thinking(text)
    print(f"Thinking: {repr(thinking)}")
    print(f"Visible: {repr(visible)}")