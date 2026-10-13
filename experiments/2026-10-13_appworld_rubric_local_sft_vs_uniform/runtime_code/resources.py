"""GPU availability guard; does not allocate memory or alter other processes."""
import csv
import io
import subprocess

def inventory():
    result = subprocess.run(['nvidia-smi', '--query-gpu=index,name,memory.total,memory.free',
                             '--format=csv,noheader,nounits'], capture_output=True, text=True, check=True)
    return [{'index': row[0].strip(), 'name': row[1].strip(), 'total_mib': int(row[2]), 'free_mib': int(row[3])}
            for row in csv.reader(io.StringIO(result.stdout))]

def require_free_gpu(index, minimum_gib):
    rows = inventory()
    match = next((row for row in rows if row['index'] == str(index)), None)
    if match is None:
        raise RuntimeError(f'Configured GPU {index} does not exist.')
    if match['free_mib'] < minimum_gib * 1024:
        raise RuntimeError(f'GPU {index} has {match["free_mib"] / 1024:.1f} GiB free; '
                           f'this experiment requires at least {minimum_gib} GiB before startup. '
                           'No existing GPU process was modified. Resume when the GPU is available.')
    return match
