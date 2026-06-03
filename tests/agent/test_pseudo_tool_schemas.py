"""Tests for rikugan.agent.pseudo_tool_schemas."""

from __future__ import annotations

from rikugan.agent.pseudo_tool_schemas import (
    ALL_PSEUDO_TOOL_SCHEMAS,
    ASK_USER_SCHEMA,
    EXPLORATION_REPORT_SCHEMA,
    PHASE_TRANSITION_SCHEMA,
    RESEARCH_NOTE_SCHEMA,
    SAVE_MEMORY_SCHEMA,
    SPAWN_SUBAGENT_SCHEMA,
    __all__,
)


def test_all_exports_are_listed() -> None:
    """`__all__` must include every public schema (and the aggregate)."""
    assert set(__all__) == {
        "ALL_PSEUDO_TOOL_SCHEMAS",
        "ASK_USER_SCHEMA",
        "EXPLORATION_REPORT_SCHEMA",
        "PHASE_TRANSITION_SCHEMA",
        "RESEARCH_NOTE_SCHEMA",
        "SAVE_MEMORY_SCHEMA",
        "SPAWN_SUBAGENT_SCHEMA",
    }


def test_aggregate_contains_every_individual_schema() -> None:
    """ALL_PSEUDO_TOOL_SCHEMAS must reference every individual schema exactly once."""
    expected = [
        EXPLORATION_REPORT_SCHEMA,
        PHASE_TRANSITION_SCHEMA,
        SAVE_MEMORY_SCHEMA,
        SPAWN_SUBAGENT_SCHEMA,
        RESEARCH_NOTE_SCHEMA,
        ASK_USER_SCHEMA,
    ]
    assert list(ALL_PSEUDO_TOOL_SCHEMAS) == expected
    assert len(ALL_PSEUDO_TOOL_SCHEMAS) == 6


def test_every_schema_is_openai_function_format() -> None:
    """Every schema must follow the {type: function, function: {name, ...}} shape."""
    for schema in ALL_PSEUDO_TOOL_SCHEMAS:
        assert schema["type"] == "function", schema["function"]["name"]
        fn = schema["function"]
        assert isinstance(fn["name"], str) and fn["name"]
        assert isinstance(fn["description"], str) and fn["description"]
        params = fn["parameters"]
        assert params["type"] == "object"
        assert isinstance(params["properties"], dict) and params["properties"]
        # `required` is optional but if present must be a list
        assert "required" not in params or isinstance(params["required"], list)


def _required_fields(schema: dict) -> list[str]:
    return list(schema["function"]["parameters"].get("required", []))


def test_exploration_report_requires_category_and_summary() -> None:
    assert _required_fields(EXPLORATION_REPORT_SCHEMA) == ["category", "summary"]


def test_phase_transition_requires_to_phase_and_reason() -> None:
    assert _required_fields(PHASE_TRANSITION_SCHEMA) == ["to_phase", "reason"]


def test_save_memory_requires_fact_only() -> None:
    assert _required_fields(SAVE_MEMORY_SCHEMA) == ["fact"]


def test_spawn_subagent_requires_task_only() -> None:
    assert _required_fields(SPAWN_SUBAGENT_SCHEMA) == ["task"]


def test_research_note_requires_title_and_content() -> None:
    assert _required_fields(RESEARCH_NOTE_SCHEMA) == ["title", "content"]


def test_ask_user_requires_question_only() -> None:
    assert _required_fields(ASK_USER_SCHEMA) == ["question"]


def test_tool_names_are_unique_across_aggregate() -> None:
    """Anthropic rejects requests with duplicate tool names."""
    names = [s["function"]["name"] for s in ALL_PSEUDO_TOOL_SCHEMAS]
    assert len(names) == len(set(names)), f"Duplicate tool names: {names}"


def test_save_memory_category_default_is_general() -> None:
    category_prop = SAVE_MEMORY_SCHEMA["function"]["parameters"]["properties"]["category"]
    assert category_prop["default"] == "general"


def test_spawn_subagent_agent_type_default_is_general() -> None:
    agent_type_prop = SPAWN_SUBAGENT_SCHEMA["function"]["parameters"]["properties"]["agent_type"]
    assert agent_type_prop["default"] == "general"
