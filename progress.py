import time
import subprocess
import select
import os
import argparse
import shlex
import json
import math
from pathlib import Path
from utils import bcolors, natural_keys


def printProgressBar (iteration, total, prefix = '', suffix = '', decimals = 1, length = 100, fill = '█', printEnd = "\r"):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + '-' * (length - filledLength)
    print(f'\r{prefix:80s} |{bar}| {percent}% {suffix}', end = printEnd)


def readStatus(filename, sim_seconds, nr, total_count):
    args = shlex.split(f'tail -n 2 {filename}')

    f = subprocess.Popen(args, stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    p = select.poll()
    p.register(f.stdout)

    last_line = None
    if p.poll(100):
        last_line = f.stdout.readline()
        # time.sleep(1)

    is_stats_file = True if filename.find('stats.txt') >= 0 else False

    finished = False
    failed = False
    interrupted = False
    last_line = last_line.decode('utf8').replace('\n', '').replace('\r', '')
    if last_line.find('Execution time') >= 0:
        finished = True

    if last_line.find('Simulation failed!') >= 0 or len(last_line) == 0 or last_line.find('[41mExecution time') >= 0:
        failed = True

    if last_line.find('Simulation interrupted!') >= 0:
        interrupted = True
    
    last_line = last_line.split('s')
    # print(last_line)
    if finished:
        execution_time = last_line[1].replace('\t\x1b[42mExecution time: ', '').replace('\t\x1b[41mExecution time: ', '')
        if is_stats_file:
            execution_time = last_line[0].replace('Execution time: ', '')
        execution_time = int(execution_time)
    
    if is_stats_file:
        last_line = sim_seconds
    elif len(last_line[0]) > 0:
        last_line = last_line[0].split('.')[0]
        last_line = last_line.replace(',', '')
    else:
        last_line = 0
    
    if not finished and not failed and not interrupted:
        eta = -1
        timestamp = int(time.time())
        percent = round(100 * (int(last_line) / float(sim_seconds)), 1)
        status_filename = filename.replace('log.txt', 'status.json')
        if not os.path.isfile(status_filename):
            status = {'t': timestamp, 'p': percent}
            with open(status_filename, 'w') as outfile:
                outfile.write(json.dumps(status, indent=4))
        else:
            with open(status_filename, 'r') as f:
                status = json.load(f)
            if timestamp - status['t'] > 60:
                seconds = timestamp - status['t']
                percent_diff = percent - status['p']
                ratio = round(seconds / percent_diff * 0.1, 1)
                percent_to_finish = 100.0 - percent
                eta = round(percent_to_finish * 10 * ratio, 0)

    if finished and not failed:
        printProgressBar(int(last_line), int(sim_seconds), prefix=f'[{nr:3d}/{count:3d}] {filename}{bcolors.OKGREEN}', printEnd=f' {round(execution_time / 60, 1)}m {bcolors.ENDC}\n')
    elif finished and failed:
        printProgressBar(int(last_line), int(sim_seconds), prefix=f'{bcolors.FAIL}[{nr:3d}/{count:3d}] {filename}', printEnd=f' {round(execution_time / 60, 1)}m {bcolors.ENDC}\n')
    elif failed or interrupted:
        color = bcolors.FAIL if failed else bcolors.WARNING
        printProgressBar(int(last_line), int(sim_seconds), prefix=f'{color}[{nr:3d}/{count:3d}] {filename}', printEnd=f'{bcolors.ENDC}\n')
    else:
        eta_str = ''
        if eta > 0:
            eta_pre = math.floor(eta / 60)
            eta_post = int(eta % 60)
            eta_str = f'{bcolors.OKBLUE}  ETA: {eta_pre}m {eta_post}s'
        printProgressBar(int(last_line), int(sim_seconds), prefix=f'[{nr:3d}/{count:3d}] {filename}{bcolors.WHITE}', printEnd=f'{eta_str}{bcolors.ENDC}\n')

if __name__ == '__main__':
    parser = argparse.ArgumentParser('Prints progress of multiple simulations')
    parser.add_argument('dir')
    parser.add_argument('-p', help='prefix')
    args = parser.parse_args()

    status = {}
    dirs = []
    for path in Path(args.dir).rglob('config.json'):
        dirs.append('/'.join(x for x in path.parts))

    def _doReadStatus(file_name, nr, count):
        with open(str(file_name), 'r') as f:
            config = json.load(f)
        sim_time = config['general']['sim_duration_s']

        log_file = file_name.replace('config.json', 'log.txt')
        log_path = Path(log_file)
        stats_file = file_name.replace('config.json', 'stats.txt')
        stats_path = Path(stats_file)
        file_to_process = None
        if stats_path.is_file() and stats_path.stat().st_size > 0:
            file_to_process = stats_file
        elif log_path.is_file() and log_path.stat().st_size > 0:
            file_to_process = log_file

        if file_to_process is not None:
            readStatus(file_to_process, sim_time, nr, count)

    # dirs = sorted(dirs)
    dirs.sort(key=natural_keys)
    pattern = f'{args.dir}/{args.p}'.replace('//', '/') if args.p is not None else False
    to_process = []
    for file_name in dirs:
        if pattern and file_name.find(pattern) == 0:
            to_process.append(file_name)
        elif not pattern:
            to_process.append(file_name)

    count = len(to_process)
    i = 1
    for file_name in to_process:
        _doReadStatus(file_name, i, count)
        i += 1
        


