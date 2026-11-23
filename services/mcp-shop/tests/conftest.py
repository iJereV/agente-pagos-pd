import pytest
from shop_fakes import World


@pytest.fixture
def world() -> World:
    return World()
