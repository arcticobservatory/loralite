import math
from mobility import get_distance
from numpy import random

class LogDistancePropagationLossModel:

    def __init__(self, exponent, ref_distance, ref_loss, sigma=0.0):
        self.exponent = exponent
        self.ref_distance = ref_distance
        self.ref_loss = ref_loss
        self.sigma = sigma

    def calculate_rx_power(self, lou_a, lou_b, tx_power_dbm):
        distance = get_distance(lou_a, lou_b)
        if distance <= self.ref_distance:
            return tx_power_dbm - self.ref_loss

        path_loss_db = 10 * self.exponent * math.log10(distance / self.ref_distance) + random.normal(0.0, self.sigma)
        rxc = -self.ref_loss - path_loss_db

        log = 'distance={}m, reference-attenuation={}db, attenuation coefficient={}db'.format(
            distance, -self.ref_loss, rxc
        )

        return round(tx_power_dbm + rxc, 2), log

    def calculate_max_distance(self, tx_power_dbm, max_sensitivity):
        distance, sensitivity = [self.ref_distance, 0]
        while sensitivity > max_sensitivity:
            distance += 1
            if distance <= self.ref_distance:
                return tx_power_dbm - self.ref_loss

            path_loss_db = 10 * self.exponent * math.log10(distance / self.ref_distance) + random.normal(0.0, self.sigma)
            rxc = -self.ref_loss - path_loss_db
            sensitivity = round(tx_power_dbm + rxc, 2)

        return distance

