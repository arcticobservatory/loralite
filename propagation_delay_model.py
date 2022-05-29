from mobility import get_distance


class ConstantSpeedPropagationDelayModel():

    # The default value is the propagation speed of light in the vacuum.
    def __init__(self, speed=299792458):
        self.speed = speed

    def get_delay(self, dev1, dev2):
        distance = get_distance(dev1, dev2)

        return float(distance) / float(self.speed)
