# Contributing

Contributions are welcome, especially security improvements, safer defaults, Windows compatibility fixes, tests, and documentation.

## Before opening a pull request

1. Do not commit `.env`, endpoint URLs, tokens, audit logs, command output, personal paths, or other private machine data.
2. Keep the server bound to localhost by default.
3. Preserve confirmation-friendly tool descriptions for destructive and full-access actions.
4. Add or update tests for behavior changes.
5. Run `RUN_TESTS.bat` or `python -m pytest -q` before submitting.

## Development setup

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e . pytest
python -m pytest -q
```

## Security reports

Do not open a public issue containing an exploitable vulnerability, secret, or live endpoint. Use GitHub's private security reporting or contact the repository owner privately.
