# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""Feature coverage tests for widely-used GitLab CI job keys."""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

import yaml
from click.testing import CliRunner

from mise_en_gitlab.cli import mise_en_gitlab

if TYPE_CHECKING:
    from pathlib import Path


def _write(tmp_path: Path, name: str, content: str) -> Path:
    p = tmp_path / name
    p.write_text(dedent(content).strip() + "\n", encoding="utf-8")
    return p


def _run_generate(
    tmp_path: Path, mise_text: str, out_name: str = "generated-ci.yml"
) -> tuple[int, Path]:
    mise = _write(tmp_path, "mise.toml", mise_text)
    out = tmp_path / out_name
    result = CliRunner().invoke(
        mise_en_gitlab, ["generate", "--in", str(mise), "--out", str(out)]
    )
    return result.exit_code, out


def test_job_pass_through_common_fields(tmp_path: Path) -> None:
    """Ensure common GitLab keys are passed through and normalized."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [tasks.build]
        run = ["echo a", "echo b"]

        [tasks.build.ci]
        stage = "build"
        before_script = ["echo before"]
        after_script = ["echo after"]
        tags = ["docker"]
        timeout = "30m"
        retry = { max = 2, when = ["runner_system_failure"] }
        interruptible = true
        allow_failure = false
        when = "on_success"
        resource_group = "rg-1"
        parallel = 2
        services = ["postgres:15"]
        [tasks.build.ci.variables]
        TZ = "UTC"

        [tasks.build.ci.artifacts]
        paths = ["dist/"]
        when = "always"
        expire_in = "1 week"
        [tasks.build.ci.artifacts.reports]
        dotenv = ".env"

        [tasks.test]
        run = "pytest -q"
        [tasks.test.ci]
        stage = "test"
        needs = ["build"]
        image = "python:3.12"

        [tasks.deploy]
        run = "./deploy.sh"
        [tasks.deploy.ci]
        stage = "deploy"
        rules = [
          { if = "'$CI_COMMIT_TAG'" },
          { when = "manual" }
        ]
        """,
    )
    assert exit_code == 0
    assert out.exists()

    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["stages"] == ["build", "test", "deploy"]

    build = data["build"]
    assert build["stage"] == "build"
    assert build["before_script"] == ["echo before"]
    assert build["after_script"] == ["echo after"]
    assert build["script"] == ["echo a", "echo b"]
    assert build["tags"] == ["docker"]
    assert build["timeout"] == "30m"
    assert build["retry"] == {"max": 2, "when": ["runner_system_failure"]}
    assert build["interruptible"] is True
    assert build["allow_failure"] is False
    assert build["when"] == "on_success"
    assert build["resource_group"] == "rg-1"
    assert build["parallel"] == 2
    assert build["services"] == ["postgres:15"]
    assert build["variables"]["TZ"] == "UTC"
    assert build["artifacts"]["paths"] == ["dist/"]
    assert build["artifacts"]["when"] == "always"
    assert build["artifacts"]["expire_in"] == "1 week"
    assert build["artifacts"]["reports"]["dotenv"] == ".env"

    test_job = data["test"]
    assert test_job["stage"] == "test"
    assert test_job["needs"] == ["build"]
    assert test_job["image"] == "python:3.12"
    assert test_job["script"] == ["pytest -q"]

    deploy = data["deploy"]
    assert deploy["stage"] == "deploy"
    assert deploy["rules"] == [{"if": "'$CI_COMMIT_TAG'"}, {"when": "manual"}]
    assert deploy["script"] == ["./deploy.sh"]


def test_rules_string_and_artifacts_list_normalization(tmp_path: Path) -> None:
    """String rules and list artifacts are normalized as expected."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [ci.defaults]
        image = "alpine:3"

        [tasks.a]
        run = "echo 1"
        [tasks.a.ci]
        stage = "build"
        rules = ["if: '$CI_PIPELINE_SOURCE' == 'push'"]
        artifacts = ["out/"]

        [tasks.b]
        run = "echo 2"
        [tasks.b.ci]
        stage = "build"
        """,
    )
    assert exit_code == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["stages"] == ["build"]

    assert data["a"]["rules"] == [{"if": "'$CI_PIPELINE_SOURCE' == 'push'"}]
    assert data["a"]["artifacts"]["paths"] == ["out/"]
    assert data["a"]["script"] == ["echo 1"]
    # defaults image applied
    assert data["a"]["image"] == "alpine:3"
    assert data["b"]["script"] == ["echo 2"]
    assert data["b"]["image"] == "alpine:3"


def test_non_ci_tasks_ignored_and_stage_dedup(tmp_path: Path) -> None:
    """Non-CI tasks are ignored; duplicate stages deduped in order."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [tasks.one]
        run = "echo one"
        [tasks.one.ci]
        stage = "build"

        [tasks.two]
        run = "echo two"
        [tasks.two.ci]
        stage = "build"

        [tasks.three]
        run = "echo three"
        """,
    )
    assert exit_code == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["stages"] == ["build"]
    assert "one" in data
    assert "two" in data
    assert "three" not in data


def test_defaults_image_applied_and_overridden(tmp_path: Path) -> None:
    """Global defaults image is applied unless job specifies its own image."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [ci.defaults]
        image = "alpine:3.19"

        [tasks.build]
        run = "echo build"
        [tasks.build.ci]
        stage = "build"

        [tasks.test]
        run = "pytest"
        [tasks.test.ci]
        stage = "test"
        image = "python:3.12"
        """,
    )
    assert exit_code == 0
    data = yaml.safe_load(out.read_text(encoding="utf-8"))
    assert data["stages"] == ["build", "test"]
    assert data["build"]["image"] == "alpine:3.19"
    assert data["test"]["image"] == "python:3.12"


def test_invalid_needs_type_exit_2(tmp_path: Path) -> None:
    """'needs' must be a list of strings."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [tasks.x]
        run = "echo hi"
        [tasks.x.ci]
        stage = "build"
        needs = "build"
        """,
        out_name="ci.yml",
    )
    assert exit_code == 2
    assert not out.exists()


def test_missing_run_in_ci_exit_2(tmp_path: Path) -> None:
    """CI-annotated task without 'run' should error."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [tasks.x]
        [tasks.x.ci]
        stage = "build"
        """,
        out_name="ci.yml",
    )
    assert exit_code == 2
    assert not out.exists()


def test_rules_invalid_item_exit_2(tmp_path: Path) -> None:
    """rules must be strings or dicts."""
    exit_code, out = _run_generate(
        tmp_path,
        """
        [tasks.x]
        run = "echo hi"
        [tasks.x.ci]
        stage = "build"
        rules = [1, "if: '$CI_COMMIT_BRANCH' == 'main'"]
        """,
        out_name="ci.yml",
    )
    assert exit_code == 2
    assert not out.exists()
