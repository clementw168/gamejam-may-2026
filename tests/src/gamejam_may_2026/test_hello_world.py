from gamejam_may_2026.hello_world import HelloWorld

def test_hello_world():
    hello_world = HelloWorld()
    assert hello_world.message == "Hello, World!"

def test_hello_world_with_fixture(this_is_a_global_fixture):
    assert this_is_a_global_fixture == "this is a global fixture"
