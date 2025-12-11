# Contributing

Thank you for considering a contribution to CostPilot! This guide explains how
we work and how to get your changes merged smoothly.

## Branching and Pull Requests
- Create feature branches from the latest `main` (e.g., `feat/<short-summary>` or `fix/<issue-id>`).
- Keep pull requests small and focused; open a draft PR early for visibility.
- Rebase onto `main` before requesting review to keep history clean.
- Provide a clear summary, testing notes, and any risks or follow-up work in the PR description.

## Commit Messages
We follow [Conventional Commits](https://www.conventionalcommits.org/) so our
history and releases stay readable. Examples:
- `feat(api): add cost breakdown endpoint`
- `fix(ui): correct currency formatting`
- `chore: update dependencies`

## Coding Standards
- Match the existing style in the area you are touching; prefer clarity over cleverness.
- Write small, single-purpose functions and keep public APIs well-documented.
- Add or update inline documentation and README sections when behavior changes.
- Ensure new code paths are covered by tests where practical.

## Tests and Local Quality Checks
Run the following before opening or updating a PR:
- `pip install -e .[dev]` to install dependencies with development extras.
- `pytest` to run the test suite.
- `ruff check .` to lint and `ruff format .` to auto-format where applicable.
- For type checking, run `mypy` if the project is configured.

If any command is not available in your environment, note that in the PR so reviewers know what was and was not run.

## Getting Help
If you have questions, open a discussion or ask in the PR comments. Early
feedback helps avoid rework. You can also reach the maintainer, Bardavouras
Konstantinos, at kostasbardavouras@gmail.com for guidance on complex changes.
