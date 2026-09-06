"""`python -m satquery.api` — run the dev API server on http://localhost:8000."""

import uvicorn

if __name__ == "__main__":
    uvicorn.run("satquery.api.app:app", host="127.0.0.1", port=8000, reload=True)
