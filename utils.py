from re import split
from random import getrandbits

ROUND_N = 4

class bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    BBLUE = '\033[44m'
    OKCYAN = '\033[96m'
    BCYAN = '\033[46m'
    OKGREEN = '\033[92m'
    BGREEN = '\033[42m'
    MAGNETA = '\033[35m'
    BMAGNETA = '\033[45m'
    WHITE = '\033[37m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    BRED = '\033[41m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'
    BYELLOW = '\033[43m'
    BWHITEDARK = '\033[7m'
    BBLINKING = '\033[5m'
    LIGHT_GRAY = '\033[2m'


def atof(text):
    try:
        retval = float(text)
    except ValueError:
        retval = text
    return retval

def natural_keys(text):
    '''
    alist.sort(key=natural_keys) sorts in human order
    http://nedbatchelder.com/blog/200712/human_sorting.html
    (See Toothy's implementation in the comments)
    float regex comes from https://stackoverflow.com/a/12643073/190597
    '''
    return [ atof(c) for c in split(r'[+-]?([0-9]+(?:[.][0-9]*)?|[.][0-9]+)', text) ]

def format_ms(time_ms, second_in_unit):
    return f'{int((time_ms - time_ms % second_in_unit) / second_in_unit):,}.{time_ms % second_in_unit:03d}s'
    # f'{int((self.next_expected_transmission_time  - self.next_expected_transmission_time  % config["general"]["second_in_unit"]) / config["general"]["second_in_unit"]):,}' \
    # f'.{self.next_expected_transmission_time % config["general"]["second_in_unit"]}s'

def get_random_true_false():
    return bool(getrandbits(1))