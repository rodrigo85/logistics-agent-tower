# Contributing

Thanks for taking the time. This guide keeps contributions predictable and reviews fast.

## Development setup

```bash
git clone https://github.com/rodrigo85/logistics-agent-tower.git
cd logistics-agent-tower
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pre-commit install
make seed && make test
```

Windows users without `make` can use `scripts\setup.bat` / `scripts\run.bat`.

## Workflow

1. Branch from `main`: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`.
2. Keep commits small and use [Conventional Commits](https://www.conventionalcommits.org/):
   `feat(routing): honour customer dock windows in OR-Tools model`.
3. Run `make check` (ruff, mypy, pytest) before pushing. CI runs the same.
4. Open a PR using the template; link the issue and update `CHANGELOG.md`.

## Code standards

* Python 3.10+, type hints everywhere, `ruff` for lint + format (120 columns).
* Library modules never configure logging; entry points call `configure_logging()`.
* Business rules live in `services/`; agents orchestrate, routers translate HTTP.
* Anything that changes a business rule (capacity thresholds, trip model, HITL
  triggers) needs a test in `tests/` and a note in `docs/ARCHITECTURE.md` or an ADR.
* Tests must not depend on network access. Mark external calls with
  `@pytest.mark.integration` and skip when credentials are absent.

## Reporting security issues

See [SECURITY.md](SECURITY.md). Please do not open public issues for vulnerabilities.
