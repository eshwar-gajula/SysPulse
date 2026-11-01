# Contributing

Thank you for helping improve SysPulse. Keep changes local-first, read-only, and focused on explaining evidence rather than taking action on a machine.

## Local checks

```bash
python -m pip install -e '.[dev]'
python -m pytest
python -m pip install pip-audit
python -m pip_audit -r requirements-audit.txt
ruff check backend tests

cd frontend
npm ci
npm test
npm run build
npm audit --audit-level=high
```

Please add deterministic tests for diagnostic rules and API changes. Avoid tests that need elevated privileges, access real user process command lines, create network listeners outside loopback, or generate unbounded CPU or memory load. Keep dependencies current and explain any platform-specific behavior in the README.
