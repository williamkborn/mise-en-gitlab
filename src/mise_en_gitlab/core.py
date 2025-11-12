# SPDX-Copyright: 2025-present William Born
# SPDX-License-Identifier: MIT
"""Core logic to parse mise.toml and generate GitLab CI YAML."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, MutableMapping, Tuple

import yaml

# tomllib in 3.11+, tomli fallback for 3.8-3.10
try:  # pragma: no cover - import path based on Python version
    import tomllib as _toml  # type: ignore[assignment]
except ModuleNotFoundError:  # pragma: no cover
    import tomli as _toml  # type: ignore[no-redef]


class ExitCode:
    SUCCESS = 0
    INVALID_OR_MISSING_CI_TASKS = 1
    MALFORMED_TOML_OR_SCHEMA = 2


@dataclass(frozen=True)
class GenerationResult:
    """Result of YAML generation."""

    yaml_text: str
    stages: List[str]
    jobs: List[str]


class NoCITasksError(Exception):
    """Raised when no CI-annotated tasks are found."""


class SchemaError(Exception):
    """Raised when input is structurally valid TOML, but fails schema expectations."""


def _ensure_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_rules(rules_value: Any) -> List[Dict[str, Any]]:
    """Normalize rules into a list of dicts.

    Supports:
    - list of strings like "if: '$CI_COMMIT_BRANCH' == 'main'"
    - list of dicts
    """
    if rules_value is None:
        return []
    if isinstance(rules_value, list):
        normalized: List[Dict[str, Any]] = []
        for item in rules_value:
            if isinstance(item, dict):
                normalized.append(item)
            elif isinstance(item, str):
                # Parse "key: value" into {key: value}
                if ":" in item:
                    key, val = item.split(":", 1)
                    normalized.append({key.strip(): val.strip()})
                else:
                    # Fallback: treat as 'if' expression if no explicit key
                    normalized.append({"if": item})
            else:
                raise SchemaError("rules must be a list of strings or dicts")
        return normalized
    raise SchemaError("rules must be a list")


def _parse_artifacts(artifacts_value: Any) -> Dict[str, Any]:
    """Normalize artifacts into a dict as GitLab expects."""
    if artifacts_value is None:
        return {}
    if isinstance(artifacts_value, dict):
        return dict(artifacts_value)
    if isinstance(artifacts_value, list):
        return {"paths": list(artifacts_value)}
    raise SchemaError("artifacts must be a table/object or list of paths")


def _collect_stages(ci_tasks: Iterable[Tuple[str, Mapping[str, Any]]]) -> List[str]:
    stages: List[str] = []
    seen = set()
    for _, ci in ci_tasks:
        stage = ci.get("stage")
        if not isinstance(stage, str) or not stage:
            raise SchemaError("each [tasks.<name>.ci] must include non-empty 'stage'")
        if stage not in seen:
            seen.add(stage)
            stages.append(stage)
    return stages


def _iter_ci_tasks(tasks: Mapping[str, Mapping[str, Any]]) -> Iterable[Tuple[str, Mapping[str, Any]]]:
    for task_name, task_body in tasks.items():
        ci = task_body.get("ci")
        if isinstance(ci, Mapping) and ci:
            yield task_name, ci


def _normalize_script(run_value: Any) -> List[str]:
    if run_value is None:
        raise SchemaError("task missing required 'run' field")
    if isinstance(run_value, list):
        if not all(isinstance(x, str) for x in run_value):
            raise SchemaError("'run' list must contain only strings")
        return list(run_value)
    if isinstance(run_value, str):
        return [run_value]
    raise SchemaError("'run' must be a string or a list of strings")


def parse_mise_toml(path: Path) -> Mapping[str, Any]:
    """Load and parse the `mise.toml` into a Python mapping."""
    try:
        with path.open("rb") as f:
            data = _toml.load(f)
    except Exception as exc:  # pragma: no cover - exercised in integration test
        raise SchemaError(f"Failed to parse TOML: {exc}") from exc
    if not isinstance(data, Mapping):
        raise SchemaError("TOML root must be a table")
    return data


def build_gitlab_ci_structure(data: Mapping[str, Any]) -> GenerationResult:
    """Build the GitLab CI structure from parsed mise data."""
    tasks = data.get("tasks")
    if not isinstance(tasks, Mapping) or not tasks:
        raise NoCITasksError("No tasks found")

    ci_tasks = list(_iter_ci_tasks(tasks))  # preserves TOML order
    if not ci_tasks:
        raise NoCITasksError("No CI-annotated tasks found (no [tasks.<name>.ci] sections)")

    stages = _collect_stages(ci_tasks)

    top: MutableMapping[str, Any] = {}
    top["stages"] = stages

    job_names: List[str] = []

    for task_name, ci in ci_tasks:
        task_body = tasks[task_name]
        run_value = task_body.get("run")
        script = _normalize_script(run_value)

        job: MutableMapping[str, Any] = {}
        # Required
        job["stage"] = ci.get("stage")
        # Optional, common fields with light normalization
        image = ci.get("image")
        if image is not None:
            job["image"] = image

        job["script"] = script

        rules = ci.get("rules")
        parsed_rules = _parse_rules(rules)
        if parsed_rules:
            job["rules"] = parsed_rules

        artifacts = ci.get("artifacts")
        parsed_artifacts = _parse_artifacts(artifacts)
        if parsed_artifacts:
            job["artifacts"] = parsed_artifacts

        needs = ci.get("needs")
        if needs is not None:
            if not isinstance(needs, list) or not all(isinstance(x, str) for x in needs):
                raise SchemaError("'needs' must be a list of job names (strings)")
            job["needs"] = list(needs)

        # Pass-through any other keys under .ci that we do not explicitly handle
        passthrough_keys = {
            k: v
            for k, v in ci.items()
            if k
            not in {
                "stage",
                "image",
                "rules",
                "artifacts",
                "needs",
            }
        }
        for key, value in passthrough_keys.items():
            job[key] = value

        top[task_name] = job
        job_names.append(task_name)

    yaml_text = yaml.safe_dump(top, sort_keys=False)
    return GenerationResult(yaml_text=yaml_text, stages=stages, jobs=job_names)


def generate_ci_yaml(input_path: Path, output_path: Path) -> int:
    """Read input mise.toml, generate CI YAML, write to output path.

    Returns an exit code per spec.
    """
    try:
        data = parse_mise_toml(input_path)
        result = build_gitlab_ci_structure(data)
    except NoCITasksError:
        return ExitCode.INVALID_OR_MISSING_CI_TASKS
    except SchemaError:
        return ExitCode.MALFORMED_TOML_OR_SCHEMA

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(result.yaml_text, encoding="utf-8")
    return ExitCode.SUCCESS


