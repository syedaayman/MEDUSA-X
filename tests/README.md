# Tests

This starter has no automated test suite yet. Current smoke checks:

- From `backend/`, run `python -m compileall -q .` and start `python main.py`; check
  `http://127.0.0.1:8000/health` and the empty patient endpoints.
- From `frontend/`, run `npm run build`.

When adding tests, use synthetic fixtures only. Do not include real patient documents
or personal health information in test data.
