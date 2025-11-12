# SPDX-FileCopyrightText: 2025-present William Born <william.born.git@gmail.com>
#
# SPDX-License-Identifier: MIT
"""mise-en-gitlab CLI"""

import click

from mise_en_gitlab.__about__ import __version__


@click.group(
    context_settings={"help_option_names": ["-h", "--help"]}, invoke_without_command=True
)
@click.version_option(version=__version__, prog_name="mise-en-gitlab")
def mise_en_gitlab() -> None:
    """mise-en-gitlab CLI"""
    click.echo("Hello world!")
