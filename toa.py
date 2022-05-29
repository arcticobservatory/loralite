import math
from logger import FakeLogger

class ToA:
    def __init__(self, sf, bw, preamble, cr, ldro, crc, hd, logger=None):
        self.sf = sf
        self.bw = bw
        self.preamble = preamble
        self.cr = cr
        self.ldro = ldro
        self.crc = crc
        self.hd = hd
        if logger is None:
            self.logger = FakeLogger()
        else:
            self.logger = logger


    def get_symbols_time(self, symbols=5):
        # symbol duration
        t_symbol = math.pow(2, int(self.sf)) / self.bw

        # preamble duration
        t_preamble = (symbols + 4.25) * t_symbol

        return t_preamble

    def get_time_on_air(self, pkt_size, sim_time=0):
        # symbol duration
        t_symbol = math.pow(2, int(self.sf)) / self.bw

        # preamble duration
        t_preamble = (self.preamble + 4.25) * t_symbol

        # payload size
        # pkt_size = len(packet['payload'].encode('utf8'))

        # low data rate optimization enabled if t_symbol > 16ms
        # read more: https://www.thethingsnetwork.org/forum/t/a-point-to-note-lora-low-data-rate-optimisation-flag/12007
        ldro = self.ldro
        if t_symbol > 0.016:
            ldro = 1

        # numerator and denominator of the time on air formula
        num = 8 * pkt_size - 4 * self.sf + 28 + 16 * self.crc - 20 * self.hd
        den = 4 * (self.sf - 2 * ldro)
        payload_symbol_count = 8 + max(math.ceil(num / den) * (self.cr + 4), 0)

        # payload duration
        t_payload = payload_symbol_count * t_symbol

        self.logger.debug(
            sim_time,
            f'SF: {self.sf}, headerDisabled: {self.hd}, codingRate: {self.cr}, '
            f'bandwidthHz: {self.bw}, nPreamble: {self.preamble}, crcEnabled: {self.crc}, '
            f'lowDataRateOptimizationEnabled: {ldro}'
        )
        self.logger.debug(sim_time, f'Packet of size {pkt_size} bytes')
        self.logger.debug(
            sim_time,
            f'Time computation: num = {num}, den = {den}, payloadSymbNb = {payload_symbol_count}, tSym = {t_symbol}'
        )
        self.logger.debug(sim_time, f'\ttPreamble = {t_preamble}')
        self.logger.debug(sim_time, f'\ttPayload = {t_payload}')
        self.logger.debug(sim_time, f'\tTotal time = {t_preamble + t_payload}')

        return t_preamble + t_payload
