# Contributing

Thank you for helping improve Zapret GUI.

## Development setup

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Before a pull request

1. Run syntax checks:
   ```bat
   python -m compileall .
   ```
2. Run tests:
   ```bat
   python -m unittest discover -s tests
   ```
3. Do not commit `vendor/zapret` binaries, `dist`, `build`, personal config, or logs.
4. Keep third-party notices current if dependencies or bundled files change.
