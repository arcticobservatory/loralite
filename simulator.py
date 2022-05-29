from ctypes import util
import math
from logger import ONLY_ALWAYS, Logger, INFO, DEBUG, CRITICAL
from propagation_loss_model import LogDistancePropagationLossModel
from propagation_delay_model import ConstantSpeedPropagationDelayModel
from mobility import calculate_distance_matrix, get_distance, generate_coordinates, plot_coordinates, calculate_distance_simple
from copy import deepcopy
from utils import ROUND_N, bcolors, format_ms, get_random_true_false
from toa import ToA
from energy import Energy
from schedule import Scheduler
from state import State
from functools import reduce
import json
import argparse
from enum import Enum
from random import choice
from string import ascii_uppercase
from datetime import datetime
from sortedcontainers import SortedList, SortedDict
import traceback
import sys
from exceptions import SimException, ClockDriftException
from definitions import *
from typing import List

# sys.stdout = open('data/dcw.log','a')

logger = Logger(log_level=INFO, forced=False)
config = {}
DIR_PATH = ''
CDPPM_SEARCH_RANGE = 1000000
PPM = 1000000

# device/radio state
STATE_ON = 'ON'
STATE_OFF = 'OFF'
STATE_SLEEP = 'SLEEP'
STATE_SIM_END = 'END'
SUBSTATE_NONE = 'NONE'
SUBSTATE_SIM_END = 'END'

# device additional substate - while ON and not IDLE
D_SUBSTATE_OP = 'OP'

# radio additional substate
R_SUBSTATE_RX = 'RX'
R_SUBSTATE_TX = 'TX'

STATE = [STATE_ON, STATE_OFF, STATE_SLEEP]
D_SUBSTATE = [SUBSTATE_NONE, D_SUBSTATE_OP]
R_SUBSTATE = [SUBSTATE_NONE, R_SUBSTATE_RX, R_SUBSTATE_TX]

DEV_ARTHEMIS_NANO = 'arthemis_nano'
RAD_SX1276 = 'sx1276'
RAD_SX1262 = 'sx1262'

DEV_TYPE = Enum('Dev', 'PARENT CHILD')
LWAN_DEV_TYPE = Enum('Dev', 'GW END_DEV')

# In Europe, duty cycles are regulated by section 7.2.3 of the ETSI EN300.220 standard. 
# This standard defines the following sub-bands and their duty cycles:
#     g (863.0 – 868.0 MHz): 1%
#     g1 (868.0 – 868.6 MHz): 1%
#     g2 (868.7 – 869.2 MHz): 0.1%
#     g3 (869.4 – 869.65 MHz): 10%
#     g4 (869.7 – 870.0 MHz): 1%
LORA_BAND_868_0 = 868.0
LORA_BAND_868_7 = 868.7
LORA_BAND_869_4 = 869.4

SUBBANDS = {
    # start, end, duty, max Tx_dBm
    LORA_BAND_868_0: (868, 868.6, 0.01, 14),
    LORA_BAND_868_7: (868.7, 869.2, 0.001, 14),
    LORA_BAND_869_4: (869.4, 869.65, 0.1, 27)
}

SF_7 = 7
SF_8 = 8
SF_9 = 9
SF_10 = 10
SF_11 = 11
SF_12 = 12

CR_1 = 1  # 4/5
CR_2 = 2  # 4/6
CR_3 = 3  # 4/7
CR_4 = 4  # 4/8

RX_SENSITIVITY = {
    SF_7: -124,
    SF_8: -127,
    SF_9: -130,
    SF_10: -133,
    SF_11: -135,
    SF_12: -137
}

DR_PAYLOAD_SIZE = {
    0: 59,
    1: 59,
    2: 59,
    3: 123,
    4: 239,
    5: 250
}

TX_PARAMS = {
    'sf': SF_12,                         # spreading factor (12, 11, 10, 9, 8, 7)
    'cr': CR_4,                          # coding rate (1, 2, 3, 4)
    'bw': 125000,                        # bandwidth in HZ (125000, 250000)
    'dr': 0,                             # data rate index  (0, 1, 2, 3, 4, 5) - for each sf
    'preamble': 8,                       # preamble length
    'crc': 1,                            # crc enabled
    'hd': 1,                             # header disabled
    'ldro': 1,                           # low data rate optimization
    'max_payload': DR_PAYLOAD_SIZE[0],   # max payload size in Bytes (59, 59, 59, 123, 239, 250) - for each dr
    'band': LORA_BAND_868_0
}

LIST_OF_DEVICES = []
GW = None

# PROPAGATION_MODEL = LogDistancePropagationLossModel(4.12, 1, 7.7)
# PROPAGATION_MODEL = LogDistancePropagationLossModel(2.9, 5, 55.75, 8.9)
PROPAGATION_MODEL = LogDistancePropagationLossModel(2.9, 5, 55.75)
DELAY_MODEL = ConstantSpeedPropagationDelayModel()
TOA = ToA(TX_PARAMS['sf'], TX_PARAMS['bw'], TX_PARAMS['preamble'], TX_PARAMS['cr'], TX_PARAMS['ldro'], TX_PARAMS['crc'], TX_PARAMS['hd'], logger)

SIM_TIME = 0
SIU = 0 # Second In Unit
EVENT_LIST = SortedDict()
commandline = ''

def get_time_on_air(pkt_size):
    return TOA.get_time_on_air(pkt_size, SIM_TIME)

def add_event(dev_id, timestamp, f, *args, **kwargs):
    global EVENT_LIST
    if timestamp >= config['general']['sim_duration_ms']:
        return
    
    if timestamp not in EVENT_LIST:
        EVENT_LIST[timestamp] = []

    event = EventUnit(dev_id, timestamp, f, *args, **kwargs)
    EVENT_LIST[timestamp].append(event)


class EventUnit:
    def __init__(self, dev_id, timestamp, f, *args, **kwargs):
        self.dev_id = dev_id
        self.timestamp = timestamp
        self.func = f
        self.func_name = f.__name__
        self.args = args
        self.kwargs = kwargs
        self.expired = False

    def execute(self):
        global SIM_TIME, LIST_OF_DEVICES
        SIM_TIME = self.timestamp
        LIST_OF_DEVICES[self.dev_id].timestamp = SIM_TIME
        LIST_OF_DEVICES[self.dev_id].current_event_timestamp = SIM_TIME
        self.func(*self.args, **self.kwargs)
        LIST_OF_DEVICES[self.dev_id].previous_event_timestamp = SIM_TIME


class LoraBand:
    def __init__(self, subband, sf):
        params = SUBBANDS[subband]
        self.band = params[0]
        self.duty_cycle = params[2]
        self.tx_dbm = params[3]
        self.sf = sf

class Device:
    def __init__(self, nr, position, type):
        self.id = nr
        self.type = type
        self.position = position
        self.state: State = State(self.id)
        self.state_table = {}
        self.lora_band = LoraBand(TX_PARAMS['band'], TX_PARAMS['sf'])
        self.packets_sent = 0
        self.packets_received = 0
        self.sent_pkt_seq = -1
        self.last_pkt_rec_at = 0
        self.received_pkt_payload = None
        self.sent_pkt_payload = None
        self.bytes_sent = 0
        self.bytes_received = 0
        self.next_transmission_time = 0
        self.transmission_allowed_at = 0
        self.receive_buff = []
        self.event_list = SortedList()
        self.receive_events = SortedList()
        self.timestamp = 0
        self.cd_negative = get_random_true_false()
        self.clock_drift = config['general']['cdppm']
        self.clock_drift_total = 0
        self.clock_drift_timestamp_modifier = config['general']['cdppm'] - 1 + 3 * 60 * 1000 #3 minutes later
        self.clock_drift_modified_at = 0
        self.detect_preamble_ms = math.ceil(TOA.get_symbols_time() * SIU) #5 symbols required to detect the preamble
        self.tranmission_interval = 0
        self.sbs_active = False
        self.current_event_timestamp = 0
        self.last_event_timestamp = 0
        self.rx_active = False

        self.initial_state = deepcopy(self.state)
        self.config = {
            'switch_on_duration': config['device']['sch_on_duration_ms'],    # how long in s it takes to turn on device
            'switch_off_duration': config['device']['sch_off_duration_ms']   # how long in s it takes to turn off device
        }

        # saving initial Device state
        self._save_state()
        # scheduling an event at timestamp 0 that will print basic information about the Device
        add_event(self.id, 0, self._info)
        
        # # perform clock drift if specified in the simulation parameters
        # if config['general']['cdppm'] > 0:
        #     if self.type == DEV_TYPE.PARENT:
        #         add_event(self.id, self.clock_drift_timestamp_modifier + config['wcm']['first_op_at_s'] * SIU, self._perform_clock_drift)
        #     elif self.type == DEV_TYPE.CHILD:
        #         add_event(self.id, self.clock_drift_timestamp_modifier + config['wcl']['first_op_at_s'] * SIU, self._perform_clock_drift)

    def _perform_clock_drift(self):
        global CDPPM_SEARCH_RANGE

        CDPPM_SEARCH_RANGE = self.tranmission_interval
        # search_range_start = self.timestamp + config['general']['cdppm']
        search_range_start = self.timestamp + 1
        search_range_end = self.timestamp + config['general']['cdppm'] + CDPPM_SEARCH_RANGE
        
        # if self.tranmission_interval < 1000000:
        #     self.clock_drift_timestamp_modifier = math.ceil(self.tranmission_interval / 2)

        # no clock drift if device is already awake
        if self.state.state == STATE_ON:
            next_clock_drift = self.timestamp + self.clock_drift_timestamp_modifier
            logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}] is ON. Clock drift moved to {format_ms(next_clock_drift, SIU)}{bcolors.ENDC}')
            add_event(self.id, next_clock_drift, self._perform_clock_drift)
            log_drift_issue(self.id, self.timestamp)
            return

        drift_direction = ''
        drift_sign = 1
        clock_drift = 0
        
        if self.cd_negative:
            drift_sign = -1
        else:
            drift_direction = '+'


        event_list_slice = EVENT_LIST.irange(search_range_start, search_range_end)
        logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}] Clock drift search range: {format_ms(search_range_start, SIU)} --> {format_ms(search_range_end, SIU)}{bcolors.ENDC}')
        tmp_event_list = SortedDict()
        event_list_index = {}
        last_modified_timestamp = 0
        for timestamp in event_list_slice:
            time_to_next_event = timestamp - self.previous_event_timestamp
            clock_drift = math.ceil(time_to_next_event * self.clock_drift / PPM) * drift_sign
            last_modified_timestamp = timestamp
            for event in EVENT_LIST[timestamp]:
                drifted_timestamp = timestamp + clock_drift
                if event.dev_id == self.id:
                    if drifted_timestamp not in tmp_event_list:
                        tmp_event_list[drifted_timestamp] = []
                    event.timestamp = drifted_timestamp
                    logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}][{drift_direction}{clock_drift}ms][{format_ms(timestamp, SIU)} -> {format_ms(drifted_timestamp, SIU)}]: event({event.func_name}, [{event.args}][{event.kwargs}]){bcolors.ENDC}')
                    tmp_event_list[drifted_timestamp].append(event)
                    if timestamp not in event_list_index:
                        event_list_index[timestamp] = []
                    event_list_index[timestamp].append(EVENT_LIST[timestamp].index(event))
            
        for timestamp in event_list_index:
            event_list: List = EVENT_LIST.pop(timestamp)
            event_to_remain = []
            for event in event_list:
                if event_list.index(event) not in event_list_index[timestamp]:
                    event_to_remain.append(event)
            
            if len(event_to_remain) > 0:
                EVENT_LIST[timestamp] = event_to_remain

        for timestamp in tmp_event_list:
            if timestamp not in EVENT_LIST:
                EVENT_LIST[timestamp] = []

            for event in tmp_event_list[timestamp]:
                EVENT_LIST[timestamp].append(event)

        self.clock_drift_total += clock_drift
        # last_modified_timestamp = last_modified_timestamp if last_modified_timestamp > 0 else (timestamp + PPM)
        # self.clock_drift_modified_at = timestamp
        # add_event(self.id, last_modified_timestamp + self.clock_drift_timestamp_modifier, self._perform_clock_drift)
        # add_event(self.id, search_range_end, self._perform_clock_drift)
        # logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}] Next clock drift at {format_ms(last_modified_timestamp + self.clock_drift_timestamp_modifier, SIU)}{bcolors.ENDC}')
        # logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}] Next clock drift at {format_ms(search_range_end, SIU)}{bcolors.ENDC}')
        # logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}] Clock drift at {format_ms(search_range_end, SIU)}{bcolors.ENDC}')


    def _save_state(self):
        self.state_table[self.state.timestamp] = deepcopy(self.state)
        logger.debug(
            self.state.timestamp,
            f'SAVING STATE. d_state: {self.state.state}, d_substate: {self.state.substate}, '
            f'r_state: {self.state.radio_state}, r_substate: {self.state.radio_substate}'
        )

    def _change_device_state(self, state, substate=None):
        State.check_state(state)
        # no changes to the current state
        if self.state.state == state and self.state.substate == substate:
            return

        old_state = self.state.state
        self.state.state = state
        self.state.set_timestamp(self.timestamp)

        if substate is not None:
            State.check_device_substate(substate)
            old_substate = self.state.substate
            self.state.substate = substate
            logger.info(self.timestamp, f'dev_{self.id} device state: {old_state} => {state}, substate: {old_substate} => {substate}')

        if substate is None:
            logger.info(self.timestamp, f'dev_{self.id} device state: {old_state} => {state}, substate: {self.state.substate}')

        if state == STATE_SLEEP and not self.sbs_active:
            if config['general']['perform_clock_drift']:
                add_event(self.id, self.timestamp + 1, self._perform_clock_drift)
            # logger.info(self.timestamp, f'{bcolors.LIGHT_GRAY}[dev_{self.id}] Clock drift at {format_ms(self.timestamp + 1, SIU)}{bcolors.ENDC}')

        self._save_state()

    def _change_radio_state(self, state, substate=None):
        State.check_state(state)
        # no changes to the current state
        if self.state.radio_state == state and self.state.radio_substate == substate:
            return

        old_state = self.state.radio_state
        self.state.radio_state = state
        self.state.set_timestamp(self.timestamp)

        if substate is not None:
            State.check_radio_substate(substate)
            old_substate = self.state.radio_substate
            self.state.radio_substate = substate
            logger.info(self.timestamp, f'dev_{self.id} radio state: {old_state} => {state}, substate: {old_substate} => {substate}')

        if substate is None:
            logger.info(self.timestamp, f'dev_{self.id} radio state: {old_state} => {state}, substate: {self.state.substate}')

        self._save_state()

    def _scheduled_log(self, log_func, msg):
        log_func(self.timestamp, msg)

    def _info(self):
        logger.info(
            SIM_TIME,
            f'dev_{self.id}, \tTYPE:{type(self).__name__}, \tSTATE: {self.state.state}, '
            f'\tRADIO_STATE: {self.state.radio_state}, \tPOSITION: {self.position}'
        )

    def add_packet_to_buffer(self, packet):
        self.receive_buff.append(packet)
        add_event(self.id, self.timestamp, self._receive)

    def mark_preamble_detected(self, receive_time, packet):
        logger.info(self.timestamp, f'{bcolors.OKGREEN}PREAMBLE detected by dev_{self.id}!{bcolors.ENDC}')
        self.rx_active = True
        add_event(self.id, receive_time, self.add_packet_to_buffer, packet)

    def _can_receive(self, ts):
        if self.state.state in [STATE_OFF, STATE_SLEEP]:
            logger.info(ts, f'Device dev_{self.id} is either OFF or SLEEPING. Dropping packet')
            return False

        if self.state.radio_state in [STATE_OFF, STATE_SLEEP]:
            logger.info(ts, f'Device dev_{self.id} radio is either OFF or in sleep state. Dropping packet')
            return False

        if self.state.radio_substate is not R_SUBSTATE_RX:
            logger.info(ts, f'Device dev_{self.id} radio is not in RX substate. Dropping packet')
            return False

        # TODO: check later
        # self.rx_active = True
        # self.rx_active_at = ts

        return True

    def _send(self, sch_packet):
        if self.__check_send_conditions() is False:
            return

        packet_payload = '#'.join([str(sch_packet[x]) for x in sch_packet])
        packet = {'payload': f"{self.id}#{packet_payload}", 'rx_dbm': 0}
        send_interval = 0
        if self.type == DEV_TYPE.PARENT:
            send_interval = self.config['send_interval']

        time_on_air_ms = self.__calculate_transmission_times(packet, send_interval)
        if time_on_air_ms is False:
            self._change_radio_state(STATE_OFF, SUBSTATE_NONE)
            self._change_device_state(STATE_OFF, SUBSTATE_NONE)
            return

        self._change_device_state(STATE_ON, D_SUBSTATE_OP)
        self._change_radio_state(STATE_ON, R_SUBSTATE_TX)
        self.packets_sent += 1
        self.bytes_sent += len(packet['payload'].encode('utf8'))
        if sch_packet[PAYLOAD.CMD] == CMD_DATA_COLLECTION_REPLY:
            self.dc_bytes_sent += len(packet['payload'].encode('utf8'))

        if self.type == DEV_TYPE.PARENT and sch_packet[PAYLOAD.CMD] != CMD_SYNC:
            self.recv_count = 0
            self.expected_recv_count = len(Device._unpack_ids(sch_packet[PAYLOAD.DATA]))
            self.total_expected_recv_count += len(Device._unpack_ids(sch_packet[PAYLOAD.DATA]))
        self.sent_pkt_seq = sch_packet[PAYLOAD.SEQ]
        self.sent_pkt_payload = sch_packet

        logger.info(self.timestamp, f'{bcolors.OKBLUE}dev_{self.id} is sending packet with seq_nr {self.sent_pkt_seq}...{bcolors.ENDC}')

        for dev in LIST_OF_DEVICES:

            # skip itself
            if self.id == dev.id:
                continue

            if self.type is not DEV_TYPE.PARENT:
                if dev.type is not DEV_TYPE.PARENT:
                    continue

            distance = get_distance(self, dev)
            delay = DELAY_MODEL.get_delay(self, dev)
            rx_dbm, info = PROPAGATION_MODEL.calculate_rx_power(self, dev, self.lora_band.tx_dbm)
            logger.debug(self.timestamp, f'Propagation for dev_{dev.id}: {info}')
            dev_packet = deepcopy(packet)
            dev_packet['rx_dbm'] = rx_dbm

            logger.debug(
                self.timestamp,
                f'Params for dev_{dev.id}: txPower={self.lora_band.tx_dbm}dbm, rxPower={rx_dbm}dbm, '
                f'distance={distance}m, delay=+{round(delay * 1000000, ROUND_N)}ns'
            )

            if dev._can_receive(self.timestamp):
                receive_time = self.timestamp + time_on_air_ms
                preamble_time = self.timestamp + self.detect_preamble_ms

                # add_event(dev.id, receive_time, dev.add_packet_to_buffer, dev_packet)
                add_event(dev.id, preamble_time, dev.mark_preamble_detected, receive_time, dev_packet)
            
        add_event(self.id, self.timestamp + time_on_air_ms, self._scheduled_log, logger.info, f'{bcolors.OKBLUE}...dev_{self.id} has finished sending the message.{bcolors.ENDC}')
        add_event(
            self.id,
            self.timestamp + time_on_air_ms, self._scheduled_log, logger.info,
            f'{bcolors.BMAGNETA}Next allowed transmission time for dev_{self.id}: {format_ms(self.transmission_allowed_at, SIU)}{bcolors.ENDC}'
        )

        if self.type is DEV_TYPE.PARENT:
            add_event(
                self.id,
                self.timestamp + time_on_air_ms, self._scheduled_log, logger.info,
                f'{bcolors.BMAGNETA}Next scheduled transmission time for dev_{self.id}: {format_ms(self.next_transmission_time, SIU)}{bcolors.ENDC}'
            )

        # here is the difference between commands
        # - sync works as before
        # - discovery and data collection have to have listening window

        if self.type == DEV_TYPE.PARENT and sch_packet[PAYLOAD.CMD] == CMD_SYNC:
            self._end_sync(time_on_air_ms)
            return 

        if self.type == DEV_TYPE.PARENT:
            receive_window = config['wcm']['dc_window_s']
            color = bcolors.BCYAN
            cmd_name = 'DATA COLLECTION'
            if sch_packet[PAYLOAD.CMD] == CMD_DISC:
                receive_window = config['wcm']['disc_window_s']
                color = bcolors.BBLUE
                cmd_name = 'DISC'

            add_event(self.id, self.timestamp + time_on_air_ms, self._scheduled_log, logger.info, f'{color}Waiting for {cmd_name} responses from devices with ID: {sch_packet[PAYLOAD.DATA]}{bcolors.ENDC}')
            add_event(self.id, self.timestamp + time_on_air_ms + config['radio']['mode_change_ms'], self._change_radio_state, STATE_ON, R_SUBSTATE_RX)
            self.receive_window = {
                'start': self.timestamp + time_on_air_ms + config['radio']['mode_change_ms'],
                'end': self.timestamp + time_on_air_ms + config['radio']['mode_change_ms'] + receive_window * SIU}
            add_event(self.id, self.receive_window['end'], self._check_if_received_all)
            # add_event(self.id, self.timestamp + time_on_air_ms, self._scheduled_log, logger.info, f'{color}RECEIVE WINDOW: {self.receive_window["start"]:,} - {self.receive_window["end"]:,}{bcolors.ENDC}')
            add_event(self.id, self.timestamp + time_on_air_ms, self._scheduled_log, logger.info, f'{color}RECEIVE WINDOW: {format_ms(self.receive_window["start"], SIU)} - {format_ms(self.receive_window["end"], SIU)}{bcolors.ENDC}')

            # self._continue_receive()
            return 

        self._end_receive(time_on_air_ms)

    def __check_send_conditions(self):
        # # it should not happen
        # # TODO: what do we do it that case
        # if self.type is DEV_TYPE.PARENT and self.clock_drift >= 0 and self.next_transmission_time > SIM_TIME:
        #     logger.warning(
        #         self.timestamp,
        #         f'There is something wrong with the schedule. NTT[{self.next_transmission_time}] '
        #         f'>= SIM_TIME[{SIM_TIME}]'
        #     )
        #     return False

        if self.state.state is not STATE_ON:
            logger.warning(
                self.timestamp,
                f'Device can\'t send a message if it is off'
            )
            return False

        if self.state.radio_state is not STATE_ON:
            logger.warning(
                self.timestamp,
                f'Device can\'t send a message if its radio is off'
            )
            return False

        if self.transmission_allowed_at > SIM_TIME:
            logger.warning(
                self.timestamp,
                f'{bcolors.WARNING}dev_{self.id} is not allowed to transmitt before {format_ms(self.next_transmission_time, SIU)}{bcolors.ENDC}'
                # f'{int((self.next_transmission_time - self.next_transmission_time % SIU) / SIU):,}' \
                # f'.{self.next_transmission_time % SIU}s{bcolors.ENDC}'
            )
            return False

    def __calculate_transmission_times(self, packet, send_interval):
        payload_size = len(packet['payload'].encode('utf8'))
        if payload_size > TX_PARAMS['max_payload']:
            logger.error(
                SIM_TIME,
                f'Packet payload is too big ({payload_size}B) for SF{TX_PARAMS["sf"]} and BW {TX_PARAMS["bw"]}Hz'
            )
            raise SimException()

        time_on_air = get_time_on_air(len(packet['payload'].encode('utf8')))
        time_on_air_ms = time_on_air * SIU

        next_transmission_delay = math.ceil(time_on_air_ms / self.lora_band.duty_cycle - time_on_air_ms)
        self.transmission_allowed_at = self.timestamp + next_transmission_delay
        if self.type == DEV_TYPE.CHILD:
            self.next_transmission_time = self.timestamp + next_transmission_delay
            return math.ceil(time_on_air_ms)

        # GW part. We need to check if config[wcl][send_interval] is within allowed Duty Cycle
        self.next_transmission_time = self.timestamp + send_interval * SIU
        if self.type == DEV_TYPE.PARENT and next_transmission_delay > send_interval * SIU:
            logger.info(self.timestamp, f"Send interval ({send_interval * SIU}ms) is smaller than allowed by the duty cycle ({next_transmission_delay}ms) for selected LoRa parameters!")
            logger.info(self.timestamp, "Please fix the send interval and run the simulation again")

            raise SimException()        

        return math.ceil(time_on_air_ms)

    @staticmethod
    def _unpack_ids(id_string):
        def _get_ids(part):
            id_r = part.split(':')
            id_r = [int(x) for x in id_r]
            if len(id_r) == 1:
                return id_r
            if len(id_r) == 2:
                return [x for x in range(id_r[0], id_r[len(id_r) - 1] + 1)]

        ids = []
        parts = id_string.split(',')
        if len(parts) == 2:
            ids += _get_ids(parts[0])
            ids += _get_ids(parts[1])
        if len(parts) == 1:
            ids = _get_ids(parts[0])

        return ids

class LoRaLitEParentNode(Device):
    def __init__(self, nr, position):
        self.nr_of_retransmissions = 0
        self.packet_schedule = {}
        self.receive_window = {}
        self.expected_recv_count = 0
        self.total_expected_recv_count = 0
        self.recv_count = 0
        self.energy = Energy(
            config['energy']['device'][config['wcm']['device_type']], 
            config['energy']['radio'][config['wcm']['radio_type']],
            config['energy']['v_load_drop'],
            SIU,
            logger
        )

        super().__init__(nr, position, DEV_TYPE.PARENT)
        self.config['send_interval'] = config['wcm']['send_interval_s']
        self.config['send_delay'] = config['wcm']['send_delay_s'] * SIU
        self.tranmission_interval = self.config['send_interval'] * SIU

        add_event(self.id, self.timestamp + config['wcm']['first_op_at_s'] * SIU - config['device']['sch_on_duration_ms'], 
            self._change_device_state, STATE_ON
        )
        add_event(self.id, self.timestamp + config['wcm']['first_op_at_s'] * SIU - config['device']['sch_on_duration_ms'], 
            self._change_radio_state, STATE_ON
        )
        add_event(self.id, self.timestamp + config['wcm']['first_op_at_s'] * SIU, self._execute_packet_schedule)
       
    def set_sending_interval_s(self, interval):
        self.config['send_interval'] = interval

    def set_sending_delay(self, delay):
        self.config['send_delay'] = delay

    def set_nr_of_retransmissions(self, number):
        self.nr_of_retransmissions = number

    def _execute_packet_schedule(self):
        def _shorten_id_list(payload):
            def _get_start_end(id_list):
                start = f'{id_list[0]}'
                end = f':{id_list[len(id_list) - 1]}' if len(id_list) > 1 else ''
                return f'{start}{end}'

            ids = payload.split(',')
            ids = [int(x) for x in ids]
            curr = ids[0] 
            temp = [] 
            res = [] 
            for ele in ids: 
                # if curr value greater than split 
                if ele < curr: 
                    res.append(temp) 
                    curr = ele 
                    temp = [] 
                temp.append(ele) 
            res.append(temp)
            if len(res) == 1:
                short = _get_start_end(res[0])
            if len(res) == 2:
                short = f'{_get_start_end(res[0])},{_get_start_end(res[1])}'

            return short

        pkt_seq = self.sent_pkt_seq + 1
        if len(self.packet_schedule) == 0:
            packet = {PAYLOAD.SEQ: pkt_seq, PAYLOAD.CMD: CMD_SYNC, PAYLOAD.DATA: self.config['send_interval'], PAYLOAD.NR_OF_RET: 0}
        else:
            packet = self.packet_schedule[pkt_seq]
            if packet[PAYLOAD.CMD] != CMD_SYNC:
                packet[PAYLOAD.DATA] = _shorten_id_list(packet[PAYLOAD.DATA])
            # logger.info(self.timestamp, f'[{pkt_seq}][{packet[PAYLOAD.CMD]}]: {packet[PAYLOAD.DATA]}')
            del self.packet_schedule[pkt_seq]

        self._send(packet)

    def _send(self, sch_packet):
        super()._send(sch_packet)

    def _receive(self):
        if self.state.state is STATE_OFF:
            return

        if self.state.radio_state is STATE_OFF:
            return

        if len(self.receive_buff) > 1:
            raise RuntimeError('There should be exactly 1 packet in the receive buffer! Something is wrong: ', self.receive_buff)

        packet = self.receive_buff.pop(0)
        sensitivity = RX_SENSITIVITY[self.lora_band.sf]

        # dropping packet if its sensitivity is below receiver sensitivity
        if packet['rx_dbm'] < sensitivity:
            logger.info(
                self.timestamp,
                f'Packet dropped by dev_{self.id}. Packet rx_dbm {packet["rx_dbm"]} dBm is below receiver sensitivity '
                f'{sensitivity} dBm.'
            )
            return

        self.packets_received += 1
        self.recv_count += 1
        self.bytes_received += len(packet['payload'].encode('utf8'))
        logger.info(self.timestamp, f'{bcolors.OKGREEN}Packet received by dev_{self.id}: {packet["payload"]} with RSSI: {packet["rx_dbm"]} dBm{bcolors.ENDC}')

        if self.recv_count == self.expected_recv_count:
            # we keep turn off the radio when we have received all expected responses
            add_event(self.id, self.timestamp + self.config['switch_off_duration'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)
            # we can turn off the device as well
            add_event(self.id, self.timestamp + self.config['switch_off_duration'], self._change_device_state, STATE_SLEEP, SUBSTATE_NONE)
            self._end_send_receive()

    def _end_sync(self, time_on_air_ms):
        # we keep the radio on as long as ToA duration of the packet
        add_event(self.id, self.timestamp + time_on_air_ms, self._change_radio_state, STATE_OFF, SUBSTATE_NONE)
        # we can turn off the device when packet is sent
        add_event(self.id, self.timestamp + time_on_air_ms + self.config['switch_off_duration'], self._change_device_state, STATE_SLEEP, SUBSTATE_NONE)
        self._end_send_receive()

    def _end_send_receive(self):
        # we need to prepare schedule for the next transmission
        add_event(self.id, self.next_transmission_time - self.config['switch_on_duration'] + self.config['send_delay'], self._change_device_state, STATE_ON, SUBSTATE_NONE)      
        add_event(self.id, self.next_transmission_time - self.config['switch_on_duration'] + self.config['send_delay'], self._change_radio_state, STATE_ON, SUBSTATE_NONE)
        add_event(self.id, self.next_transmission_time + self.config['send_delay'], self._execute_packet_schedule)

    def _check_if_received_all(self):
        if self.state.state is STATE_SLEEP:
            return

        if self.state.radio_state is STATE_OFF:
            return

        #if the device is still up it means that it did not receive all expected responses :(
        if self.recv_count < self.expected_recv_count:
            logger.info(self.timestamp, f'{bcolors.WARNING}dev_{self.id} received only {self.recv_count} / {self.expected_recv_count}.{bcolors.ENDC}')
            if config['general']['quit_on_failure']:
                raise ClockDriftException(f'dev_{self.id} received only {self.recv_count} / {self.expected_recv_count}.')

        add_event(self.id, self.timestamp + self.config['switch_off_duration'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)
        add_event(self.id, self.timestamp + self.config['switch_off_duration'], self._change_device_state, STATE_SLEEP, SUBSTATE_NONE)
        self._end_send_receive()

class LoRaLitEChildNode(Device):
    def __init__(self, nr, position):
        self.next_expected_transmission_time = 0.0
        self.packet_delay = 0
        self.timestamp = 0
        self.sync = 0
        self.d = 0
        self.dc = 0
        self.dc_bytes_sent = 0
        self.sbs = config['wcl']['sleep_before_slot']
        self.rx_active_at = 0
        self.energy = Energy(
            config['energy']['device'][config['wcl']['device_type']], 
            config['energy']['radio'][config['wcl']['radio_type']],
            config['energy']['v_load_drop'],
            SIU,
            logger
        )

        super().__init__(nr, position, DEV_TYPE.CHILD)
        self.config['wait_before'] = math.ceil(config['wcl']['guard_time_ms'] / 2)
        self.config['wait_after'] = math.ceil(config['wcl']['guard_time_ms'] / 2) + self.detect_preamble_ms
        self.config['guard_time'] = config['wcl']['guard_time_ms']
        self.config['op_duration'] = config['wcl']['op_duration_ms']

        add_event(self.id, self.timestamp + config['wcl']['first_op_at_s'] * SIU + self.config['switch_on_duration'], self._change_device_state, STATE_ON, SUBSTATE_NONE)
        add_event(self.id, self.timestamp + config['wcl']['first_op_at_s'] * SIU + self.config['switch_on_duration'], self._change_radio_state, STATE_ON, R_SUBSTATE_RX)        

    def _send(self, packet):
        super()._send(packet)
        self.sbs_active = False

    def _receive(self):
        if self.state.state is STATE_OFF:
            return

        if self.state.radio_state is STATE_OFF:
            return

        if self.state.radio_substate is not R_SUBSTATE_RX:
            logger.info(self.timestamp, f'{bcolors.FAIL}dev_{self.id} can not receive because radio not in {R_SUBSTATE_RX} mode!{bcolors.ENDC}')
            return

        if len(self.receive_buff) > 1:
            raise RuntimeError('There should be exactly 1 packet in the receive buffer! Something is wrong.')

        self.rx_active = False
        packet = self.receive_buff.pop(0)
        sensitivity = RX_SENSITIVITY[self.lora_band.sf]

        # dropping packet if its sensitivity is below receiver sensitivity
        if packet['rx_dbm'] < sensitivity:
            logger.info(
                self.timestamp,
                f'Packet dropped by dev_{self.id}. Packet rx_dbm {packet["rx_dbm"]} dBm is below receiver sensitivity '
                f'{sensitivity} dBm.'
            )
            return

        self.packets_received += 1
        self.bytes_received += len(packet['payload'].encode('utf8'))
        logger.info(self.timestamp, f'{bcolors.OKGREEN}Packet received by dev_{self.id}: {packet["payload"]} with RSSI: {packet["rx_dbm"]} dBm{bcolors.ENDC}')
        time_on_air = get_time_on_air(len(packet['payload'].encode('utf8')))
        time_on_air_ms = math.ceil(time_on_air * SIU)
        self.last_pkt_rec_at = self.timestamp - time_on_air_ms

        payload = packet['payload'].split('#')
        self.received_pkt_payload = {
            PAYLOAD.SEQ: payload[PAYLOAD.SEQ.value - 1], 
            PAYLOAD.CMD: payload[PAYLOAD.CMD.value - 1], 
            PAYLOAD.DATA: payload[PAYLOAD.DATA.value - 1], 
            PAYLOAD.NR_OF_RET: payload[PAYLOAD.NR_OF_RET.value - 1],
            PAYLOAD.RSSI: packet['rx_dbm']
        }
        
        if self.received_pkt_payload[PAYLOAD.CMD] is CMD_SYNC:
            self.sync += 1
            new_delay = int(self.received_pkt_payload[PAYLOAD.DATA])
            self.packet_delay = new_delay * SIU
            self.tranmission_interval = new_delay * SIU

        
        next_transmission_time = self.timestamp + self.packet_delay - time_on_air_ms
        self.next_expected_transmission_time = self.timestamp + math.ceil(time_on_air * SIU / self.lora_band.duty_cycle - time_on_air * SIU) - time_on_air_ms
        
        if next_transmission_time > self.next_expected_transmission_time:
            self.next_expected_transmission_time = next_transmission_time
        
        logger.info(
            self.timestamp, f'{bcolors.BWHITEDARK}Next possible for dev_{self.id} packet arrival time: {format_ms(self.next_expected_transmission_time, SIU)}{bcolors.ENDC}'
        )

        # case where device has to respond to GW
        if self.received_pkt_payload[PAYLOAD.CMD] is not CMD_SYNC:
            received_pkt_data = Device._unpack_ids(self.received_pkt_payload[PAYLOAD.DATA])
            if self.id not in received_pkt_data:
                self._end_receive(self.config['op_duration'])
                return

            if self.received_pkt_payload[PAYLOAD.CMD] == CMD_DISC:
                self.d += 1
                current_cmd = CMD_DISC_REPLY
                data = self.received_pkt_payload[PAYLOAD.RSSI]
                max_toa_ms = math.ceil(get_time_on_air(len(f'{len(LIST_OF_DEVICES)}#{config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{RX_SENSITIVITY[TX_PARAMS["sf"]]}.00#0'.encode('utf8'))) * SIU)
        
            if self.received_pkt_payload[PAYLOAD.CMD] == CMD_DATA_COLLECTION:
                self.dc += 1
                current_cmd = CMD_DATA_COLLECTION_REPLY
                max_toa_ms = math.ceil(get_time_on_air(config['lora']['payload_size']) * SIU)

                tmp_pkt_len = len(f'{self.id}#{self.sent_pkt_seq + 1}#{current_cmd}##0')
                if config['lora']['bytes_to_send'] > 0:
                    to_fill = config['lora']['payload_size'] - tmp_pkt_len
                    if self.dc_bytes_sent + to_fill + tmp_pkt_len > config['lora']['bytes_to_send']:
                        to_fill = config['lora']['bytes_to_send'] - self.dc_bytes_sent - tmp_pkt_len 
                    data = ''.join(choice(ascii_uppercase) for i in range(to_fill))
                else:
                    data = ''.join(choice(ascii_uppercase) for i in range(config['lora']['payload_size'] - tmp_pkt_len))

            self.sent_pkt_seq += 1
            packet = {PAYLOAD.SEQ: self.sent_pkt_seq, PAYLOAD.CMD: current_cmd, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: 0}
            packet_timeslot = config['wcl']['reply_gt_ms'] + max_toa_ms + config['radio']['mode_change_ms']

            slot_nr = received_pkt_data.index(self.id)
            packet_ts = self.timestamp + (packet_timeslot * slot_nr)
            if slot_nr == 0:
                packet_ts += config['wcl']['reply_gt_ms'] - config['radio']['mode_change_ms']

            if self.sbs and self.received_pkt_payload[PAYLOAD.CMD] == CMD_DATA_COLLECTION:
                # if waiting (idle) time is bigger than Guard Time + switch on + switch off + radio mode_change the device goes to sleep to conserve energy
                # guarded_period_ms = 2 * max_toa_ms + self.config['switch_off_duration'] + self.config['switch_on_duration']
                guarded_period_ms = max_toa_ms + config["wcl"]["reply_gt_ms"] + self.config['switch_off_duration'] + self.config['switch_on_duration']
                if packet_ts > self.timestamp + guarded_period_ms:
                    self.sbs_active = True
                    add_event(self.id, self.timestamp + self.config['switch_off_duration'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)
                    add_event(self.id, self.timestamp + self.config['switch_off_duration'], self._change_device_state, STATE_SLEEP, SUBSTATE_NONE)

                    # we need to wake-up the device before the response slot time
                    wakeup_ts = packet_ts - guarded_period_ms
                    add_event(self.id, wakeup_ts, self._change_device_state, STATE_ON, SUBSTATE_NONE)
                    add_event(self.id, wakeup_ts, self._change_radio_state, STATE_ON, R_SUBSTATE_RX)

                    sleep_ms = packet_ts - (self.timestamp + guarded_period_ms)
                    logger.info(self.timestamp, f'{bcolors.MAGNETA}Response timeslot for dev_{self.id}: {format_ms(packet_ts, SIU)} -> ' \
                        f'{format_ms(packet_ts + max_toa_ms + config["wcl"]["reply_gt_ms"], SIU)} [S: {sleep_ms}ms W_at:{format_ms(wakeup_ts, SIU)}]{bcolors.ENDC}')
                else:
                    logger.info(self.timestamp, f'{bcolors.MAGNETA}Response timeslot for dev_{self.id}[{slot_nr}]: {format_ms(packet_ts, SIU)} -> {format_ms(packet_ts + max_toa_ms + config["wcl"]["reply_gt_ms"], SIU)}{bcolors.ENDC}')
            else:
                logger.info(self.timestamp, f'{bcolors.MAGNETA}Response timeslot for dev_{self.id}[{slot_nr}]: {format_ms(packet_ts, SIU)} -> {format_ms(packet_ts + max_toa_ms + config["wcl"]["reply_gt_ms"], SIU)}{bcolors.ENDC}')


            add_event(self.id, packet_ts + config['radio']['mode_change_ms'], self._change_radio_state, STATE_ON, R_SUBSTATE_TX)            
            add_event(self.id, packet_ts + config['radio']['mode_change_ms'], self._send, packet)            

            return

        self._end_receive(self.config['op_duration'])

    def _end_receive(self, op_duration):
        # we got the packet so we can turn off radio
        add_event(self.id, self.timestamp + op_duration + self.config['switch_off_duration'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)

        # device needs to execute some jobs related to the received call but after the given operational time it can
        # be turned off
        add_event(self.id, self.timestamp + op_duration + self.config['switch_off_duration'], self._change_device_state, STATE_SLEEP, SUBSTATE_NONE)

        # we need to turn on the device so it can potentially receive the next wake-up call around the next expected
        # transmission time
        next_schedule_timestamp = math.floor(self.next_expected_transmission_time - self.config['wait_before'])
        
        add_event(self.id, next_schedule_timestamp - self.config['switch_on_duration'], self._change_device_state, STATE_ON, SUBSTATE_NONE)
        add_event(self.id, next_schedule_timestamp - self.config['switch_on_duration'], self._change_radio_state, STATE_ON, SUBSTATE_NONE)
        add_event(self.id, next_schedule_timestamp, self._change_radio_state, STATE_ON, R_SUBSTATE_RX)
        add_event(self.id, next_schedule_timestamp + self.config['guard_time'] + self.detect_preamble_ms, self.__check_if_received)

        guard_time_start = next_schedule_timestamp
        guard_time_end = next_schedule_timestamp + self.config['guard_time']
        guard_time_end_with_preamble = next_schedule_timestamp + self.config['guard_time'] + self.detect_preamble_ms
        logger.info(
            self.timestamp, f'{bcolors.BWHITEDARK}[dev_{self.id}] next guard time: <{format_ms(guard_time_start, SIU)} : {format_ms(guard_time_end, SIU)} [{format_ms(guard_time_end_with_preamble, SIU)}]>{bcolors.ENDC}'
        )

    def __check_if_received(self):
        if self.last_pkt_rec_at == 0.0:
            return

        # TODO: check later
        # if self.rx_active and self.rx_active_at < self.timestamp:
        #     self.rx_active = False
        #     return

        if self.rx_active:
            return

        interval_since_last_pkt = self.timestamp - self.last_pkt_rec_at
        # device did not receive a packet within an expected receive window
        if interval_since_last_pkt > (self.config['guard_time'] + self.detect_preamble_ms):
            self.rx_active = False
            # if interval_since_last_pkt > self.packet_delay:
            nr_of_lost_pkts = math.floor(interval_since_last_pkt / self.packet_delay)
            self.next_expected_transmission_time = self.last_pkt_rec_at + (nr_of_lost_pkts + 1) * self.packet_delay
            logger.info(
                self.timestamp, 
                f'{bcolors.WARNING}dev_{self.id} did not receive expected packet!{bcolors.ENDC} ' \
                f'{bcolors.BWHITEDARK}Next possible for dev_{self.id} packet arrival time: {format_ms(self.next_expected_transmission_time, SIU)}{bcolors.ENDC}'
                )
            if config['general']['quit_on_failure']:
                raise ClockDriftException(f'{bcolors.WARNING}dev_{self.id} did not receive expected packet!{bcolors.ENDC}')

            self._end_receive(self.config['op_duration'])

        return

class LoRaWANGateway(Device):
    def __init__(self, nr, position):
        self.nr_of_retransmissions = 0
        self.energy = Energy(
            config['energy']['device'][config['lwangw']['device_type']], 
            config['energy']['radio'][config['lwangw']['radio_type']],
            config['energy']['v_load_drop'],
            SIU,
            logger
        )

        super().__init__(nr, position, LWAN_DEV_TYPE.GW)

        self._change_device_state(STATE_ON)
        self._change_radio_state(STATE_ON, R_SUBSTATE_RX)

    def _receive(self):
        if self.state.state is STATE_OFF:
            return

        if self.state.radio_state is STATE_OFF:
            return

        if len(self.receive_buff) > 1:
            raise RuntimeError('There should be exactly 1 packet in the receive buffer! Something is wrong.')
        
        packet = self.receive_buff.pop(0)
        sensitivity = RX_SENSITIVITY[self.lora_band.sf]

        # dropping packet if its sensitivity is below receiver sensitivity
        if packet['rx_dbm'] < sensitivity:
            logger.info(
                self.timestamp,
                f'Packet dropped by dev_{self.id}. Packet rx_dbm {packet["rx_dbm"]} dBm is below receiver sensitivity '
                f'{sensitivity} dBm.'
            )
            return

        self.packets_received += 1
        self.bytes_received += len(packet['payload'].encode('utf8'))
        logger.info(self.timestamp, f'{bcolors.OKGREEN}Packet received by GW_{self.id}: {packet["payload"]} with RSSI: {packet["rx_dbm"]} dBm{bcolors.ENDC}')


class LoRaWANEndDevice(Device):
    def __init__(self, nr, position):
        self.packet_schedule = {}
        self.rx1 = {}
        self.rx2 = {}
        self.rx1_timeout = False
        self.rx2_timeout = False
        self.last_packet = False
        self.energy = Energy(
            config['energy']['device'][config['lwaned']['device_type']], 
            config['energy']['radio'][config['lwaned']['radio_type']],
            config['energy']['v_load_drop'],
            SIU,
            logger
        )

        super().__init__(nr, position, LWAN_DEV_TYPE.END_DEV)
        self.config['send_interval'] = config['lwaned']['send_interval_s'] * SIU
        self.config['send_delay'] = config['lwaned']['send_delay_s'] * SIU
        self.config['rx_window'] = math.ceil(TOA.get_symbols_time() * SIU) #5 symbols required to detect the preamble

        first_op_at_s = config['lwaned']['first_op_at_s']
        first_op_at_s += first_op_at_s + config['lwaned']['separation_s'] * self.id - 1
        first_op_at_ms = first_op_at_s * SIU

        print(f'RX1 and RX2 size: {self.detect_preamble_ms} ms')

        add_event(self.id, self.timestamp + first_op_at_ms - config['device']['sch_on_duration_ms'], self._change_device_state, STATE_ON)
        add_event(self.id, self.timestamp + first_op_at_ms - config['device']['sch_on_duration_ms'], self._change_radio_state, STATE_ON)
        add_event(self.id, self.timestamp + first_op_at_ms, self._execute_packet_schedule)
       

    def set_sending_interval_s(self, interval):
        self.config['send_interval'] = interval

    def _execute_packet_schedule(self):
        pkt_seq = self.sent_pkt_seq + 1
        if len(self.packet_schedule) == 0:
            return
        else:
            packet = self.packet_schedule[pkt_seq]
            del self.packet_schedule[pkt_seq]

            if len(self.packet_schedule) == 0:
                self.last_packet = True

        self._send(packet)

    def _send(self, sch_packet):
        packet = {'payload': sch_packet[PAYLOAD.DATA], 'rx_dbm': 0}
        time_on_air_ms = math.ceil(get_time_on_air(len(sch_packet[PAYLOAD.DATA])) * SIU)
        next_transmission_delay = math.ceil(time_on_air_ms / self.lora_band.duty_cycle - time_on_air_ms)
        self.next_transmission_time = self.timestamp + next_transmission_delay

        self._change_device_state(STATE_ON, D_SUBSTATE_OP)
        self._change_radio_state(STATE_ON, R_SUBSTATE_TX)
        self.packets_sent += 1
        self.bytes_sent += len(packet['payload'].encode('utf8'))
        self.sent_pkt_seq = sch_packet[PAYLOAD.SEQ]
        self.sent_pkt_payload = sch_packet

        logger.info(self.timestamp, f'{bcolors.OKBLUE}dev_{self.id} is sending packet with seq_nr {self.sent_pkt_seq}...{bcolors.ENDC}')

        distance = get_distance(self, GW)
        delay = DELAY_MODEL.get_delay(self, GW)
        rx_dbm, info = PROPAGATION_MODEL.calculate_rx_power(self, GW, self.lora_band.tx_dbm)
        logger.debug(self.timestamp, f'Propagation for GW_{GW.id}: {info}')
        dev_packet = deepcopy(packet)
        dev_packet['rx_dbm'] = rx_dbm

        logger.debug(
            self.timestamp,
            f'Params for GW_{GW.id}: txPower={self.lora_band.tx_dbm}dbm, rxPower={rx_dbm}dbm, '
            f'distance={distance}m, delay=+{round(delay * 1000000, ROUND_N)}ns'
        )

        receive_time = int(round(self.timestamp + time_on_air_ms, 0))
        add_event(GW.id, receive_time, GW.add_packet_to_buffer, dev_packet)

        add_event(self.id, self.timestamp + time_on_air_ms, self._scheduled_log, logger.info, f'{bcolors.OKBLUE}...dev_{self.id} has finished sending the message.{bcolors.ENDC}')
        add_event(self.id, 
            self.timestamp + time_on_air_ms, self._scheduled_log, logger.info,
            f'{bcolors.BMAGNETA}Next allowed transmission time for dev_{self.id}: {format_ms(self.next_transmission_time, SIU)}{bcolors.ENDC}'
                # f'{int((self.next_transmission_time - self.next_transmission_time % SIU) / SIU):,}' \
                # f'.{self.next_transmission_time % SIU}s'
        )

        if self.timestamp + self.config['send_interval'] < self.next_transmission_time:
            raise RuntimeError('Send interval is too small for dev_{dev.id}!') 

        # we keep the radio in TX mode as long as ToA duration of the packet
        add_event(self.id, self.timestamp + time_on_air_ms + config['radio']['mode_change_ms'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)
        add_event(self.id, self.timestamp + time_on_air_ms + SIU - config['radio']['mode_change_ms'], self._change_radio_state, STATE_ON, R_SUBSTATE_RX)

        self.rx1 = {
            'start': self.timestamp + time_on_air_ms + SIU,
            'end': self.timestamp + time_on_air_ms + SIU + self.config['rx_window']}

        add_event(self.id, self.rx1['end'] + config['radio']['mode_change_ms'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)

        self.rx2 = {
            'start': self.rx1['end'] + SIU,
            'end': self.rx1['end'] + SIU + self.config['rx_window']}

        add_event(self.id, self.rx2['start'] - config['radio']['mode_change_ms'], self._change_radio_state, STATE_ON, R_SUBSTATE_RX)
        add_event(self.id, self.rx2['end'] + config['device']['sch_off_duration_ms'], self._change_radio_state, STATE_OFF, SUBSTATE_NONE)
        add_event(self.id, self.rx2['end'] + config['device']['sch_off_duration_ms'], self._change_device_state, STATE_SLEEP, SUBSTATE_NONE)

        if not self.last_packet:
            # we need to prepare schedule for the next transmission
            add_event(self.id, self.timestamp + self.config['send_interval'] - self.config['switch_on_duration'] + self.config['send_delay'], self._change_device_state, STATE_ON, SUBSTATE_NONE)            
            add_event(self.id, self.timestamp + self.config['send_interval'] - self.config['switch_on_duration'] + self.config['send_delay'], self._change_radio_state, STATE_ON, SUBSTATE_NONE)
            add_event(self.id, self.timestamp + self.config['send_interval'] + self.config['send_delay'], self._execute_packet_schedule)

        self.rx1_timeout = False
        self.rx2_timeout = False

        # we schedule _receive() 1s after transmission (LoRaWAN specification)
        # add_event(self.id, self.rx1['start'], self._receive)

    # def _receive(self):
    #     if self.state.state is STATE_OFF:
    #         return

    #     if self.state.radio_state is STATE_OFF:
    #         return

    #     # no packet
    #     msg_in_buffer = False
    #     if len(self.receive_buff) > 0:
    #         msg_in_buffer = True

    #     if len(self.receive_buff) > 1:
    #         raise RuntimeError('There should be exactly 1 packet in the receive buffer! Something is wrong.')

    #     #we have a specified receive-window where we expect the packet(s) to arrive
    #     if not msg_in_buffer and not self.rx1_timeout and self.rx1['start'] <= self.timestamp <= self.rx1['end']:
    #         add_event(self.id, self.timestamp + config['general']['sim_sensitive_part_resolution'], self._receive)
    #         return
    #     elif not self.rx1_timeout:
    #         self.rx1_timeout = True
    #         return

    #     if not msg_in_buffer and not self.rx2_timeout and self.rx2['start'] <= self.timestamp <= self.rx2['end']:
    #         add_event(self.id, self.timestamp + config['general']['sim_sensitive_part_resolution'], self._receive)
    #         return
    #     elif not self.rx2_timeout:
    #         self.rx2_timeout = True
    #         return

    #     if self.rx1_timeout and self.rx2_timeout:
    #         return

    #     #we are outside receive-window
    #     if not msg_in_buffer:
    #         return

    #     packet = self.receive_buff.pop(0)
    #     sensitivity = RX_SENSITIVITY[self.lora_band.sf]

    #     # dropping packet if its sensitivity is below receiver sensitivity
    #     if packet['rx_dbm'] < sensitivity:
    #         logger.info(
    #             self.timestamp,
    #             f'Packet dropped by dev_{self.id}. Packet rx_dbm {packet["rx_dbm"]} dBm is below receiver sensitivity '
    #             f'{sensitivity} dBm.'
    #         )
    #         return

    #     self.packets_received += 1
    #     self.bytes_received += len(packet['payload'].encode('utf8'))
    #     logger.info(self.timestamp, f'{bcolors.OKGREEN}Packet received by dev_{self.id}: {packet["payload"]} with RSSI: {packet["rx_dbm"]} dBm{bcolors.ENDC}')


def log_exception(commandline, e, tb):
    with open(f'data/error.log', 'a') as outfile:
        outfile.write(f'{commandline}\n')
        outfile.write(f'{e}\n')
        outfile.write(f'{tb}\n\n')

def log_drift_failure(case):
    with open(f'data/drift_case.log', 'a') as outfile:
        outfile.write(f'{config["general"]["cdppm"],config["wcl"]["guard_time_ms"],config["wcm"]["send_interval_s"],case}\n')

def log_drift_issue(dev_id, timestamp):
    with open(f'data/drift_issue.log', 'a') as outfile:
        outfile.write(f'{commandline}\n')
        outfile.write(f'[{dev_id}]: {format_ms(timestamp, SIU)}\n\n')

    
if __name__ == '__main__':
    parser = argparse.ArgumentParser('LoRa scenario simulator for DAO')
    parser.add_argument('config', help='Specify config file for the simulator')
    parser.add_argument('-o', help='Output directory name', default=None)
    parser.add_argument('-f', help='Force removal of the previous results for the same configuration?', action='store_true')
    parser.add_argument('-l', help='Simple LoRaWAN simulation', action='store_true')
    parser.add_argument('-c', help='Run data-oriented simulation', action='store_true')
    parser.add_argument('-td', help='Set send_interval_s', type=int, default=-1)
    parser.add_argument('-u', help='If run with -c or -l: update send_interval_s to the longest possible', action='store_true')
    parser.add_argument('-d', help='If run with -c: update dw and dcw to the recommended values', action='store_true')
    parser.add_argument('-nbs', help='If run with -c: do not balance energy for End-Devices', action='store_true')
    parser.add_argument('-b', help='If run with -c or -l: update number_of_bytes to the specified value', type=int, default=-1)
    parser.add_argument('-dw', help='Discovery window size in seconds', type=int, default=-1)
    parser.add_argument('-dcw', help='Data Collection window size in seconds', type=int, default=-1)
    parser.add_argument('-n', help='Number of End-Devices', type=int, default=-1)
    parser.add_argument('-radio', help='Radio type for end- / child node: sx1262, sx1276', default='sx1262')
    parser.add_argument('-gwradio', help='Sets LoRaWAN GW radio', default='ic880a_4paths')
    parser.add_argument('-s', help='Only generate schedule for the simulation', action='store_true')
    parser.add_argument('-st', help='Simulation time in seconds', type=int, default=-1)
    parser.add_argument('-gc', help='Generates new coordinates for child nodes for given x, y, and range', type=int, nargs=3)
    parser.add_argument('-cf', help='Shows node coordinates on a figure.', action='store_true')
    parser.add_argument('-plc', help='Plots node coordinates on a figure and saves to a file', action='store_true')
    parser.add_argument('-sbs', help='Let a child node sleep instead of waiting for the assigned response slot', action='store_true')
    parser.add_argument('-gt', help='Guard Time size in ms', type=int, default=0)
    parser.add_argument('-gto', help='Sets minimal working Guard Time with relation to clock drift of a given ppm accuracy', action='store_true')
    parser.add_argument('-cdppm', help='Clock drift in ppm', type=int, default=0)
    parser.add_argument('-pcd', help='Perform clock drift', action='store_true')
    parser.add_argument('-cdp', help='Clock drift: Parent node always before the schedule by cdppm.', action='store_true')
    parser.add_argument('-cdc', help='Clock drift: Child nodes always before the schedule by cdppm.', action='store_true')
    parser.add_argument('-qof', help='Abort the simulation on failure related to the clock drift', action='store_true')
    args = parser.parse_args()

    import os
    from time import time
    import shutil
    started = time()

    commandline = 'python3 simulator.py '
    for k in args.__dict__:
        if getattr(args, k) is None:
            continue
        if getattr(args, k) is False:
            continue
        if type(getattr(args, k)) is int and getattr(args, k) < 0:
            continue

        if getattr(args, k) is True:
            commandline += f'-{k} '
        elif k == 'config':
            commandline += f'{getattr(args, k)} '
        elif type(getattr(args, k)) is list:
            commandline += f'-{k} {" ".join([str(x) for x in getattr(args, k)])} '
        else:
            commandline += f'-{k} {getattr(args, k)} '

    with open(f'data/run.log', 'a') as outfile:
        from datetime import datetime
        dt = datetime.fromtimestamp(time())
        date = dt.strftime('%Y-%m-%d %H:%M:%S')
        commandline = f'[{date}]: {commandline}'
        outfile.write(f'{commandline}\n')
        print(f'\n{commandline}')

    try:
        if not os.path.isfile(args.config):
            print('Configuration file does not exist!')
            exit()

        with open(args.config, 'r') as f:
            config = json.load(f)

        SIU = config['general']['second_in_unit']
        # max_toa = get_time_on_air(config['lora']['payload_size'])
        # config['wcl']['guard_time_ms'] = 3 * round(max_toa, ROUND_N)
        if args.gt > 0 and args.gto:
            raise RuntimeError('You can either use -gt or -gto!')

        if args.gt > 0:
            config['wcl']['guard_time_ms'] = args.gt        
        
        if args.st > 0:
            config['general']['sim_duration_s'] = args.st

        if args.cdppm > 0:
            config['general']['cdppm'] = args.cdppm

        if args.qof:
            config['general']['quit_on_failure'] = True

        sim_seconds = config['general']['sim_duration_s']
        config['general']['sim_duration_ms'] = sim_seconds * SIU
        logger.set_sim_time(config['general']['sim_duration_ms'])
        config['wcm']['radio_type'] = args.radio
        config['wcl']['radio_type'] = args.radio
        config['lwaned']['radio_type'] = args.radio
        config['lwangw']['radio_type'] = args.gwradio

        if args.td > 0 and args.u:
            raise RuntimeError('You can either use -td or -u!')

        if (args.cdp or args.cdc) and not args.pcd:
            raise RuntimeError('You need -pcd to use -cdp or -cdc!')

        if args.cdp and args.cdc:
            raise RuntimeError('You can either use -cdp or -cdc!')

        if args.pcd:
            config['general']['perform_clock_drift'] = True

        if args.td > 0:
            # change payload size here
            min_delay_s = math.ceil(get_time_on_air(config['lora']['payload_size']) / SUBBANDS[TX_PARAMS['band']][2])
            # min_delay_s = math.ceil(get_time_on_air(TX_PARAMS['max_payload']) / SUBBANDS[TX_PARAMS['band']][2])
            if args.td < min_delay_s:
                raise RuntimeError(f'Minimum allowed send_interval_s: {min_delay_s}s')
            config['wcm']['send_interval_s'] = args.td
            config['lwaned']['send_interval_s'] = args.td

        if args.n > 0:
            number_of_devices = args.n + 1
            config['general']['number_of_devices'] = args.n + 1

        number_of_devices = config['general']['number_of_devices']
        coordinates = []
        xc, yc, lrange = [0, 0, 0]
        max_lrange = PROPAGATION_MODEL.calculate_max_distance(SUBBANDS[LORA_BAND_868_0][3], RX_SENSITIVITY[SF_12])
        distance_warning = None
        if args.gc:
            xc, yc, lrange = args.gc
            if lrange > max_lrange:
                distance_warning = f'Specified in -gc range: {lrange}m is higher than the maximum possible: {max_lrange}m for the selected propagation settings!'
            coordinates = generate_coordinates(xc, yc, lrange, number_of_devices - 1)
            config_coordinates = []
            config_coordinates.append([xc, yc, 0])
            for x, y in coordinates:
                config_coordinates.append([x, y, 0])
            config['locations'] = config_coordinates

        if args.dw > 0:
            config['wcm']['disc_window_s'] = args.dw

        if args.dcw > 0:
            config['wcm']['dc_window_s'] = args.dcw

        if args.b > -1:
            bytes_to_send = args.b
            config['lora']['bytes_to_send'] = bytes_to_send

        scheduler = Scheduler(config, TX_PARAMS, RX_SENSITIVITY[TX_PARAMS['sf']], SUBBANDS, TOA)
        if args.c and args.d:
            dw, dcw = scheduler.get_recommended_dw_dcw(sim_seconds, number_of_devices)
            config['wcm']['disc_window_s'] = dw
            config['wcm']['dc_window_s'] = dcw
            scheduler.set_config(config)

        if args.c and args.u:
            try:
                delay_s = scheduler.get_longest_possible_interval(sim_seconds, number_of_devices, config['lora']['bytes_to_send'])
            except RuntimeError:
                dcw, error = scheduler.find_smallest_dcw(sim_seconds, number_of_devices, bytes_to_send)
                raise error
            config['wcm']['send_interval_s'] = delay_s
            scheduler.set_config(config)

        if args.gto:
            gt = (math.ceil(config['wcm']['send_interval_s'] * SIU * (config['general']['cdppm'] / SIU ** 2)) * 4) + 2
            print(f'Minimal Guard Time of {gt} ms for the given clock drift of {config["general"]["cdppm"]} ppm was set.')
            config['wcl']['guard_time_ms'] = gt

        if args.l and args.u:
            delay_s = scheduler.get_longest_possible_interval_for_lwan(sim_seconds, config['lora']['bytes_to_send'])
            config['lwaned']['send_interval_s'] = delay_s
            scheduler.set_config(config)

        if args.o is not None:
            DIR_PATH = f'data/{args.o}_{number_of_devices - 1}_{config["wcm"]["disc_window_s"]}_{config["wcm"]["dc_window_s"]}'
            if args.l:
                DIR_PATH = f'data/{args.o}_{number_of_devices - 1}'
        else:
            now = datetime.today().strftime('%Y%m%d_%H%M%S')
            DIR_PATH = f'data/experiments/{now}'

        if os.path.isdir(DIR_PATH) and args.f:
            shutil.rmtree(DIR_PATH)
        elif os.path.isdir(DIR_PATH):
            print(f'{DIR_PATH} exists! Please use: --f True or remove the directory manually')
            exit()

        os.makedirs(DIR_PATH)
        logger.set_file(f'{DIR_PATH}/log.txt')
        config['general']['dir_path'] = DIR_PATH
        scheduler.set_config(config)

        timestamp = int(time())
        status = {'t': timestamp, 'p': 0.0}
        with open(f'{DIR_PATH}/status.json', 'w') as outfile:
            outfile.write(json.dumps(status, indent=4))

        if len(coordinates) == 0:
            xc, yc, _ = config['locations'][0]
            max_dist, max_dist_co = [0, None]
            for x, y, z in config['locations'][1:number_of_devices]:
                dist = calculate_distance_simple((xc, yc, 0), (x, y, z))
                if dist > max_dist:
                    max_dist = dist
                    max_dist_co = [x, y, z]
                coordinates.append((x, y))
            # lrange = PROPAGATION_MODEL.calculate_max_distance(SUBBANDS[LORA_BAND_868_0][3], RX_SENSITIVITY[SF_12])
            lrange = int(max_dist)
        
        if len(coordinates) > 0 and len(coordinates) < number_of_devices:
            is_lrange_set = "lrange" in locals()
            lrange = lrange if is_lrange_set else max_lrange
            print(lrange)
            xc, yc, _ = config['locations'][0]
            coordinates = generate_coordinates(xc, yc, lrange, number_of_devices - 1, coordinates)
            config_coordinates = []
            config_coordinates.append([xc, yc, 0])
            for x, y in coordinates:
                config_coordinates.append([x, y, 0])
            config['locations'] = config_coordinates

        if args.sbs:
            config['wcl']['sleep_before_slot'] = args.sbs

        with open(f'{DIR_PATH}/config.json', 'w') as outfile:
            outfile.write(json.dumps(config, indent=4))

        if args.plc and len(coordinates) > 0:
            plot_coordinates(xc, yc, max_lrange, coordinates, DIR_PATH, lrange, args.cf)

        if not args.l:
            m_lou = LoRaLitEParentNode(0, config['locations'][0])
            if args.pcd:
                if args.cdp:
                    m_lou.cd_negative = True
                if args.cdc:
                    m_lou.cd_negative = False
            LIST_OF_DEVICES.append(m_lou)
            for i in range(1, number_of_devices):
                lou = LoRaLitEChildNode(i, config['locations'][i])
                if args.pcd:
                    if args.cdp:
                        lou.cd_negative = False
                    if args.cdc:
                        lou.cd_negative = True
                LIST_OF_DEVICES.append(lou)

            calculate_distance_matrix(LIST_OF_DEVICES)
            if not args.c:
                m_lou.packet_schedule = scheduler.generate_schedule_for_wcm(sim_seconds, number_of_devices)
            else:
                balance_energy = True
                if args.nbs:
                    balance_energy = False
                
                if config['wcm']['send_interval_s'] >= 28800:
                    m_lou.packet_schedule = scheduler.generate_schedule_for_wcm_data_simple(sim_seconds, number_of_devices, config['lora']['bytes_to_send'], balance_energy)
                else:
                    m_lou.packet_schedule = scheduler.generate_schedule_for_wcm_data_fix(sim_seconds, number_of_devices, config['lora']['bytes_to_send'], balance_energy)
        else:
            m_lou = LoRaWANGateway(0, config['locations'][0])
            LIST_OF_DEVICES.append(m_lou)
            GW = m_lou
            for i in range(1, number_of_devices):
                lou = LoRaWANEndDevice(i, config['locations'][i])
                delay, lou.packet_schedule = scheduler.generate_schedule_for_lwan(lou, sim_seconds, number_of_devices, config['lora']['bytes_to_send'])
                lou.config['send_interval'] = delay * SIU
                LIST_OF_DEVICES.append(lou)

            calculate_distance_matrix(LIST_OF_DEVICES)
    except Exception as e:
        log_exception(commandline, e, traceback.format_exc())
        raise e

    if distance_warning is not None:
        logger.info(SIM_TIME, f'{bcolors.WARNING}{distance_warning}{bcolors.ENDC}\n')
        logger._flush()

    if args.s:
        from sys import exit
        exit(0)

    try:
        logger.info(SIM_TIME, 'Simulation started!')
        while SIM_TIME < config['general']['sim_duration_ms']:
            try:
                events = EVENT_LIST.popitem(0)[1]
                for event in events:
                    event.execute()
            except KeyError:
                # end of simulation
                SIM_TIME = config['general']['sim_duration_ms']
            except ClockDriftException as e:
                if config['general']['quit_on_failure'] and args.cdp:
                    log_drift_failure(1)
                    raise KeyboardInterrupt
                if config['general']['quit_on_failure'] and args.cdc:
                    log_drift_failure(2)
                    raise KeyboardInterrupt
            except Exception as e:
                log_exception(commandline, e, traceback.format_exc())

    except KeyboardInterrupt:
        logger._flush()
        logger.info(SIM_TIME, f'{bcolors.WARNING}Simulation interrupted!{bcolors.ENDC}\n')
        logger._flush()
        exit(0)
    except Exception as e:
        logger._flush()
        log_exception(commandline, e, traceback.format_exc())
        logger.info(SIM_TIME, f'{bcolors.BRED}Simulation failed!{bcolors.ENDC}\n')
        logger._flush()
        raise e

    LIST_OF_DEVICES.sort(key=lambda x: x.id)
    def _print_dev_stats():
        eds_packets_sent = sum([x.packets_sent for x in LIST_OF_DEVICES if x.type is not DEV_TYPE.PARENT and LWAN_DEV_TYPE.GW])
        for dev in LIST_OF_DEVICES:
            logger.always(SIM_TIME, f'{bcolors.UNDERLINE}Stats for dev_{dev.id} [{dev.type.name}]{bcolors.ENDC}')
            logger.always(SIM_TIME, f'\t{"[Packets sent]":20s}: {dev.packets_sent}')
            logger.always(SIM_TIME, f'\t{"[Bytes sent]":20s}: {dev.bytes_sent:,}')
            if not args.l and dev.type is not DEV_TYPE.PARENT:
                logger.always(SIM_TIME, f'\t{"[DCR Bytes sent]":20s}: {dev.dc_bytes_sent:,}')
            logger.always(SIM_TIME, f'\t{"[Packets received]":20s}: {dev.packets_received}')
            if dev.type is DEV_TYPE.PARENT:
                logger.always(SIM_TIME, f'\t{"[Should receive]":20s}: {dev.total_expected_recv_count}')
                logger.always(SIM_TIME, f'\t{"[Child nodes sent]":20s}: {eds_packets_sent}')
            elif dev.type is LWAN_DEV_TYPE.GW:
                logger.always(SIM_TIME, f'\t{"[Should receive]":20s}: {eds_packets_sent}')
            if not args.l and dev.type is not DEV_TYPE.PARENT:
                logger.always(SIM_TIME, f'\t{"[D received]":20s}: {dev.d:,}')
                logger.always(SIM_TIME, f'\t{"[DC received]":20s}: {dev.dc:,}\n')
            else:
                logger.always(SIM_TIME, f'\t{"[Bytes received]":20s}: {dev.bytes_received:,}\n')
    
    sim_msg = f'{bcolors.BGREEN}Simulation finished!{bcolors.ENDC}\n'
    time_color = bcolors.BGREEN
    if LIST_OF_DEVICES[0].type is DEV_TYPE.PARENT and LIST_OF_DEVICES[0].packets_received < LIST_OF_DEVICES[0].total_expected_recv_count:
        sim_msg = f'{bcolors.BRED}Simulation failed!{bcolors.ENDC}\n'
        time_color = bcolors.BRED

    logger.always(SIM_TIME, sim_msg)

    _print_dev_stats()

    for dev in LIST_OF_DEVICES:
        dev.energy.calculate_energy_usage(dev.initial_state, dev.state_table, dev.id, sim_seconds)

    ended = time()
    logger.always(SIM_TIME, f'{time_color}Execution time: {math.ceil(ended - started)}s.{bcolors.ENDC}\n')

