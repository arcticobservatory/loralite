from definitions import *
from utils import bcolors, ROUND_N
from state import State

class Energy:
    # DEVICE default values for Sparkfun Arthemis Nano
    #
    # RADIO default values for sx1276 from Semtech datasheet: https://www.mouser.com/datasheet/2/761/sx1276-1278113.pdf
    # page 14
    def __init__(self, device_energy_ch, radio_energy_ch, v_load_drop, second_in_unit, logger):
        self.d_sleep_a = device_energy_ch['sleep_a']
        self.d_on_a = device_energy_ch['on_a']
        self.d_op_a = device_energy_ch['op_a']
        self.d_v = device_energy_ch['v']
        self.d_sleep_w = self.d_v * self.d_sleep_a
        self.d_on_w = self.d_v * self.d_on_a
        self.d_op_w = self.d_v * self.d_op_a
        self.d_off_w = 0.0
        self.d_off_a = 0.0
        self.d_none_w = 0.0
        self.d_none_a = 0.0

        self.r_sleep_a = radio_energy_ch['sleep_a']
        self.r_on_a = radio_energy_ch['on_a']
        self.r_rx_a = radio_energy_ch['rx_a']
        self.r_tx_a = radio_energy_ch['tx_a']
        self.r_v = radio_energy_ch['v']
        self.r_sleep_w = self.r_v * self.r_sleep_a
        self.r_on_w = self.r_v * self.r_on_a
        self.r_off_w = 0.0
        self.r_off_a = 0.0
        self.r_none_w = 0.0
        self.r_none_a = 0.0
        self.r_rx_w = self.r_v * self.r_rx_a
        self.r_tx_w = self.r_v * self.r_tx_a

        self.v_load_drop = v_load_drop
        self.second_in_unit = second_in_unit

        self.wh = 3600.0
        self.logger = logger


    def calculate_energy_usage(self, ini_state, state_table, dev_id, sim_time):
        sim_duration_ms = sim_time * self.second_in_unit
        mm = []
        # duration of given device/radio state & substate
        state_d = {
            'state': {STATE_SLEEP: 0, STATE_ON: 0, STATE_OFF: 0},
            'substate': {SUBSTATE_NONE: 0, D_SUBSTATE_OP: 0},
            'radio_state': {STATE_SLEEP: 0, STATE_ON: 0, STATE_OFF: 0},
            'radio_substate': {SUBSTATE_NONE: 0, R_SUBSTATE_RX: 0, R_SUBSTATE_TX: 0}
        }

        # keeping previous state to compare in the loop
        prev_state_ts = {'state': 0, 'substate': 0, 'radio_state': 0, 'radio_substate': 0}
        prev_state = {'state': ini_state.state, 'substate': ini_state.substate, 'radio_state': ini_state.radio_state,
                      'radio_substate': ini_state.radio_substate}
        
        # f = open(file_name, 'a')
        def _check_and_increase_state_d(state, state_type):
            # if the current state if different than the previous state
            if prev_state[state_type] is not getattr(state, state_type):
                state_d[state_type][prev_state[state_type]] += round(state.timestamp - prev_state_ts[state_type])
                if state_type.find('radio') > -1:
                    r_a = getattr(self, f'r_{prev_state[state_type].lower()}_a')
                    r_v = self.r_v
                    if f'r_{prev_state[state_type].lower()}' in [R_SUBSTATE_RX, R_SUBSTATE_TX]:
                        r_v = round(r_v - self.v_load_drop, 3)
                    mm.append((prev_state_ts[state_type], state.timestamp, r_a, r_v))
                else:
                    d_a = getattr(self, f'd_{prev_state[state_type].lower()}_a')
                    d_v = self.d_v
                    if f'd_{prev_state[state_type].lower()}_a' in [STATE_ON, D_SUBSTATE_OP]:
                        d_v = round(d_v - self.v_load_drop, 3)
                        print(d_v)
                    mm.append((prev_state_ts[state_type], state.timestamp, d_a, d_v))
                prev_state[state_type] = getattr(state, state_type)
                prev_state_ts[state_type] = state.timestamp

        last_ts = 0.0
        for ts, state in state_table.items():
            _check_and_increase_state_d(state, 'state')
            _check_and_increase_state_d(state, 'substate')
            _check_and_increase_state_d(state, 'radio_state')
            _check_and_increase_state_d(state, 'radio_substate')
            last_ts = ts

        # additional calculation for the last state
        if last_ts < sim_duration_ms:
            state = State(dev_id, STATE_SIM_END, SUBSTATE_SIM_END, STATE_SIM_END, SUBSTATE_SIM_END)
            state.set_timestamp(sim_duration_ms)
            _check_and_increase_state_d(state, 'state')
            _check_and_increase_state_d(state, 'substate')
            _check_and_increase_state_d(state, 'radio_state')
            _check_and_increase_state_d(state, 'radio_substate')

        energy_used = {'device': {}, 'radio': {}}
        total_energy_used = 0.0
        self.logger.always(sim_duration_ms, f'{bcolors.HEADER}{bcolors.UNDERLINE}Energy usage for dev_{dev_id}{bcolors.ENDC}')

        # for each state_type duration
        for state_type in state_d:
            for state_state in state_d[state_type]:
                # print(f'{state_type} {state_state}')
                duration = state_d[state_type][state_state]
                if state_type.find('radio') > -1:
                    joules = float(duration) / self.second_in_unit * getattr(self, f'r_{state_state.lower()}_w')
                    # joules1 = joules
                    # joules = float(duration) / self.second_in_unit * (getattr(self, f'r_{state_state.lower()}_a') * 
                    if state_state in [R_SUBSTATE_RX, R_SUBSTATE_TX] and self.v_load_drop > 0:
                        r_v = getattr(self, 'r_v') - self.v_load_drop
                        r_w = getattr(self, f'r_{state_state.lower()}_a') * r_v
                        # r_w_o = getattr(self, f'r_{state_state.lower()}_w')
                        joules = float(duration) / self.second_in_unit * r_w 
                        # joules2 = joules
                        # print(f'RADIO {state_state}: {joules1} <=> {joules2} [{r_w_o} <=> {r_w}]')

                    energy_used['radio'][state_state] = joules
                    info = f'\t{bcolors.HEADER}[RADIO][{state_type}][{state_state}]{bcolors.ENDC}'
                    self.logger.always(sim_duration_ms, f'{bcolors.HEADER}{info:40s}: {joules:.5f}J, {duration / self.second_in_unit}s / {round(sim_time, ROUND_N)}s{bcolors.ENDC}')
                    total_energy_used += joules
                    continue

                joules = float(duration) / self.second_in_unit * getattr(self, f'd_{state_state.lower()}_w')
                # joules1 = joules
                if state_state in [STATE_ON, D_SUBSTATE_OP] and self.v_load_drop > 0:
                    d_v = getattr(self, 'd_v') - self.v_load_drop
                    d_w = getattr(self, f'd_{state_state.lower()}_a') * d_v
                    # d_w_o = getattr(self, f'd_{state_state.lower()}_w')
                    joules = float(duration) / self.second_in_unit * d_w
                    # joules2 = joules
                    # print(f'DEVICE {state_state}: {joules1} <=> {joules2} [{d_w_o} <=> {d_w}]')

                energy_used['device'][state_state] = joules
                info = f'\t{bcolors.HEADER}[DEVICE][{state_type}][{state_state}]{bcolors.ENDC}'
                self.logger.always(sim_duration_ms, f'{bcolors.HEADER}{info:40s}: {joules:.5f}J, {duration / self.second_in_unit}s / {round(sim_time, ROUND_N)}s{bcolors.ENDC}')
                total_energy_used += joules

        # some additional conversions
        wh_to_j = 1 / self.wh
        total_j_to_wh = total_energy_used * wh_to_j
        total_mah = total_j_to_wh / self.d_v * 1000.0
        self.logger.always(
            sim_duration_ms,
            f'{bcolors.BOLD}{bcolors.HEADER}TOTAL ENERGY USED: {total_energy_used:.5f}J => {total_j_to_wh:.5f}Wh '
            f'=> {total_mah:.5f}mAh @ {self.d_v}V{bcolors.ENDC}\n'
        )
