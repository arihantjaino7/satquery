from pathlib import Path

import pytest

from scripts.make_fixtures import build_all


@pytest.fixture(scope="session")
def fixtures_dir(tmp_path_factory) -> Path:
    """Fresh, deterministic fixture set built once per test session.

    Deliberately independent of the repo's fixtures/ directory so tests
    never depend on someone having run scripts/make_fixtures.py first, and
    never mutate what's on disk for manual `python -m satquery inspect`.
    """
    out_dir = tmp_path_factory.mktemp("fixtures")
    build_all(out_dir, seed=42)
    return out_dir
