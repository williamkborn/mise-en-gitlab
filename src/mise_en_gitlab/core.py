# SPDX-Copyright: 2025-present William Born
# SPDX-License-Identifier: MIT
"""Core logic to parse mise.toml and generate GitLab CI YAML."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Iterable, Mapping, MutableMapping

import yaml

# tomllib in 3.11+, tomli fallback for 3.8-3.10
try:  # pragma: no cover - import path based on Python version
    import tomllib as _toml
except ModuleNotFoundError:  # pragma: no cover
    import tomli as _toml  # type: ignore[no-redef]


class ExitCode:
    """CLI exit codes for the generator."""

    # pylint: disable=too-few-public-methods
    SUCCESS = 0
    INVALID_OR_MISSING_CI_TASKS = 1
    MALFORMED_TOML_OR_SCHEMA = 2


@dataclass(frozen=True)
class GenerationResult:
    """Result of YAML generation."""

    yaml_text: str
    stages: list[str]
    jobs: list[str]


class NoCITasksError(Exception):
    """Raised when no CI-annotated tasks are found."""


class SchemaError(Exception):
    """Raised when input is structurally valid TOML, but fails schema expectations."""


def _ensure_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_rule_item(item: Any) -> dict[str, Any]:
    """Normalize a single rules item into a dict."""
    if isinstance(item, dict):
        return item
    if isinstance(item, str):
        if ":" in item:
            key, val = item.split(":", 1)
            return {key.strip(): val.strip()}
        return {"if": item}
    msg = "rules must be a list of strings or dicts"
    raise SchemaError(msg)


def _parse_rules(rules_value: Any) -> list[dict[str, Any]]:
    """Normalize rules into a list of dicts.

    Supports:
    - list of strings like "if: '$CI_COMMIT_BRANCH' == 'main'"
    - list of dicts
    """
    if rules_value is None:
        return []
    if isinstance(rules_value, list):
        return [_normalize_rule_item(item) for item in rules_value]
    msg = "rules must be a list"
    raise SchemaError(msg)


def _read_default_image(data: Mapping[str, Any]) -> str | None:
    """Read [ci.defaults].image if present."""
    ci_top = data.get("ci")
    if isinstance(ci_top, Mapping):
        defaults = ci_top.get("defaults")
        if isinstance(defaults, Mapping):
            img = defaults.get("image")
            if isinstance(img, str) and img:
                return img
    return None


def _parse_artifacts(artifacts_value: Any) -> dict[str, Any]:
    """Normalize artifacts into a dict as GitLab expects."""
    if artifacts_value is None:
        return {}
    if isinstance(artifacts_value, dict):
        return dict(artifacts_value)
    if isinstance(artifacts_value, list):
        return {"paths": list(artifacts_value)}
    msg = "artifacts must be a table/object or list of paths"
    raise SchemaError(msg)


def _collect_stages(ci_tasks: Iterable[tuple[str, Mapping[str, Any]]]) -> list[str]:
    stages: list[str] = []
    seen = set()
    for _, ci in ci_tasks:
        stage = ci.get("stage")
        if not isinstance(stage, str) or not stage:
            msg = "each [tasks.<name>.ci] must include non-empty 'stage'"
            raise SchemaError(msg)
        if stage not in seen:
            seen.add(stage)
            stages.append(stage)
    return stages


def _iter_ci_tasks(
    tasks: Mapping[str, Mapping[str, Any]],
) -> Iterable[tuple[str, Mapping[str, Any]]]:
    for task_name, task_body in tasks.items():
        ci = task_body.get("ci")
        if isinstance(ci, Mapping) and ci:
            yield task_name, ci


def _normalize_script(run_value: Any) -> list[str]:
    if run_value is None:
        msg = "task missing required 'run' field"
        raise SchemaError(msg)
    if isinstance(run_value, list):
        if not all(isinstance(x, str) for x in run_value):
            msg = "'run' list must contain only strings"
            raise SchemaError(msg)
        return list(run_value)
    if isinstance(run_value, str):
        return [run_value]
    msg = "'run' must be a string or a list of strings"
    raise SchemaError(msg)


if TYPE_CHECKING:
    # Imported for type checking only; annotations are postponed
    from pathlib import Path


def _collect_passthrough(ci: Mapping[str, Any]) -> dict[str, Any]:
    excluded = {"stage", "image", "rules", "artifacts", "needs"}
    return {k: v for k, v in ci.items() if k not in excluded}


def _build_job_base(
    task_body: Mapping[str, Any], ci: Mapping[str, Any], *, default_image: str | None
) -> MutableMapping[str, Any]:
    """Build base job fields (stage, image, script)."""
    job: MutableMapping[str, Any] = {}
    job["stage"] = ci.get("stage")
    image = ci.get("image", default_image)
    if image is not None:
        job["image"] = image
    job["script"] = _normalize_script(task_body.get("run"))
    return job


def _parse_needs(needs_value: Any) -> list[str]:
    if needs_value is None:
        return []
    if not isinstance(needs_value, list) or not all(isinstance(x, str) for x in needs_value):
        msg = "'needs' must be a list of job names (strings)"
        raise SchemaError(msg)
    return list(needs_value)


def _apply_optional_fields(job: MutableMapping[str, Any], ci: Mapping[str, Any]) -> None:
    parsed_rules = _parse_rules(ci.get("rules"))
    if parsed_rules:
        job["rules"] = parsed_rules
    parsed_artifacts = _parse_artifacts(ci.get("artifacts"))
    if parsed_artifacts:
        job["artifacts"] = parsed_artifacts
    needs = _parse_needs(ci.get("needs"))
    if needs:
        job["needs"] = needs
    for key, value in _collect_passthrough(ci).items():
        job[key] = value


def _build_job(
    task_body: Mapping[str, Any], ci: Mapping[str, Any], *, default_image: str | None
) -> MutableMapping[str, Any]:
    """Build a single GitLab job structure from task and its ci table."""
    job = _build_job_base(task_body, ci, default_image=default_image)
    _apply_optional_fields(job, ci)
    return job


def parse_mise_toml(path: Path) -> Mapping[str, Any]:
    """Load and parse the `mise.toml` into a Python mapping."""
    try:
        with path.open("rb") as f:
            data = _toml.load(f)
    except Exception as exc:  # pragma: no cover - exercised in integration test
        msg = f"Failed to parse TOML: {exc}"
        raise SchemaError(msg) from exc
    if not isinstance(data, Mapping):
        msg = "TOML root must be a table"
        raise SchemaError(msg)
    return data


def build_gitlab_ci_structure(data: Mapping[str, Any]) -> GenerationResult:
    """Build the GitLab CI structure from parsed mise data."""
    # Global defaults: [ci.defaults]
    default_image = _read_default_image(data)

    tasks = data.get("tasks")
    if not isinstance(tasks, Mapping) or not tasks:
        msg = "No tasks found"
        raise NoCITasksError(msg)

    ci_tasks = list(_iter_ci_tasks(tasks))  # preserves TOML order
    if not ci_tasks:
        msg = "No CI-annotated tasks found (no [tasks.<name>.ci] sections)"
        raise NoCITasksError(msg)

    stages = _collect_stages(ci_tasks)

    top: MutableMapping[str, Any] = {}
    top["stages"] = stages

    job_names: list[str] = []

    for task_name, ci in ci_tasks:
        task_body = tasks[task_name]
        job = _build_job(task_body, ci, default_image=default_image)

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
