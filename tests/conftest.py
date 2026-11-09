import pytest

from tsunagu.config import SCENARIOS
from tsunagu.exporters import api_json, duckdb_out
from tsunagu.simulate import run


@pytest.fixture(scope="session")
def tiny():
    return run(SCENARIOS["tiny"])


@pytest.fixture(scope="session")
def tiny_db(tiny, tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "tiny.duckdb"
    duckdb_out.write(tiny, path)
    return path


@pytest.fixture(scope="session")
def tiny_api(tiny, tmp_path_factory):
    folder = tmp_path_factory.mktemp("api")
    api_json.write(tiny, folder)
    return folder
