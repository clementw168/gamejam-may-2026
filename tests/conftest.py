import pytest


@pytest.fixture
def this_is_a_global_fixture():
    return "this is a global fixture"
