"""Tests for typed GLM dialect configuration and model metadata.

Task 4 of the GLM reasoning resilience plan.  The parser is the single source
of truth for GLM configuration validation: it rejects unknown nested keys,
validates boolean/enum/range values, and reports exact field paths so users
see *which* GLM setting is wrong.

Model metadata is data-only and lives next to the parser so call sites can
ask ``get_glm_model_metadata("glm-5.2")`` instead of hard-coding capability
flags.
"""

from __future__ import annotations

import pytest

from rikugan.core.glm_config import get_glm_model_metadata, parse_glm_extra


def test_default_glm_config_is_guarded_and_preserved():
    parsed = parse_glm_extra({"dialect": "glm"}, "glm-5.2")

    assert parsed.thinking.enabled is True
    assert parsed.thinking.reasoning_effort == "max"
    assert parsed.thinking.preserve is True
    assert parsed.guard.enabled is True
    assert parsed.guard.reasoning_token_ceiling == 16_384
    assert parsed.guard.recovery_max_tokens == 16_384


def test_glm_config_rejects_unknown_nested_key_with_field_path():
    with pytest.raises(ValueError, match=r"provider.extra.thinking.unknown"):
        parse_glm_extra(
            {"dialect": "glm", "thinking": {"unknown": True}},
            "glm-5.2",
        )


def test_glm_config_validates_ranges():
    with pytest.raises(ValueError, match=r"reasoning_token_ceiling"):
        parse_glm_extra(
            {
                "dialect": "glm",
                "degeneration_guard": {"reasoning_token_ceiling": 1023},
            },
            "glm-5.2",
        )


def test_unknown_glm_model_disables_tool_stream_and_effort():
    metadata = get_glm_model_metadata("glm-experimental")

    assert metadata.reasoning_content is True
    assert metadata.streaming_tool_calls is False
    assert metadata.reasoning_effort is False


def test_glm_5_2_context_window_is_one_million():
    """Z.AI lists GLM-5.2 with a 1,000,000-token context window and a
    131,072-token output limit."""
    metadata = get_glm_model_metadata("glm-5.2")

    assert metadata.context_window == 1_000_000
    assert metadata.max_output_tokens == 131_072


@pytest.mark.parametrize(
    "model_id",
    ["glm-5.1", "glm-5", "glm-4.7"],
)
def test_pre_glm_5_2_context_window_is_200k(model_id: str):
    """Z.AI lists GLM-5.1, GLM-5, and GLM-4.7 with a 200,000-token
    context window and a 131,072-token output limit.  These three
    must NOT inherit the 1M context window from GLM-5.2."""
    metadata = get_glm_model_metadata(model_id)

    assert metadata.context_window == 200_000
    assert metadata.max_output_tokens == 131_072


def test_unknown_glm_model_context_window_falls_back_to_200k():
    """Unknown GLM model IDs inherit the conservative 200K context
    window rather than the 1M ceiling, so request payloads are
    clamped against a realistic upper bound."""
    metadata = get_glm_model_metadata("glm-experimental")

    assert metadata.context_window == 200_000
    assert metadata.max_output_tokens == 131_072
