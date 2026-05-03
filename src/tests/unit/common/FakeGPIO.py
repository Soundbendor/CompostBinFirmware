class FakeGPIO:
    """
    Fake GPIO class. Imitates gpiod.LineRequest
    """
    def __init__(self, value):
        self.value = value

    def get_value(self, pin):
        return self.value