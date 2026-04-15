class FakeGPIO:
    def __init__(self, value):
        self.value = value

    def get_value(self, pin):
        return self.value