import subprocess
import argparse
import shlex
import json
from pathlib import Path
from utils import natural_keys
from analyse import read_status
import re
from shutil import which

def compress(file_name, remove_log):
    with open(str(file_name), 'r') as f:
        config = json.load(f)
    sim_time = config['general']['sim_duration_s']

    log_file = file_name.replace('config.json', 'log.txt')
    stats_file = file_name.replace('config.json', 'stats.txt')
    if not Path(stats_file).is_file():
        # print(f'[{stats_file}]: does not exist! Creating new summary first...')
        log_path = file_name.replace('/config.json', '')
        log_name = 'log.txt'
        read_status(log_path, log_name, sim_time, True)

    bz2_log_file = file_name.replace('config.json', 'log.txt.bz2')
    if not Path(bz2_log_file).is_file():
        args = shlex.split(f"pbzip2 -v {log_file}")
        process = subprocess.run(args, capture_output=True)
        if len(process.stderr) > 0:
            try:
                input_size, output_size, wall_clock = _read_process_output(process)
            except RuntimeError:
                print(f'[{log_file}]: not compressed :(')
                return
            print(f'[{log_file}]: {round(input_size / 1024.0 / 1024.0, 2)}MB -> {round(output_size / 1024.0 / 1024.0, 2)}MB in {wall_clock}s.')
        else:
            print(f'[{log_file}]: not compressed :(')
    else:
        print(f'[{log_file}]: already compressed.')

    if Path(log_file).is_file():
        if remove_log:
            print(f'[{log_file}]: file exists...', end=' ')
            Path(log_file).unlink()
            print('removed!')
        else:
            print(f'[{log_file}]: file still exists. If you want to remove it run the command again with -f flag!')

def decompress(file_name, empty_flag=None):
    if not Path(file_name).is_file():
        print(f'[{file_name}]: does not exist!')
        return

    if not Path(file_name.replace('.bz2', '')).is_file():
        args = shlex.split(f"pbzip2 -v -k -d {file_name}")
        process = subprocess.run(args, capture_output=True)
        if len(process.stderr) > 0:
            try:
                input_size, output_size, wall_clock = _read_process_output(process)
            except RuntimeError:
                print(f'[{file_name}]: not decompressed :(')
                return
            print(f'[{file_name}]: {round(input_size / 1024.0 / 1024.0, 2)}MB -> {round(output_size / 1024.0 / 1024.0, 2)}MB in {wall_clock}s.')
    else:
        print(f'[{file_name}]: already decompressed.')

def _read_process_output(process):
    lines = process.stderr.decode('utf-8')
    lines = re.split('\r|\n', lines)
    lines = list(filter(None, lines))
    line = lines.pop()
    if line.find('Wall Clock') < 0:
        raise RuntimeError()
    
    line = re.sub(r'^\s+', '', line)
    wall_clock = round(float(line.replace('Wall Clock: ', '').replace(' seconds', '')), 2)

    input_size, output_size = [0, 0]
    for line in lines:
        if line.find('Input Size') >= 0:
            line = re.sub(r'^\s+', '', line)
            input_size = float(line.replace('Input Size: ', '').replace(' bytes', ''))
            continue

        if line.find('Output Size') >= 0:
            line = re.sub(r'^\s+', '', line)
            output_size = float(line.replace('Output Size: ', '').replace(' bytes', ''))
            continue

    return input_size, output_size, wall_clock

if __name__ == '__main__':
    parser = argparse.ArgumentParser('Compress log files in a given directory')
    parser.add_argument('dir')
    parser.add_argument('-p', help='prefix')
    parser.add_argument('-d', help='decompress', action='store_true')
    parser.add_argument('-f', help='Removes the log file if compressed and still remains in a given directory', action='store_true')
    args = parser.parse_args()

    if which('pbzip2') is None:
        raise RuntimeError(f'You need to install pbzip2 to run this script!')

    status = {}
    dirs = []
    if not args.d:
        for path in Path(args.dir).rglob('config.json'):
            dirs.append('/'.join(x for x in path.parts))
        f = compress
    else:
        for path in Path(args.dir).rglob('log.txt.bz2'):
            dirs.append('/'.join(x for x in path.parts))
        
        f = decompress
        
    dirs.sort(key=natural_keys)
    pattern = f'{args.dir}/{args.p}'.replace('//', '/') if args.p is not None else False
    for file_name in dirs:
        if pattern and file_name.find(pattern) == 0:
            f(file_name, args.f)
        elif not pattern:
            f(file_name, args.f)