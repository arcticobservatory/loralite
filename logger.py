import logging
from utils import ROUND_N
from sortedcontainers import SortedDict

DEBUG = logging.DEBUG
INFO = logging.INFO
WARNING = logging.WARNING
ERROR = logging.ERROR
CRITICAL = logging.CRITICAL
ONLY_ALWAYS = 100

class FakeLogger:
    def debug(self, t, msg):
        new_entry = f'{int((t - t % 1000) / 1000):10,}.{t % 1000:03d}s\t{msg}'
        print(new_entry)

class Logger:
    def __init__(self, log_level=DEBUG, forced=False):
        if log_level not in [DEBUG, INFO, WARNING, ERROR, CRITICAL, ONLY_ALWAYS]:
            raise RuntimeError('Unknown log level: {}'.format(log_level))
        self._log_level = log_level
        self._log = SortedDict()
        self._previous_ts = 0
        self._last_ts = 0
        self._sim_time = 0
        self._file = None
        self._forced = forced
        # logging.basicConfig(level=log_level)

    def set_file(self, file_path):
        self._file = open(file_path, 'w')

    def close_file(self):
        if self._file is not None:
            self._file.close()

    def debug(self, t, msg):
        if self._log_level <= DEBUG:
            self._print(t, msg)
        # logging.debug(msg)

    def info(self, t, msg):
        if self._log_level <= INFO:
            self._print(t, msg)
        # logging.info(msg)

    def warning(self, t, msg):
        if self._log_level <= WARNING:
            self._print(t, msg)
        # logging.warning(msg)

    def error(self, t, msg):
        if self._log_level <= ERROR:
            self._print(t, msg)
        # logging.error(msg)

    def critical(self, t, msg):
        if self._log_level <= CRITICAL:
            self._print(t, msg)
        # logging.critical(msg)

    def always(self, t, msg):
        self._print(t, msg)

    def set_sim_time(self, sim_time):
        self._sim_time = sim_time

    def _flush(self):
        # log_list = list(self._log)
        # log_list.sort()

        for x in self._log:
            for y in self._log[x]:
                if self._file is not None:
                    self._file.write(f'{y}\n')
                print(y)       
        
        self._log.clear()

    def _print(self, t, msg):
        new_entry = f'{int((t - t % 1000) / 1000):10,}.{t % 1000:03d}s\t{msg}'
        if t not in self._log:
            self._log[t] = []

        self._log[t].append(new_entry)
        
        if t - self._last_ts >= 10000 or t == self._sim_time or self._forced:
            # log_list = list(self._log)
            # log_list.sort()

            for x in self._log:
                for y in self._log[x]:
                    if self._file is not None:
                        self._file.write(f'{y}\n')
                    print(y)
                        
            
            self._log.clear()

        self._last_ts = t
