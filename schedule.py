import math
from exceptions import SimException
from definitions import *
from random import choice, shuffle
from itertools import cycle
from string import ascii_uppercase


class Scheduler:
    def __init__(self, config, tx_params, rx_sensitivity, subbands, toa):
        self.config = config
        self.tx_params = tx_params
        self.toa = toa
        self.rx_sensitivity = rx_sensitivity
        self.subbands = subbands

    def set_config(self, config):
        self.config = config

    def generate_schedule_for_wcm(self, sim_seconds, number_of_devices):
        nr_of_cmd = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / self.config['wcm']['send_interval_s'])
        # print(nr_of_cmd)
        # print('####')
        toa_dc_ms = self.toa.get_time_on_air(self.tx_params['max_payload']) * self.config['general']['second_in_unit']
        toa_disc_ms = self.toa.get_time_on_air(len(f'{number_of_devices + 1}#{self.config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{self.rx_sensitivity}.00#0'.encode('utf8'))) * self.config['general']['second_in_unit']
        packets_per_disc_window = math.floor(self.config['wcm']['disc_window_s'] * 1000 / (toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))
        packets_per_dc_window =  math.floor(self.config['wcm']['dc_window_s'] * 1000 / (toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))

        def _get_number_of_slots_for_cmd(for_cmd, packets_per_cmd):
            return math.ceil((number_of_devices - 1) / packets_per_cmd)

        slots_per_disc_cmd = _get_number_of_slots_for_cmd(CMD_DISC, packets_per_disc_window)
        slots_per_dc_cmd = _get_number_of_slots_for_cmd(CMD_DATA_COLLECTION, packets_per_dc_window)

        if self.config['wcm']['dc_after_disc'] is False:
            if self.config['wcm']['first_disc_at_cmd_nr'] != -1:
                if self.config['wcm']['first_disc_at_cmd_nr'] == self.config['wcm']['first_dc_at_cmd_nr']:
                    print('Error: [wcm][first_disc_at_cmd_nr] and [wcm][first_dc_at_cmd_nr] can not be the same number because [wcm][dc_after_disc] is set to False!')
                    raise SimException()

                if self.config['wcm']['first_dc_at_cmd_nr'] != -1 and self.config['wcm']['first_disc_at_cmd_nr'] > self.config['wcm']['first_dc_at_cmd_nr']:
                    print('Error: [wcm][first_disc_at_cmd_nr] has to be lower than [wcm][first_dc_at_cmd_nr]!')
                    raise SimException()

                if self.config['wcm']['first_dc_at_cmd_nr'] != -1 and self.config['wcm']['first_disc_at_cmd_nr'] <= self.config['wcm']['first_dc_at_cmd_nr'] < self.config['wcm']['first_disc_at_cmd_nr'] + self.config['wcm']['repeat_cmd_n_times'] * slots_per_disc_cmd:
                    print(f'Error: [wcm][first_dc_at_cmd_nr] has to be greater than [wcm][first_disc_at_cmd_nr] ({self.config["wcm"]["first_disc_at_cmd_nr"]}) + [wcm][repeat_cmd_n_times] ' \
                        f'({self.config["wcm"]["repeat_cmd_n_times"]}) * slots_per_disc_cmd ({slots_per_disc_cmd})!')
                    raise SimException()

            if self.config['wcm']['dc_every_n_cmd'] != -1:
                if self.config['wcm']['disc_every_n_cmd'] > self.config['wcm']['dc_every_n_cmd']:
                    print('Error: [wcm][dc_every_n_cmd] can not be smaller than [wcm][disc_every_n_cmd]!')
                    raise SimException()

                if self.config['wcm']['dc_every_n_cmd'] == self.config['wcm']['disc_every_n_cmd']:
                    print('Error: [wcm][disc_every_n_cmd] and [wcm][dc_every_n_cmd] can not be the same number because [wcm][dc_after_disc] is set to False!')
                    raise SimException()

                if self.config['wcm']['disc_every_n_cmd'] != -1 and self.config['wcm']['dc_every_n_cmd'] % self.config['wcm']['disc_every_n_cmd'] == 0:
                    print('Error: [wcm][dc_every_n_cmd] can not be a multiple of [wcm][disc_every_n_cmd]!')
                    raise SimException()

                if self.config['wcm']['disc_every_n_cmd'] <= self.config['wcm']['dc_every_n_cmd'] < self.config['wcm']['disc_every_n_cmd'] + self.config['wcm']['repeat_cmd_n_times'] * slots_per_disc_cmd:
                    print(f'Error: [wcm][dc_every_n_cmd] has to be greater than [wcm][disc_every_n_cmd] ({self.config["wcm"]["dc_every_n_cmd"]}) + [wcm][repeat_cmd_n_times] ' \
                        f'({self.config["wcm"]["repeat_cmd_n_times"] }) * slots_per_disc_cmd ({slots_per_disc_cmd})!')
                    raise SimException()


        # print(f'{toa_disc_ms}: {packets_per_disc_window} | {toa_dc_ms}: {packets_per_dc_window}')
        # print('####')

        current_cmd = previous_cmd = CMD_SYNC
        current_delay = self.config['wcm']['send_interval_s']
        nr_of_retransmissions = slots_to_schedule = dev_per_slot = 0
        data = ''
        schedule = {}
        dev_ids = [x for x in range(1, number_of_devices)]

        if self.config['general']['save_schedule_to_file']:
            file_name = f'{self.config["general"]["dir_path"]}/schedule.txt'
            f = open(file_name, 'a')

        for cmd_nr in range(0, nr_of_cmd+1):
            if cmd_nr == 0:
                current_cmd = CMD_SYNC
                data = str(current_delay)
            elif cmd_nr == self.config['wcm']['first_disc_at_cmd_nr'] or cmd_nr % self.config['wcm']['disc_every_n_cmd'] == 0 and self.config['wcm']['disc_every_n_cmd'] != -1:
                current_cmd = CMD_DISC
                nr_of_retransmissions = self.config['wcm']['repeat_cmd_n_times'] - 1
                slots_to_schedule = slots_per_disc_cmd
                dev_per_slot = packets_per_disc_window
                dev_ids = [x for x in range(1, number_of_devices)]
                data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
            elif previous_cmd is not CMD_SYNC and nr_of_retransmissions > 0:
                nr_of_retransmissions -= 1
            elif previous_cmd is not CMD_SYNC and nr_of_retransmissions == 0 and slots_to_schedule > 1:
                slots_to_schedule -= 1
                nr_of_retransmissions = self.config['wcm']['repeat_cmd_n_times'] - 1
                current_cmd = previous_cmd
                del dev_ids[:dev_per_slot]
                data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
            elif (self.config['wcm']['dc_after_disc'] and previous_cmd is CMD_DISC) \
                or (self.config['wcm']['dc_after_disc'] is False and (cmd_nr == self.config['wcm']['first_dc_at_cmd_nr'] or cmd_nr % self.config['wcm']['dc_every_n_cmd'] == 0 and self.config['wcm']['dc_every_n_cmd'] != -1)):
                current_cmd = CMD_DATA_COLLECTION
                nr_of_retransmissions = self.config['wcm']['repeat_cmd_n_times'] - 1
                slots_to_schedule = slots_per_dc_cmd
                dev_per_slot = packets_per_dc_window
                dev_ids = [x for x in range(1, number_of_devices)]
                data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
            else:
                current_cmd = CMD_SYNC
                data = str(current_delay)

            info = f'[{cmd_nr:3}]: {current_cmd} | {current_delay} | {data:15} | {nr_of_retransmissions}'
            if self.config['general']['save_schedule_to_file']:
                f.write(f'{info}\n')
            # print(info)

            schedule[cmd_nr] = {PAYLOAD.SEQ: cmd_nr, PAYLOAD.CMD: current_cmd, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: nr_of_retransmissions}
            previous_cmd = current_cmd

        if self.config['general']['save_schedule_to_file']:
            f.close()

        return schedule


    def get_recommended_dw_dcw(self, sim_seconds, number_of_devices):
        toa_dc_ms = math.ceil(self.toa.get_time_on_air(self.config['lora']['payload_size']) * self.config['general']['second_in_unit'])
        toa_disc_ms = math.ceil(self.toa.get_time_on_air(len(f'{number_of_devices + 1}#{self.config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{self.rx_sensitivity}.00#0'.encode('utf8'))) * self.config['general']['second_in_unit'])

        rec_dcw = math.ceil((toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        rec_dw = math.ceil((toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        
        print(f'Configured optimal lengths of dw: {rec_dw}s, and dcw: {rec_dcw}s! Requested with -c -d flags.')

        return rec_dw, rec_dcw

    def find_smallest_dcw(self, sim_seconds, number_of_devices, bytes_to_send):
        dcw = self.config['wcm']['dc_window_s']
        error = None
        while True:
            try:
                delay_s = self.get_longest_possible_interval(sim_seconds, number_of_devices, bytes_to_send, dcw)
                break
            except RuntimeError as e:
                if error is None:
                    error = e
                dcw += 1
                continue

        print(f'Smallest allowed DCW: {dcw} with send_interval_s: {delay_s}')

        return dcw, error

    def get_longest_possible_interval(self, sim_seconds, number_of_devices, bytes_to_send, dcw=0):
        if bytes_to_send > 0:
            days = int(sim_seconds / 86400)
            toa_dc_ms = self.toa.get_time_on_air(self.config['lora']['payload_size']) * self.config['general']['second_in_unit']
            toa_disc_ms = self.toa.get_time_on_air(len(f'{number_of_devices + 1}#{self.config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{self.rx_sensitivity}.00#0'.encode('utf8'))) * self.config['general']['second_in_unit']

            # rec_dcw = math.ceil((toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices - 1) / self.config['general']['second_in_unit'])
            # rec_dw = math.ceil((toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices - 1) / self.config['general']['second_in_unit'])

            if dcw == 0:
                dcw = self.config['wcm']['dc_window_s']

            packets_per_disc_window = math.floor(self.config['wcm']['disc_window_s'] * self.config['general']['second_in_unit'] / (toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))
            packets_per_dc_window =  math.floor(dcw * self.config['general']['second_in_unit'] / (toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))

            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size'])

            def _get_number_of_slots_for_cmd(for_cmd, packets_per_cmd):
                return math.ceil((number_of_devices - 1) / packets_per_cmd)

            slots_per_disc_cmd = _get_number_of_slots_for_cmd(CMD_DISC, packets_per_disc_window)
            slots_per_dc_cmd = _get_number_of_slots_for_cmd(CMD_DATA_COLLECTION, packets_per_dc_window)

            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size']) * slots_per_dc_cmd

            possible_nr_of_cmd = dcr_packets_count + days + slots_per_disc_cmd * days
            possible_delay_s = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / possible_nr_of_cmd)
            # the send delay can not be smaller than 
            minimum_allowed_delay_s = toa_dc_ms / self.config['general']['second_in_unit'] / self.subbands[self.tx_params['band']][2]
            if possible_delay_s < minimum_allowed_delay_s:
                dcw = self.config['wcm']['dc_window_s']
                raise RuntimeError(f'It is not possible to request {bytes_to_send} bytes of data from {number_of_devices - 1} ' \
                    f'EDs with a given DCW: {dcw}. Required send_interval_s == {possible_delay_s}. Minimum allowed send_interval_s == {minimum_allowed_delay_s}')
            print(f'Maximum allowed delay for the specified amount ({bytes_to_send}B) of data: {possible_delay_s}s!')
        else:
            possible_delay_s = self.config['wcm']['send_interval_s']

        return possible_delay_s

    def generate_schedule_for_wcm_data(self, dev, sim_seconds, number_of_devices, bytes_to_send, balance_energy=True):
        days = int(sim_seconds / 86400)
        toa_dc_ms = math.ceil(self.toa.get_time_on_air(self.config['lora']['payload_size']) * self.config['general']['second_in_unit'])
        toa_disc_ms = math.ceil(self.toa.get_time_on_air(len(f'{number_of_devices + 1}#{self.config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{self.rx_sensitivity}.00#0'.encode('utf8'))) * self.config['general']['second_in_unit'])
        rec_dcw = math.ceil((toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        rec_dw = math.ceil((toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        
        if self.config['wcm']['disc_window_s'] != rec_dw or self.config['wcm']['dc_window_s'] != rec_dcw:
            print(f'Recommended dw: {rec_dw}s, dcw: {rec_dcw}s')

        delay_s = self.config['wcm']['send_interval_s']
        nr_of_cmd = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / delay_s)
        nr_of_cmd_per_day = math.floor(nr_of_cmd / days)
        cmd_left = nr_of_cmd - days * nr_of_cmd_per_day

        packets_per_disc_window = math.floor(self.config['wcm']['disc_window_s'] * self.config['general']['second_in_unit'] / (toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))
        packets_per_dc_window =  math.floor(self.config['wcm']['dc_window_s'] * self.config['general']['second_in_unit'] / (toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))

        dcr_packets_count = 0
        if bytes_to_send > 0:
            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size'])

        def _get_number_of_slots_for_cmd(for_cmd, packets_per_cmd):
            return math.ceil((number_of_devices - 1) / packets_per_cmd)

        slots_per_disc_cmd = _get_number_of_slots_for_cmd(CMD_DISC, packets_per_disc_window)
        slots_per_dc_cmd = _get_number_of_slots_for_cmd(CMD_DATA_COLLECTION, packets_per_dc_window)

        cmd_per_day = []
        for day in range(0, days):
            if cmd_left > 0:
                cmd_per_day.append([x for x in range(0, nr_of_cmd_per_day + slots_per_dc_cmd)])
                cmd_left -= slots_per_dc_cmd
                continue

            cmd_per_day.append([x for x in range(0, nr_of_cmd_per_day)])

        max_allowed_dcr_count = nr_of_cmd - days - slots_per_disc_cmd * days
        if bytes_to_send > 0:
            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size']) * slots_per_dc_cmd
        else:
            dcr_packets_count = math.floor((nr_of_cmd - days - slots_per_disc_cmd * days) / slots_per_dc_cmd)

        nr_of_dcr_per_day = math.floor(dcr_packets_count / days)
        if nr_of_dcr_per_day == 0:
            nr_of_dcr_per_day = 1
        dcr_left = dcr_packets_count - nr_of_dcr_per_day * days
        if dcr_left < 0:
            dcr_left = 0

        if dcr_packets_count > max_allowed_dcr_count:
            nr_of_cmd = dcr_packets_count + days + slots_per_disc_cmd * days
            delay_s = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / nr_of_cmd)
            raise RuntimeError(f'It is not possible to request {bytes_to_send} bytes of data from {number_of_devices - 1}' \
                f'EDs with the current configuration. Needed DCRs: {dcr_packets_count}. Scheduled DCRs: {max_allowed_dcr_count}! ' \
                f'Maximum send_interval_s == {delay_s}!')

        if bytes_to_send > 0:
            possible_nr_of_cmd = dcr_packets_count + days + slots_per_disc_cmd * days
            possible_delay_s = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / possible_nr_of_cmd)
            if possible_delay_s != delay_s:
                print(f'Maximum allowed delay for the specified amount ({bytes_to_send}B) of data: {possible_delay_s}s!')
            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size'])

        dcr_every_n_cmd = math.floor((nr_of_cmd - days - slots_per_disc_cmd * days) / (dcr_packets_count))
        if dcr_every_n_cmd > nr_of_cmd_per_day:
            dcr_every_n_cmd = nr_of_cmd_per_day - 1

        dc_count = dc_total_count = bytes_scheduled = count = 0
        current_cmd = previous_cmd = CMD_SYNC
        current_delay = delay_s
        nr_of_retransmissions = slots_to_schedule = dev_per_slot = 0
        data = ''
        schedule = {}
        dev_ids = [x for x in range(1, number_of_devices)]
        d_slots = {}
        dc_slots = {}
        sync_free_slots = []
        orig_nr_of_dcr_per_day = nr_of_dcr_per_day
        def _count_slots(slots_list, slots_to_schedule, devs):
            if slots_to_schedule not in slots_list:
                slots_list[slots_to_schedule] = {'devs': devs, 'count': 0}

            slots_list[slots_to_schedule]['count'] += 1
            return slots_list

        d_slots_balancing = {}
        dc_slots_balancing = {}
        def _balance_slots(slots_list, slots_to_schedule, devs):
            if slots_to_schedule not in slots_list:
                slots_list[slots_to_schedule] = devs
                return slots_list, ','.join([str(x) for x in devs])

            last_devs_order = slots_list[slots_to_schedule]
            new_order = [last_devs_order[-1]] + last_devs_order[:-1]
            slots_list[slots_to_schedule] = new_order

            return slots_list, ','.join([str(x) for x in new_order])

        count = 0
        days_separator = []
        
        for day in range(0, days):
            dc_count = 0
            for cmd_nr in cmd_per_day[day]:
                if cmd_nr == 0:
                    if day > 0:
                        days_separator.append(count - 1)
                    current_cmd = CMD_SYNC
                    data = str(current_delay)
                    nr_of_dcr_per_day = orig_nr_of_dcr_per_day
                elif cmd_nr == 1:
                    current_cmd = CMD_DISC
                    slots_to_schedule = slots_per_disc_cmd
                    dev_per_slot = packets_per_disc_window
                    dev_ids = [x for x in range(1, number_of_devices)]
                    data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                    if slots_to_schedule not in d_slots:
                        d_slots[slots_to_schedule] = {'devs': data, 'count': 0}
                    d_slots = _count_slots(d_slots, slots_to_schedule, data)
                    if balance_energy:
                        d_slots_balancing, data = _balance_slots(d_slots_balancing, slots_to_schedule, dev_ids[:dev_per_slot])
                    slots_to_schedule -= 1
                elif slots_to_schedule > 0:
                    current_cmd = previous_cmd
                    del dev_ids[:dev_per_slot]
                    data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                    if current_cmd == CMD_DATA_COLLECTION:
                        dc_slots = _count_slots(dc_slots, slots_to_schedule, data)
                        if balance_energy:
                            dc_slots_balancing, data = _balance_slots(dc_slots_balancing, slots_to_schedule, dev_ids[:dev_per_slot])
                    else:
                        d_slots = _count_slots(d_slots, slots_to_schedule, data)
                        if balance_energy:
                            d_slots_balancing, data = _balance_slots(d_slots_balancing, slots_to_schedule, dev_ids[:dev_per_slot])
                    slots_to_schedule -= 1
                elif cmd_nr > 1 and cmd_nr % dcr_every_n_cmd == 0 and (bytes_scheduled < bytes_to_send or bytes_to_send == 0) and dc_count < nr_of_dcr_per_day:
                    current_cmd = CMD_DATA_COLLECTION
                    slots_to_schedule = slots_per_dc_cmd
                    dev_per_slot = packets_per_dc_window
                    dev_ids = [x for x in range(1, number_of_devices)]
                    data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                    bytes_scheduled += self.config['lora']['payload_size']
                    dc_slots = _count_slots(dc_slots, slots_to_schedule, data)
                    if balance_energy:
                        dc_slots_balancing, data = _balance_slots(dc_slots_balancing, slots_to_schedule, dev_ids[:dev_per_slot])
                    # _balance_slots666666666666666666666666666666666666666666666666666666666666666666666666666666666666666
                    slots_to_schedule -= 1
                    dc_count += 1
                    dc_total_count += 1
                else:
                    current_cmd = CMD_SYNC
                    data = str(current_delay)
                    sync_free_slots.append(count)

                schedule[count] = {PAYLOAD.SEQ: count, PAYLOAD.CMD: current_cmd, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: 0}
                previous_cmd = current_cmd
                count += 1

        shuffle(sync_free_slots)
        dcr_left = 0
        for slot in dc_slots:
            dcr_left += dcr_packets_count - dc_slots[slot]['count']
            dc_slots[slot]['dcr_left'] = dcr_packets_count - dc_slots[slot]['count']

        if dcr_left <= len(sync_free_slots):
            for slot in dc_slots:
                dcr_left = dc_slots[slot]['dcr_left']
                for x in range(0, dcr_left):
                    dc_slots[slot]['count'] += 1
                    cmd_nr = sync_free_slots.pop()
                    data = dc_slots[slot]['devs']
                    if balance_energy:
                        dc_slots_balancing, data = _balance_slots(dc_slots_balancing, slot, dc_slots[slot]['devs'].split(','))
                    schedule[cmd_nr] = {PAYLOAD.SEQ: cmd_nr, PAYLOAD.CMD: CMD_DATA_COLLECTION, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: 0}
                
                dc_slots[slot]['dcr_left'] = 0

        if self.config['general']['save_schedule_to_file']:
            file_name = f'{self.config["general"]["dir_path"]}/schedule.txt'
            f = open(file_name, 'a')

            count = 0
            for cmd_nr in schedule:
                if cmd_nr == 0:
                    f.write(f'Day: {count}\n')
                    count += 1

                if cmd_nr - 1 in days_separator:
                    f.write(f'\nDay: {count}\n')
                    count += 1
                packet = schedule[cmd_nr]
                info = f'[{cmd_nr:3}]: {packet[PAYLOAD.CMD]} | {current_delay} | {packet[PAYLOAD.DATA]:30} | {packet[PAYLOAD.NR_OF_RET]}'
                f.write(f'{info}\n')

            f.close()

        print(f'[SYNC]: {days + len(sync_free_slots)}')

        if len(d_slots) == 0:
            raise RuntimeError(f'Problem with DISC schedule: not a single DISC scheduled!')

        for slot in d_slots:
            print(f'[DISC][{d_slots[slot]["devs"]:30}]: {d_slots[slot]["count"]} | {days}')
            if d_slots[slot]['count'] != days:
                raise RuntimeError(f'Problem with DISC schedule: [{d_slots[slot]["devs"]}][{d_slots[slot]["count"]}] vs {days}')

        if len(dc_slots) == 0:
            raise RuntimeError(f'Problem with DC schedule: not a single DC scheduled!')

        for slot in dc_slots:
            print(f'[DCOL][{dc_slots[slot]["devs"]:30}]: {dc_slots[slot]["count"]} | {dcr_packets_count} | {dc_slots[slot]["count"] * self.config["lora"]["payload_size"]}B')
            if dc_slots[slot]['count'] != dcr_packets_count:
                raise RuntimeError(f'Problem with DC schedule: [{dc_slots[slot]["devs"]}][{dc_slots[slot]["count"]}] vs {dcr_packets_count}')

        return schedule

    def generate_schedule_for_wcm_data_fix(self, sim_seconds, number_of_devices, bytes_to_send, balance_energy=True):
        days = int(sim_seconds / 86400)
        days = days if days > 0 else 1
        toa_dc_ms = math.ceil(self.toa.get_time_on_air(self.config['lora']['payload_size']) * self.config['general']['second_in_unit'])
        toa_disc_ms = math.ceil(self.toa.get_time_on_air(len(f'{number_of_devices + 1}#{self.config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{self.rx_sensitivity}.00#0'.encode('utf8'))) * self.config['general']['second_in_unit'])
        rec_dcw = math.ceil((toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        rec_dw = math.ceil((toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        c_dcw = self.config['wcm']['dc_window_s'] 
        c_dw = self.config['wcm']['disc_window_s']
        uses_rec_settings = True if c_dcw == rec_dcw and c_dw == rec_dw else False

        for x in range(1, number_of_devices + 1):
            per_x_dcw = math.ceil((toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * x / self.config['general']['second_in_unit'])
            print(f'[DCW][{x}]: {per_x_dcw}')

        if not uses_rec_settings:
            print(f'Recommended dw: {rec_dw}s, dcw: {rec_dcw}s')

        delay_s = self.config['wcm']['send_interval_s']
        nr_of_cmd = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / delay_s)
        nr_of_cmd_per_day = math.floor(nr_of_cmd / days)
        cmd_left = nr_of_cmd - days * nr_of_cmd_per_day

        packets_per_disc_window = math.floor(self.config['wcm']['disc_window_s'] * self.config['general']['second_in_unit'] / (toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))
        packets_per_dc_window =  math.floor(self.config['wcm']['dc_window_s'] * self.config['general']['second_in_unit'] / (toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))

        dcr_packets_count = 0
        if bytes_to_send > 0:
            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size'])

        def _get_number_of_slots_for_cmd(for_cmd, packets_per_cmd):
            return math.ceil((number_of_devices - 1) / packets_per_cmd)

        slots_per_disc_cmd = _get_number_of_slots_for_cmd(CMD_DISC, packets_per_disc_window)
        slots_per_dc_cmd = _get_number_of_slots_for_cmd(CMD_DATA_COLLECTION, packets_per_dc_window)

        cmd_per_day = []
        for day in range(0, days):
            if cmd_left > 0:
                cmd_per_day.append([x for x in range(0, nr_of_cmd_per_day + slots_per_dc_cmd)])
                cmd_left -= slots_per_dc_cmd
                continue

            cmd_per_day.append([x for x in range(0, nr_of_cmd_per_day)])

        max_allowed_dcr_count = nr_of_cmd - days - slots_per_disc_cmd * days
        if bytes_to_send > 0:
            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size']) * slots_per_dc_cmd
        else:
            dcr_packets_count = math.floor((nr_of_cmd - days - slots_per_disc_cmd * days) / slots_per_dc_cmd)

        nr_of_dcr_per_day = math.floor(dcr_packets_count / days)
        if nr_of_dcr_per_day == 0:
            nr_of_dcr_per_day = 1
        dcr_left = dcr_packets_count - nr_of_dcr_per_day * days
        # nr_of_sync_cmd (days) - nr_of_disc_responses_cmd (slots_per_disc_cmd * days) - nr_of_scheduled_dc_responses_cmd (nr_of_dcr_per_day * days)
        cmd_left = (nr_of_cmd - days - slots_per_disc_cmd * days - nr_of_dcr_per_day * days)
        if dcr_left < 0:
            dcr_left = 0

        if dcr_packets_count > max_allowed_dcr_count:
            nr_of_cmd = dcr_packets_count + days + slots_per_disc_cmd * days
            delay_s = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / nr_of_cmd)
            raise RuntimeError(f'It is not possible to request {bytes_to_send} bytes of data from {number_of_devices - 1}' \
                f'EDs with the current configuration. Needed DCRs: {dcr_packets_count}. Scheduled DCRs: {max_allowed_dcr_count}! ' \
                f'Maximum send_interval_s == {delay_s}!')

        if bytes_to_send > 0:
            possible_nr_of_cmd = dcr_packets_count + days + slots_per_disc_cmd * days
            possible_delay_s = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / possible_nr_of_cmd)
            if possible_delay_s != delay_s:
                print(f'Maximum allowed delay for the specified amount ({bytes_to_send}B) of data: {possible_delay_s}s!')
            dcr_packets_count = math.ceil(bytes_to_send / self.config['lora']['payload_size'])

        dcr_every_n_cmd = math.floor((nr_of_cmd - days - slots_per_disc_cmd * days) / (dcr_packets_count))
        if dcr_every_n_cmd > nr_of_cmd_per_day:
            dcr_every_n_cmd = nr_of_cmd_per_day - 1

        dc_count = dc_total_count = bytes_scheduled = count = 0
        current_cmd = previous_cmd = CMD_SYNC
        current_delay = delay_s
        nr_of_retransmissions = slots_to_schedule = dev_per_slot = 0
        data = ''
        schedule = {}
        dev_ids = [x for x in range(1, number_of_devices)]
        d_slots = {}
        dc_slots = {}
        sync_free_slots = []
        orig_nr_of_dcr_per_day = nr_of_dcr_per_day
        def _count_slots(slots_list, slots_to_schedule, devs):
            if slots_to_schedule not in slots_list:
                slots_list[slots_to_schedule] = {'devs': devs, 'count': 0}

            slots_list[slots_to_schedule]['count'] += 1
            return slots_list

        d_slots_balancing = {}
        dc_slots_balancing = {}
        dev_stats = {}
        for i in range(1, number_of_devices):
            dev_stats[i] = {'c': 0, 'b': 0}

        def _balance_slots(cyclic_dev_list, dc=False):
            new_order = next(cyclic_dev_list)
            if dc:
                for id in new_order:
                    dev_stats[id]['c'] += 1
                    dev_stats[id]['b'] += self.config['lora']['payload_size']

            return ','.join([str(x) for x in new_order])

        def _balance_devs(cnt, devs):
            all = []
            for d in devs:
                all += d
            # new_order = [all[-1]] + all[:-1]
            new_order = all[1:] + all[:1]

            nr_slots = len(cnt) - 1
            dev_assigned = 0
            for i in range(0, len(cnt)):
                if i == 0:
                    devs[i] = new_order[:cnt[i]]
                elif i == nr_slots:
                    devs[i] = new_order[dev_assigned:]
                else:
                    devs[i] = new_order[dev_assigned:dev_assigned + cnt[i]]

                dev_assigned += len(devs[i])

            return devs

        def _get_balanced_list_of_devs(slots_per_window):
            it = 1
            iit = 0
            cyclic_devs = []
            condition = []
            is_gen_done = False
            all_devs = [x for x in range(1, number_of_devices)]
            # slots_to_schedule = slots_per_dc_cmd
            devs = []
            cnt = []
            while len(all_devs) > 0:
                slot_devs = all_devs[:slots_per_window]
                cnt.append(len(slot_devs))
                devs.append(slot_devs)
                del all_devs[:slots_per_window]
            
            while True:
                iit = 1
                for dev in devs:
                    if it == 1 and len(condition) == 0:
                        condition = dev
                    if it > 1 and condition == dev and iit == 1:
                        is_gen_done = True
                        break
                    cyclic_devs.append(dev)
                    iit += 1
                if is_gen_done:
                    break
                it += 1
                devs = _balance_devs(cnt, devs)
            
            return cyclic_devs

        d_balanced_list_of_devs = cycle(_get_balanced_list_of_devs(packets_per_disc_window))
        dc_balanced_list_of_devs = cycle(_get_balanced_list_of_devs(packets_per_dc_window))

        count = 0
        days_separator = []    
        for day in range(0, days):
            dc_count = 0
            for cmd_nr in cmd_per_day[day]:
                if cmd_nr == 0:
                    if day > 0:
                        days_separator.append(count - 1)
                    current_cmd = CMD_SYNC
                    data = str(current_delay)
                    nr_of_dcr_per_day = orig_nr_of_dcr_per_day
                elif cmd_nr == 1:
                    current_cmd = CMD_DISC
                    slots_to_schedule = slots_per_disc_cmd
                    dev_per_slot = packets_per_disc_window
                    dev_ids = [x for x in range(1, number_of_devices)]
                    data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                    if balance_energy:
                        data = _balance_slots(d_balanced_list_of_devs)
                    d_slots = _count_slots(d_slots, slots_to_schedule, data)
                    slots_to_schedule -= 1
                elif slots_to_schedule > 0:
                    current_cmd = previous_cmd
                    del dev_ids[:dev_per_slot]
                    data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                    if current_cmd == CMD_DATA_COLLECTION:
                        if balance_energy:
                            data = _balance_slots(dc_balanced_list_of_devs, True)
                        else:
                            for x in dev_ids[:dev_per_slot]:
                                dev_stats[x]['c'] += 1
                                dev_stats[x]['b'] += self.config['lora']['payload_size']
                        dc_slots = _count_slots(dc_slots, slots_to_schedule, data)
                    else:
                        if balance_energy:
                            data = _balance_slots(d_balanced_list_of_devs)
                        d_slots = _count_slots(d_slots, slots_to_schedule, data)
                    slots_to_schedule -= 1
                    if current_cmd == CMD_DATA_COLLECTION and (number_of_devices - 1) == slots_per_dc_cmd and bytes_scheduled >= bytes_to_send:
                        slots_to_schedule = len([x for x in dev_stats if dev_stats[x]['b'] < bytes_to_send])
                elif (
                    cmd_nr > 1 
                    and (cmd_nr % dcr_every_n_cmd == 0 or slots_to_schedule == 0) 
                    and (bytes_scheduled < bytes_to_send or bytes_to_send == 0) 
                    and (dc_count < nr_of_dcr_per_day or (slots_per_dc_cmd == 1 and dcr_left < days and bytes_to_send == 0))
                ):
                    if dc_count >= nr_of_dcr_per_day and (slots_per_dc_cmd == 1 and dcr_left < days and bytes_to_send == 0):
                        dcr_left -= 1
                    current_cmd = CMD_DATA_COLLECTION
                    slots_to_schedule = slots_per_dc_cmd
                    dev_per_slot = packets_per_dc_window
                    dev_ids = [x for x in range(1, number_of_devices)]
                    data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                    if (number_of_devices - 1) == slots_to_schedule:
                        bytes_scheduled = max([dev_stats[x]['b'] for x in dev_stats])
                    bytes_scheduled += self.config['lora']['payload_size']
                    
                    if balance_energy:
                        data = _balance_slots(dc_balanced_list_of_devs, True)
                    else:
                        for x in dev_ids[:dev_per_slot]:
                            dev_stats[x]['c'] += 1
                            dev_stats[x]['b'] += self.config['lora']['payload_size']
                    dc_slots = _count_slots(dc_slots, slots_to_schedule, data)
                    slots_to_schedule -= 1
                    dc_count += 1
                    dc_total_count += 1
                else:
                    current_cmd = CMD_SYNC
                    data = str(current_delay)
                    sync_free_slots.append(count)

                schedule[count] = {PAYLOAD.SEQ: count, PAYLOAD.CMD: current_cmd, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: 0}
                previous_cmd = current_cmd
                count += 1

        # for id in dev_stats:
        #     print(f'[{id}]: {dev_stats[id]} -> {bytes_to_send}')

        shuffle(sync_free_slots)
        dcr_left = 0
        for slot in dc_slots:
            dcr_left += dcr_packets_count - dc_slots[slot]['count']
            dc_slots[slot]['dcr_left'] = dcr_packets_count - dc_slots[slot]['count']

        if dcr_left <= len(sync_free_slots) and dcr_left > 0:
            for slot in dc_slots:
                dcr_left = dc_slots[slot]['dcr_left']
                for x in range(0, dcr_left):
                    dc_slots[slot]['count'] += 1
                    cmd_nr = sync_free_slots.pop()
                    data = dc_slots[slot]['devs']
                    if balance_energy:
                        data = _balance_slots(dc_balanced_list_of_devs, True)
                    else:
                        for x in dev_ids[:dev_per_slot]:
                            dev_stats[x]['c'] += 1
                            dev_stats[x]['b'] += self.config['lora']['payload_size']
                    schedule[cmd_nr] = {PAYLOAD.SEQ: cmd_nr, PAYLOAD.CMD: CMD_DATA_COLLECTION, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: 0}
                
                dc_slots[slot]['dcr_left'] = 0

        if self.config['general']['save_schedule_to_file']:
            file_name = f'{self.config["general"]["dir_path"]}/schedule.txt'
            f = open(file_name, 'a')

            count = 0
            for cmd_nr in schedule:
                if cmd_nr == 0:
                    f.write(f'Day: {count}\n')
                    count += 1

                if cmd_nr - 1 in days_separator:
                    f.write(f'\nDay: {count}\n')
                    count += 1
                packet = schedule[cmd_nr]
                info = f'[{cmd_nr:3}]: {packet[PAYLOAD.CMD]} | {current_delay} | {packet[PAYLOAD.DATA]:30} | {packet[PAYLOAD.NR_OF_RET]}'
                f.write(f'{info}\n')

            f.close()

        print(f'[SYNC]: {days + len(sync_free_slots)}')

        if len(d_slots) == 0:
            raise RuntimeError(f'Problem with DISC schedule: not a single DISC scheduled!')

        for slot in d_slots:
            print(f'[DISC][{d_slots[slot]["devs"]:30}]: {d_slots[slot]["count"]} | {days}')
            if d_slots[slot]['count'] != days:
                raise RuntimeError(f'Problem with DISC schedule: [{d_slots[slot]["devs"]}][{d_slots[slot]["count"]}] vs {days}')

        if len(dc_slots) == 0:
            raise RuntimeError(f'Problem with DC schedule: not a single DC scheduled!')

        for id in dev_stats:
            print(f'[DCOL][{id}]: {dev_stats[id]["c"]} | {dcr_packets_count} || {dev_stats[id]["b"]} -> {bytes_to_send}')
            if dev_stats[id]['b'] < bytes_to_send or dev_stats[id]['c'] != dcr_packets_count:
                raise RuntimeError(f'Problem with DC schedule: [{id}][{dev_stats[id]["c"]}] vs {dcr_packets_count}')

        return schedule

    def generate_schedule_for_wcm_data_simple(self, sim_seconds, number_of_devices, bytes_to_send, balance_energy=True):
        days = int(sim_seconds / 86400)
        days = days if days > 0 else 1
        toa_dc_ms = math.ceil(self.toa.get_time_on_air(self.config['lora']['payload_size']) * self.config['general']['second_in_unit'])
        toa_disc_ms = math.ceil(self.toa.get_time_on_air(len(f'{number_of_devices + 1}#{self.config["general"]["max_packet_nr"]}#{CMD_DISC_REPLY}#{self.rx_sensitivity}.00#0'.encode('utf8'))) * self.config['general']['second_in_unit'])
        rec_dcw = math.ceil((toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        rec_dw = math.ceil((toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']) * (number_of_devices + 1) / self.config['general']['second_in_unit'])
        c_dcw = self.config['wcm']['dc_window_s'] 
        c_dw = self.config['wcm']['disc_window_s']
        uses_rec_settings = True if c_dcw == rec_dcw and c_dw == rec_dw else False

        if not uses_rec_settings:
            print(f'Recommended dw: {rec_dw}s, dcw: {rec_dcw}s')

        delay_s = self.config['wcm']['send_interval_s']
        nr_of_cmd = math.floor((sim_seconds - self.config['wcm']['first_op_at_s']) / delay_s)

        packets_per_disc_window = math.floor(self.config['wcm']['disc_window_s'] * self.config['general']['second_in_unit'] / (toa_disc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))
        packets_per_dc_window =  math.floor(self.config['wcm']['dc_window_s'] * self.config['general']['second_in_unit'] / (toa_dc_ms + self.config['wcl']['reply_gt_ms'] + self.config['radio']['mode_change_ms']))

        current_cmd = CMD_SYNC
        current_delay = delay_s
        dev_per_slot = 0
        data = ''
        schedule = {}
        dev_ids = [x for x in range(1, number_of_devices)]
        d_slots = 0
        dc_slots = 0
        sync_free_slots = []

        def _balance_slots(cyclic_dev_list, dc=False):
            new_order = next(cyclic_dev_list)

            return ','.join([str(x) for x in new_order])

        def _balance_devs(cnt, devs):
            all = []
            for d in devs:
                all += d
            # new_order = [all[-1]] + all[:-1]
            new_order = all[1:] + all[:1]

            nr_slots = len(cnt) - 1
            dev_assigned = 0
            for i in range(0, len(cnt)):
                if i == 0:
                    devs[i] = new_order[:cnt[i]]
                elif i == nr_slots:
                    devs[i] = new_order[dev_assigned:]
                else:
                    devs[i] = new_order[dev_assigned:dev_assigned + cnt[i]]

                dev_assigned += len(devs[i])

            return devs

        def _get_balanced_list_of_devs(slots_per_window):
            it = 1
            iit = 0
            cyclic_devs = []
            condition = []
            is_gen_done = False
            all_devs = [x for x in range(1, number_of_devices)]
            # slots_to_schedule = slots_per_dc_cmd
            devs = []
            cnt = []
            while len(all_devs) > 0:
                slot_devs = all_devs[:slots_per_window]
                cnt.append(len(slot_devs))
                devs.append(slot_devs)
                del all_devs[:slots_per_window]
            
            while True:
                iit = 1
                for dev in devs:
                    if it == 1 and len(condition) == 0:
                        condition = dev
                    if it > 1 and condition == dev and iit == 1:
                        is_gen_done = True
                        break
                    cyclic_devs.append(dev)
                    iit += 1
                if is_gen_done:
                    break
                it += 1
                devs = _balance_devs(cnt, devs)
            
            return cyclic_devs

        d_balanced_list_of_devs = cycle(_get_balanced_list_of_devs(packets_per_disc_window))
        dc_balanced_list_of_devs = cycle(_get_balanced_list_of_devs(packets_per_dc_window))

        for cmd_nr in range(0, nr_of_cmd + 1):
            if cmd_nr % 3 == 0:
                current_cmd = CMD_SYNC
                data = str(current_delay)
            elif cmd_nr % 3 == 1:
                current_cmd = CMD_DISC
                dev_per_slot = packets_per_disc_window
                dev_ids = [x for x in range(1, number_of_devices)]
                data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                if balance_energy:
                    data = _balance_slots(d_balanced_list_of_devs)
                d_slots += 1
            elif cmd_nr % 3 == 2:
                current_cmd = CMD_DATA_COLLECTION
                del dev_ids[:dev_per_slot]
                data = ','.join([str(x) for x in dev_ids[:dev_per_slot]])
                if balance_energy:
                    data = _balance_slots(dc_balanced_list_of_devs, True)
                dc_slots += 1

            schedule[cmd_nr] = {PAYLOAD.SEQ: cmd_nr, PAYLOAD.CMD: current_cmd, PAYLOAD.DATA: data, PAYLOAD.NR_OF_RET: 0}

        if self.config['general']['save_schedule_to_file']:
            file_name = f'{self.config["general"]["dir_path"]}/schedule.txt'
            with open(file_name, 'a') as f:
                for cmd_nr in schedule:
                    packet = schedule[cmd_nr]
                    info = f'[{cmd_nr:3}]: {packet[PAYLOAD.CMD]} | {current_delay} | {packet[PAYLOAD.DATA]:30} | {packet[PAYLOAD.NR_OF_RET]}'
                    f.write(f'{info}\n')

        print(f'[SYNC]: {days + len(sync_free_slots)}')

        if d_slots== 0:
            raise RuntimeError(f'Problem with DISC schedule: not a single DISC scheduled!')

        if dc_slots == 0:
            raise RuntimeError(f'Problem with DC schedule: not a single DC scheduled!')

        return schedule

    def get_longest_possible_interval_for_lwan(self, sim_seconds, bytes_to_send):
        if bytes_to_send > 0:
            paktes_count = math.floor(bytes_to_send / self.config['lora']['payload_size'])
            toa_s = self.toa.get_time_on_air(self.config['lora']['payload_size'])
            toa_ms = toa_s * self.config['general']['second_in_unit']
            delay_ms = math.ceil(toa_ms / self.subbands[self.tx_params['band']][2])
            nr_pkts = math.ceil(sim_seconds * self.config['general']['second_in_unit'] / delay_ms)

            if paktes_count > nr_pkts:
                raise RuntimeError('Defined bytes_to_send impossible to transmit within a given amount of time')

            if paktes_count < nr_pkts:
                delay_ms = math.floor(sim_seconds * self.config['general']['second_in_unit'] / (paktes_count + 1))

            delay_s = math.ceil(delay_ms / self.config['general']['second_in_unit'])
        else:
            delay_s = self.config['lwaned']['send_interval_s']

        return delay_s

    def generate_schedule_for_lwan(self, dev, sim_seconds, number_of_devices, bytes_to_send):
        schedule = {}
        
        payload = ''.join(choice(ascii_uppercase) for i in range(self.config['lora']['payload_size']))
        if bytes_to_send > 0:
            paktes_count = math.ceil(bytes_to_send / self.config['lora']['payload_size'])
            toa_s = self.toa.get_time_on_air(self.config['lora']['payload_size'])
            toa_ms = toa_s * self.config['general']['second_in_unit']
            delay_ms = math.ceil(toa_ms / dev.lora_band.duty_cycle)
            nr_pkts = math.ceil(sim_seconds * self.config['general']['second_in_unit'] / delay_ms)

            if paktes_count > nr_pkts:
                raise RuntimeError('Defined bytes_to_send impossible to transmit within a given amount of time')

            if paktes_count < nr_pkts:
                delay_ms = math.floor(sim_seconds * self.config['general']['second_in_unit'] / (paktes_count + 1))

            print(f'Calculated delay for the specified amount ({bytes_to_send}B) of data: {delay_ms}s!')
        else:
            delay_ms = self.config['lwaned']['send_interval_s'] * self.config['general']['second_in_unit']
            paktes_count = math.ceil(sim_seconds * self.config['general']['second_in_unit'] / delay_ms)

        if self.config['general']['save_schedule_to_file']:
            file_name = f'{self.config["general"]["dir_path"]}/schedule_ed_{dev.id}.txt'
            f = open(file_name, 'a')

        delay_s = math.ceil(delay_ms / self.config["general"]["second_in_unit"])
        total_bytes = 0
        scheduled_bytes = 0
        for i in range(0, paktes_count):
            tmp_payload = payload
            total_bytes += len(tmp_payload)

            if bytes_to_send > 0 and total_bytes > bytes_to_send:
                diff = total_bytes - bytes_to_send
                tmp_payload = ''.join(choice(ascii_uppercase) for i in range(self.config['lora']['payload_size'] - diff))

            info = f'[{i:3}]: {delay_s} | {payload:15}'
            if self.config['general']['save_schedule_to_file']:
                f.write(f'{info}\n')
            schedule[i] = {PAYLOAD.SEQ: i, PAYLOAD.DATA: tmp_payload}
            scheduled_bytes += len(tmp_payload)

        if self.config['general']['save_schedule_to_file']:
            f.close()

        print(f'[LWANED_{dev.id}]: scheduled {scheduled_bytes}B to send')

        return delay_s, schedule