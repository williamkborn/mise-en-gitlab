# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""CLI integration tests for mise-en-gitlab."""

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


def test_generate_success(tmp_path: Path) -> None:
    """End-to-end: generate expected YAML from sample mise.toml."""
    mise = _write(
        tmp_path,
        "mise.toml",
        """
        [tasks.build]
        run = "pnpm build"

        [tasks.build.ci]
        stage = "build"
        image = "node:20"
        rules = ["if: '$CI_COMMIT_BRANCH' == 'main'"]
        artifacts = ["dist/"]

        [tasks.test]
        run = "pytest"

        [tasks.test.ci]
        stage = "test"
        image = "python:3.12"

        [tasks.deploy]
        run = "./scripts/deploy.sh"

        [tasks.deploy.ci]
        stage = "deploy"
        rules = ["if: '$CI_COMMIT_TAG'"]
        needs = ["build", "test"]
        """,
    )
    output = tmp_path / "generated-ci.yml"
    runner = CliRunner()
    result = runner.invoke(
        mise_en_gitlab, ["generate", "--in", str(mise), "--out", str(output)]
    )
    assert result.exit_code == 0, result.output
    assert output.exists()

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["stages"] == ["build", "test", "deploy"]

    assert "build" in data
    assert "test" in data
    assert "deploy" in data

    assert data["build"]["stage"] == "build"
    assert data["build"]["image"] == "node:20"
    assert data["build"]["script"] == ["pnpm build"]
    assert data["build"]["rules"] == [{"if": "'$CI_COMMIT_BRANCH' == 'main'"}]
    assert data["build"]["artifacts"]["paths"] == ["dist/"]

    assert data["test"]["stage"] == "test"
    assert data["test"]["image"] == "python:3.12"
    assert data["test"]["script"] == ["pytest"]

    assert data["deploy"]["stage"] == "deploy"
    assert data["deploy"]["script"] == ["./scripts/deploy.sh"]
    assert data["deploy"]["rules"] == [{"if": "'$CI_COMMIT_TAG'"}]
    assert data["deploy"]["needs"] == ["build", "test"]


def test_generate_no_ci_tasks_exit_1(tmp_path: Path) -> None:
    """Return exit code 1 when no [tasks.*.ci] present."""
    mise = _write(
        tmp_path,
        "mise.toml",
        """
        [tasks.lint]
        run = "ruff check ."
        """,
    )
    out = tmp_path / "ci.yml"
    result = CliRunner().invoke(
        mise_en_gitlab, ["generate", "--in", str(mise), "--out", str(out)]
    )
    assert result.exit_code == 1
    assert not out.exists()


def test_generate_malformed_toml_exit_2(tmp_path: Path) -> None:
    """Return exit code 2 on malformed TOML."""
    mise = _write(
        tmp_path,
        "mise.toml",
        """
        [tasks.lint
        run = "ruff check ."
        """,
    )
    out = tmp_path / "ci.yml"
    result = CliRunner().invoke(
        mise_en_gitlab, ["generate", "--in", str(mise), "--out", str(out)]
    )
    assert result.exit_code == 2
    assert not out.exists()


def test_missing_stage_in_ci_exit_2(tmp_path: Path) -> None:
    """Require 'stage' in [tasks.*.ci]."""
    mise = _write(
        tmp_path,
        "mise.toml",
        """
        [tasks.build]
        run = "echo hi"
        [tasks.build.ci]
        image = "alpine:3"
        """,
    )
    out = tmp_path / "ci.yml"
    result = CliRunner().invoke(
        mise_en_gitlab, ["generate", "--in", str(mise), "--out", str(out)]
    )
    assert result.exit_code == 2
    assert not out.exists()
