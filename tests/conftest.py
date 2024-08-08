import pytest

# https://anyio.readthedocs.io/en/stable/testing.html
@pytest.fixture(autouse=True)
def anyio_backend():
    return 'asyncio'
