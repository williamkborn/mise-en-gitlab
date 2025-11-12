# mise-en-gitlab

[![PyPI - Version](https://img.shields.io/pypi/v/mise-en-gitlab.svg)](https://pypi.org/project/mise-en-gitlab)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mise-en-gitlab.svg)](https://pypi.org/project/mise-en-gitlab)

---

## Overview

`mise-en-gitlab` converts a project's `mise.toml` into a GitLab CI configuration fragment.  
Define build/test/deploy tasks once in Mise and generate a valid `.gitlab-ci.yml` snippet or child-pipeline include from those definitions.

### Why
- Keep your CI config DRY by treating Mise as the single source of truth for tasks.
- Generate stable, schema-checked GitLab jobs directly from your task graph.
- Make pipelines self-describing and reproducible across environments.

### What gets generated
- `stages` list derived from each `[tasks.<name>.ci.stage]`
- One GitLab job per `[tasks.<name>.ci]` block
- Preserves ordering and relationships (`needs`, `rules`, `artifacts`, and other common keys)
- Optional global defaults via `[ci.defaults]` (e.g., default image)

---

## Installation

```console
pip install mise-en-gitlab
```

Requirements: Python 3.8+.

---

## Quick Start

Generate a GitLab CI YAML from `mise.toml`:

```bash
mise-en-gitlab generate --in mise.toml --out generated-ci.yml
```

- `--in`: path to input mise file (default: `mise.toml`)
- `--out`: path to write the generated YAML (default: `generated-ci.yml`)
- `-v/--verbose`: show debug logs

Exit codes:
- `0`: success
- `1`: invalid or missing CI-annotated tasks
- `2`: malformed TOML or schema error

---

## Input: Mise tasks annotated for CI

Any task under `[tasks.<name>]` becomes a GitLab job when it includes a `[tasks.<name>.ci]` table.

Minimal example:

```toml
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
```

### Global defaults

You can set a default image for all jobs (unless overridden by a job) using:

```toml
[ci.defaults]
image = "alpine:3.19"
```

---

## Output: GitLab CI YAML

Given the input above, the generated YAML (simplified) looks like:

```yaml
stages:
  - build
  - test
  - deploy

build:
  stage: build
  image: node:20
  script:
    - pnpm build
  rules:
    - if: '$CI_COMMIT_BRANCH' == 'main'
  artifacts:
    paths:
      - dist/

test:
  stage: test
  image: python:3.12
  script:
    - pytest

deploy:
  stage: deploy
  script:
    - ./scripts/deploy.sh
  rules:
    - if: '$CI_COMMIT_TAG'
  needs:
    - build
    - test
```

Notes on normalization:
- `rules` accepts a list of strings (e.g., `"if: <expr>"`) or dicts (`{ if = "...", when = "..." }`); both are normalized to GitLab's object form.
- `artifacts` can be a list (treated as `paths`) or a table (`paths`, `when`, `expire_in`, `reports`, etc.).
- `run` can be a string or a string list; it maps to `script`.
- Unrecognized keys under `[tasks.<name>.ci]` are passed through as-is (common keys like `before_script`, `after_script`, `tags`, `timeout`, `retry`, `interruptible`, `allow_failure`, `when`, `resource_group`, `parallel`, `services`, `variables` are supported by pass-through).

---

## Using with Dynamic Child Pipelines

Upload the generated file as an artifact and include it in a downstream:

```yaml
generate-from-mise:
  stage: build
  image: python:3.12
  script:
    - pip install mise-en-gitlab
    - mise-en-gitlab generate --in mise.toml --out generated-ci.yml
  artifacts:
    paths:
      - generated-ci.yml

trigger:
  stage: test
  trigger:
    include:
      - artifact: generated-ci.yml
        job: generate-from-mise
    strategy: depend
```

---

## Definition of Done (internal quality bar)

When `mise-en-gitlab generate` runs on a valid `mise.toml`:
- Produces valid GitLab CI YAML with proper `stages`
- Outputs one job per `[tasks.*.ci]` block with preserved relationships
- Output is compatible with GitLab’s pipeline linter
- Works as a dynamic pipeline include without further manual edits
- Non-CI tasks are ignored
- CLI exits with appropriate codes and readable feedback for errors

---

## Troubleshooting

- Exit code `1`: No `[tasks.<name>.ci]` sections found.
- Exit code `2`: TOML parse error or schema error (e.g., missing `stage` in a CI-annotated task, `needs` not a list of strings, missing `run`).
- Python 3.8–3.10 use `tomli` under the hood; Python 3.11+ use `tomllib`.

---

## Development

This repo includes a `mise.toml` with common tasks:

```bash
# Install tool versions and generate a pre-commit hook powered by mise tasks
mise run setup-dev

# Run the full precommit pipeline (format, lint, type-check, tests)
mise precommit
```

Or directly with Hatch:

```bash
hatch fmt
hatch run lizard
hatch run pydoclint
hatch run pylint
hatch run typecheck
hatch run test
```

---

## License

`mise-en-gitlab` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
# mise-en-gitlab

[![PyPI - Version](https://img.shields.io/pypi/v/mise-en-gitlab.svg)](https://pypi.org/project/mise-en-gitlab)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/mise-en-gitlab.svg)](https://pypi.org/project/mise-en-gitlab)

-----

## Table of Contents

- [Installation](#installation)
- [License](#license)

## Installation

```console
pip install mise-en-gitlab
```

## License

`mise-en-gitlab` is distributed under the terms of the [MIT](https://spdx.org/licenses/MIT.html) license.
