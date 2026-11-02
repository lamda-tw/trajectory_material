"""Infrastructure recovery only: preserve prompts, labels, and all attempt evidence."""
import os
import signal
import subprocess

from b_common import read


class JudgeTransportUnavailable(RuntimeError):
    """The supervisor may retry this batch after a network cooldown."""


def transient_transport(folder, item):
    if item.get('failure_type') != 'transport':
        return False
    evidence = [item.get('error', '')]
    for name in ('stderr.log', 'events.jsonl'):
        path = folder / name
        if path.exists():
            with path.open('rb') as stream:
                stream.seek(max(0, path.stat().st_size - 200000))
                evidence.append(stream.read().decode(errors='replace'))
    text = '\n'.join(evidence).lower()
    # Authentication, exhausted quota, and invalid requests require diagnosis.
    if any(x in text for x in ('unauthorized', 'invalid_api_key', 'insufficient_quota',
                               'usage limit', 'quota exceeded', 'permission denied',
                               'authentication failed', 'invalid request', 'http 401', 'http 403')):
        return False
    return any(x in text for x in ('timed out', 'timeout', 'connection reset',
        'connection refused', 'connection closed', 'connection error', 'remote disconnected',
        'stream disconnected', 'temporary failure in name resolution',
        'network is unreachable', 'service unavailable', 'bad gateway', 'gateway timeout'))


def retryable_request(dest, meta):
    attempts = meta.get('attempts', [])
    start = meta.get('transport_round_start', 0)
    # Never reset semantic repair/protocol failures or re-sample an accepted answer.
    return (bool(attempts[start:])
            and all(a.get('failure_type') == 'transport' for a in attempts)
            and all(transient_transport(dest / a['directory'], a) for a in attempts[start:]))


def batch_network_retryable(folder):
    failed = []
    for path in (folder / 'judging').glob('*/metadata.json'):
        meta = read(path)
        if meta.get('status') == 'failed':
            failed.append(retryable_request(path.parent, meta))
    return bool(failed) and all(failed)


def run_request(cmd, *, input, stdout, stderr, env, cwd, timeout):
    # Codex's launcher spawns a native child. Kill the owned process group on timeout,
    # otherwise a detached child can keep writing while another attempt is started.
    with subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True, stdout=stdout, stderr=stderr,
                          env=env, cwd=cwd, start_new_session=True) as process:
        try:
            process.communicate(input=input, timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass
            finally:
                # A child can survive SIGTERM even if the wrapper already exited.
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise
        return subprocess.CompletedProcess(cmd, process.returncode)
