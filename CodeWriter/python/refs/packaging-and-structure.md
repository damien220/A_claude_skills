# Packaging & Project Structure — Python Reference

Grounded in **PEP 517/518** (build system), **PEP 621** (project metadata in `pyproject.toml`), and
the Python Packaging User Guide. One `pyproject.toml` is the single source of truth for build,
metadata, dependencies, and tool config.

## Use a `src/` layout

Put the importable package under `src/`. This prevents the classic bug where tests import the
package from the working directory instead of the installed copy, so "it works locally but the
wheel is broken" can't happen.

```
myproject/
├── pyproject.toml
├── README.md
├── src/
│   └── myproject/
│       ├── __init__.py
│       ├── core.py
│       └── cli.py
└── tests/
    └── test_core.py
```

```python
# WRONG — flat layout: `import myproject` may resolve to the source tree, masking packaging bugs
myproject/
├── myproject/__init__.py
└── tests/
```

## `pyproject.toml` declares everything (PEP 621)

Metadata, dependencies, entry points, and tool config live in one file. No `setup.py` /
`setup.cfg` for new projects.

```toml
[build-system]
requires = ["hatchling"]                 # or setuptools>=61, pdm-backend, flit-core…
build-backend = "hatchling.build"

[project]
name = "myproject"
version = "0.1.0"
description = "One-line summary of the package."
requires-python = ">=3.10"
readme = "README.md"
dependencies = [
    "httpx>=0.27",
    "pydantic>=2.6",
]

[project.optional-dependencies]
dev = ["pytest>=8", "mypy>=1.8", "ruff>=0.5"]

[project.scripts]
myproject = "myproject.cli:main"         # installs a `myproject` console command

# Tool config lives here too (see tooling/pyproject-snippet.toml for the [tool.ruff]/[tool.mypy] blocks)
```

## Expose CLIs through entry points, not loose scripts

A `[project.scripts]` entry point creates a proper console command on install, cross-platform, that
points at a function. Don't ship a bare `script.py` that users run with `python path/to/script.py`.

```python
# src/myproject/cli.py
def main() -> int:
    """Entry point for the `myproject` console command."""
    ...
    return 0
```

## Dependency specification: constrain libraries, pin applications

| Project kind                       | Strategy                                                                                | Why                                         |
| ---------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------- |
| **Library** (others depend on it)  | loose lower bounds + compatible-release (`>=2.6,<3`)                                    | don't over-constrain consumers' resolutions |
| **Application/service** (deployed) | a fully pinned **lock file** (`uv.lock`, `poetry.lock`, `pip-tools` `requirements.txt`) | reproducible, identical deploys             |

Declare _abstract_ dependencies in `pyproject.toml`; record _concrete_ pinned versions in a lock
file committed alongside. Separate runtime deps from dev/test deps (optional-dependencies group).

## `__init__.py` defines the package's public surface

Keep `__init__.py` thin: re-export the intended public API and (optionally) set `__all__`. Avoid
heavy work or side effects at import time — importing the package should be cheap and safe.

```python
# src/myproject/__init__.py
"""myproject — public API."""
from myproject.core import Client, process

__all__ = ["Client", "process"]
```

## One responsibility per module; avoid `utils.py`

Group code by domain concept, not by "kind of thing." A growing `utils.py`/`helpers.py` is a smell —
split functions into modules named for what they do (`retry.py`, `serialization.py`). Use a
sub-package (`mypkg/api/`) when a concept grows past one file. Prefer absolute imports
(`from myproject.core import X`); reserve relative imports for within a package.

## Dev_util_prj — `config_manager_factory`

`Config_Manager` is a **scaffolding generator**, not a runtime library. Run it once to produce
config files, loaders, env templates, and JSON Schema for Web APIs, CLI tools, MCP servers, or
microservices — the generated output has no runtime dependency on this tool.

**Install (clone from source):**

```bash
git clone https://github.com/damien220/Configuration_Manager
cd Config_Manager/dist && pip install config_manager-0.1.0-py3-none-any.whl
```

```bash
# Run the interactive generator (prompts for app type, format, env profiles, secrets handling)
python -m config_manager_factory
# Outputs: config/default.yaml, .env.example, config_loader.py, schema.json
# No runtime dep on this tool — generated files are self-contained
```
