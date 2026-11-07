# Environment and dependency reproducibility

## Tested configuration (Phase 2.12 freeze)

| Item | Value |
|------|--------|
| OS | Windows 11 (build 10.0.26200) |
| Python | 3.13.9 (Anaconda) |
| networkx | 3.5 |
| numpy | 2.2.6 |
| Declared support | Python ≥ 3.10 (`pyproject.toml`) |

Optional (dev/viz): `pytest>=7.0`, `matplotlib>=3.7`.

## Install (clean environment)

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# Unix: source .venv/bin/activate
pip install -U pip
pip install -e ".[dev]"
# or: pip install -r requirements.txt && pip install -e .
```

Authoritative package metadata: `pyproject.toml`.  
Convenience pins / notes: `requirements.txt`.

## Notes

- Do not treat Cursor’s ambient packages as the project lockfile.
- Matplotlib is optional for plotting; core algorithms do not require it.
- Legacy code under `legacy/` is not part of the active install surface.
