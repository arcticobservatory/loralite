from definitions import *

class State:
    def __init__(self, dev_id, d_state=STATE_SLEEP, d_substate=SUBSTATE_NONE, r_state=STATE_OFF, r_substate=SUBSTATE_NONE):
        self.state = d_state
        self.substate = d_substate
        self.radio_state = r_state
        self.radio_substate = r_substate
        self._dev_id = dev_id
        self.timestamp = 0

    def set_timestamp(self, timestamp):
        self.timestamp = timestamp

    @staticmethod
    def check_state(state):
        if state not in STATE:
            raise RuntimeError(f'Given device state: {state} is not valid!')

    @staticmethod
    def check_device_substate(substate):
        if substate not in D_SUBSTATE:
            raise RuntimeError(f'Given device substate: {substate} is not valid!')

    @staticmethod
    def check_radio_substate(substate):
        if substate not in R_SUBSTATE:
            raise RuntimeError(f'Given radio substate: {substate} is not valid!')
