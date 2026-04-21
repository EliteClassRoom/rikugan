"""Subprocess bridge for CLI-based external agents (Claude Code, Codex, etc.)."""

from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Generator
from dataclasses import dataclass

from .types import A2AEvent, ExternalAgentConfig

_SUBPROCESS_AGENTS = {
    "claude": ["claude"],
    "codex": ["codex"],
}


@dataclass
class SubprocessBridge:
    """Bridge to CLI-based agents via subprocess.

    Detects available CLI agents on PATH and runs tasks via structured
    subprocess invocations with JSON output parsing.
    """

    def discover(self) -> list[ExternalAgentConfig]:
        """Auto-detect CLI agents available on PATH."""
        agents: list[ExternalAgentConfig] = []

        for agent_name, commands in _SUBPROCESS_AGENTS.items():
            cmd = commands[0]
            if shutil.which(cmd):
                agents.append(
                    ExternalAgentConfig(
                        name=agent_name,
                        transport="subprocess",
                        endpoint=cmd,
                        capabilities=self._capabilities_for(agent_name),
                    )
                )

        return agents

    def run_task(
        self,
        agent: ExternalAgentConfig,
        task: str,
        timeout: int = 300,
    ) -> Generator[A2AEvent, None, str]:
        """Run a task via CLI subprocess, yielding events.

        Yields events as the subprocess produces output, then yields a
        final event with the aggregated result string.

        For Claude CLI: uses `claude --print --output-format json`
        For Codex CLI: uses `codex --quiet --format json`
        """
        cmd = self._build_command(agent, task)
        if cmd is None:
            yield A2AEvent(event_type="error", text=f"No known command for agent: {agent.name}")
            return

        proc: subprocess.Popen[str] | None = None
        result_lines: list[str] = []
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**__import__("os").environ, **agent.env},
                text=True,
                encoding="utf-8",
            )

            for line in proc.stdout or []:
                if not line.strip():
                    continue
                result_lines.append(line)
                yield A2AEvent(event_type="stdout", text=line.rstrip("\n"))

            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if proc and proc.poll() is None:
                proc.kill()
            yield A2AEvent(event_type="error", text=f"Timeout after {timeout}s")
            return
        except Exception as e:
            yield A2AEvent(event_type="error", text=str(e))
            return
        finally:
            if proc and proc.poll() is None:
                proc.kill()

        # Try to parse last line as JSON
        result = ""
        for line in result_lines:
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    content = parsed.get("content", parsed.get("result", str(parsed)))
                    result = content if isinstance(content, str) else json.dumps(content)
                else:
                    result = str(parsed)
            except json.JSONDecodeError:
                result = line

        yield A2AEvent(event_type="completed", text=result, done=True)

    def _build_command(self, agent: ExternalAgentConfig, task: str) -> list[str] | None:
        name = agent.name.lower()
        if name == "claude":
            return ["claude", "--print", "--output-format", "json", task]
        if name == "codex":
            return ["codex", "--quiet", "--format", "json", task]
        return None

    @staticmethod
    def _capabilities_for(name: str) -> list[str]:
        if name == "claude":
            return ["code_generation", "research", "refactoring", "analysis"]
        if name == "codex":
            return ["code_generation", "research", "refactoring"]
        return []
