"""Owned macOS local text adapter. Reuses the existing runtime, not another queue."""
import json
import os
from pathlib import Path
import sys

import checkpoint as cp
from local_text_worker import endpoint


def command(worker, scratch):
    if sys.platform != 'darwin':
        raise cp.Fault('Local text confinement is verified only on macOS')
    if worker.get('provider') != 'ollama' or worker.get('billing') != 'local' or worker.get('tools'):
        raise cp.Fault('Local adapter permits only tool-free local Ollama text tasks')
    host = endpoint(worker['endpoint']); port = __import__('urllib.parse', fromlist=['urlsplit']).urlsplit(host).port
    source = Path(__file__).with_name('local_text_worker.py').resolve()
    roots = ['/System', '/usr/lib', '/usr/share', '/Library/Apple', str(Path(sys.base_prefix).resolve()), str(Path(sys.executable).resolve().parent.parent)]
    quote = lambda p: json.dumps(str(p))
    read = '\n'.join('(allow file-read* (subpath ' + quote(p) + '))' for p in roots)
    policy = ('(version 1)\n(deny default)\n(allow process-exec process-fork)\n'
              '(allow sysctl-read mach-lookup file-read-metadata)\n'
              '(allow file-read* (literal "/") (literal "/dev/urandom") (literal "/dev/random") (literal "/dev/null") (literal ' + quote(source) + '))\n'
              '(allow file-write* (literal "/dev/null"))\n' + read + '\n'
              '(allow network-outbound (remote ip "localhost:' + str(port) + '"))\n')
    environment = {'PATH': '/usr/bin:/bin', 'HOME': str(scratch), 'TMPDIR': str(scratch),
                   'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'LANG': 'en_US.UTF-8'}
    return ['/usr/bin/sandbox-exec', '-p', policy, sys.executable, '-I', '-B', str(source)], environment


def request(worker, task):
    if task['routing']['required_tools']:
        raise cp.Fault('Local text task cannot request tools')
    return json.dumps({'prompt': task['objective'], 'model': worker['model'],
                       'model_digest': worker['model_digest'], 'endpoint': worker['endpoint'], 'output_schema': task['routing'].get('output_schema')})


def result(log, output):
    if log.stat().st_size > 131072:
        raise cp.Fault('Local worker output exceeds bound')
    value = json.loads(log.read_text())
    cp.atomic(output, value['answer'].encode())
    return {k: value.get(k) for k in ('model', 'model_digest', 'prompt_tokens', 'completion_tokens',
                                    'eval_ns', 'load_ns', 'paid_api_cost_usd', 'electricity_cost')}
