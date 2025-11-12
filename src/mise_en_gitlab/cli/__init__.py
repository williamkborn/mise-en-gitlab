# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""mise-en-gitlab CLI"""

from pathlib import Path

import click

from mise_en_gitlab.__about__ import __version__
from mise_en_gitlab.core import ExitCode, generate_ci_yaml
from mise_en_gitlab.logging import init_cli_logging


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=False
)
@click.version_option(version=__version__, prog_name="mise-en-gitlab")
def mise_en_gitlab() -> None:
    """mise-en-gitlab CLI"""
    # Group entry point; subcommands implement functionality.
    return


@mise_en_gitlab.command("generate")
@click.option(
    "--in",
    "in_path",
    type=click.Path(path_type=str, exists=False, dir_okay=False),
    default="mise.toml",
    show_default=True,
    help="Path to input mise.toml",
)
@click.option(
    "--out",
    "out_path",
    type=click.Path(path_type=str, dir_okay=False),
    default="generated-ci.yml",
    show_default=True,
    help="Path to write generated GitLab CI YAML",
)
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
def generate(in_path: str, out_path: str, *, verbose: bool) -> None:
    """Generate GitLab CI YAML from mise.toml."""
    init_cli_logging(verbose=verbose)

    input_file = Path(in_path)
    output_file = Path(out_path)

    if not input_file.exists():
        click.secho(f"Input file not found: {input_file}", fg="red", err=True)
        raise click.exceptions.Exit(ExitCode.MALFORMED_TOML_OR_SCHEMA)

    exit_code = generate_ci_yaml(input_file, output_file)
    if exit_code == ExitCode.SUCCESS:
        click.secho(f"Generated GitLab CI YAML → {output_file}", fg="green", err=False)
    elif exit_code == ExitCode.INVALID_OR_MISSING_CI_TASKS:
        click.secho(
            "No CI-annotated tasks found. Add [tasks.<name>.ci] sections.",
            fg="yellow",
            err=True,
        )
    elif exit_code == ExitCode.MALFORMED_TOML_OR_SCHEMA:
        click.secho("Malformed TOML or schema error.", fg="red", err=True)
    raise click.exceptions.Exit(exit_code)
