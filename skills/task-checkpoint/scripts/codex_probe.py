#!/usr/bin/env python3
"""Read-only, bounded Codex app-server probe. Never starts a model turn."""
import json
import os
import queue
import subprocess
import threading
import time

import checkpoint as cp


def probe(executable='codex', timeout=25, codex_home=None):
    environment = dict(os.environ)
    if codex_home is not None:
        environment['CODEX_HOME'] = str(codex_home)
    process = subprocess.Popen([executable, 'app-server', '--stdio'], stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, env=environment)
    messages = queue.Queue()

    def receive():
        for line in process.stdout:
            try:
                messages.put(json.loads(line))
            except ValueError:
                continue
        messages.put(None)

    threading.Thread(target=receive, daemon=True).start()
    deadline = time.monotonic() + timeout

    def send(value):
        process.stdin.write(json.dumps(value) + '\n')
        process.stdin.flush()

    def answer(ident):
        while time.monotonic() < deadline:
            try:
                value = messages.get(timeout=max(.01, deadline - time.monotonic()))
            except queue.Empty:
                break
            if value is None:
                raise cp.Fault('Codex probe ended before reply')
            if value.get('id') == ident:
                if 'error' in value:
                    raise cp.Fault('Codex read-only probe method unavailable')
                return value['result']
        raise cp.Fault('Codex read-only probe timed out')

    try:
        send({'id': 0, 'method': 'initialize', 'params': {'clientInfo': {
            'name': 'task_checkpoint', 'version': '0.8.1'}}})
        answer(0)
        send({'method': 'initialized', 'params': {}})
        send({'id': 1, 'method': 'account/rateLimits/read', 'params': {}})
        limits = answer(1)
        send({'id': 3, 'method': 'account/read', 'params': {}})
        account = answer(3)
        return {'observed_at': cp.now(), 'source': 'codex-app-server',
                'rate_limits': limits, 'account': account}
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        process.stdin.close()
        process.stdout.close()
