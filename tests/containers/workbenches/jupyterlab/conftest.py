import pytest
from testcontainers.mysql import MySqlContainer


@pytest.fixture(scope="module")
def mysql_container():
    with MySqlContainer("mysql:8.0.26") as container:
        yield container
