class HelloWorld:
    def __init__(self):
        self.message = "Hello, World!"

    def print_message(self):
        print(self.message)


if __name__ == "__main__":
    hello_world = HelloWorld()
    hello_world.print_message()
