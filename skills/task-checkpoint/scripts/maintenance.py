#!/usr/bin/env python3
"""Read-only recovery bootstrap, available while ordinary task work is stopped."""
import argparse
import contextlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys

import checkpoint as cp

SCRIPTS = Path(__file__).resolve().parent
SKILL = SCRIPTS.parent
DOCS = {
    'task-checkpoint': SKILL / 'SKILL.md',
    'model-switcher': Path.home() / '.agents/skills/model-switcher/SKILL.md',
    'operator': SKILL / 'references/operator.md',
    'reserve': SKILL / 'references/reserve.md',
    'readme': SKILL / 'README.md',
}
VERBS = {
    'checkpoint.py': {'inspect', 'verify', 'policy', 'checkpoint', 'resume',
                      'owner-check', 'release', 'recover-previous', 'refresh-handoff'},
    'reserve.py': {'status', 'grant', 'prepare-review', 'revoke', 'configure', 'retire-policy'},
    'maintenance.py': {'status', 'docs', 'signals'},
}


def build_parser():
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--account-state', type=Path)
    sub = p.add_subparsers(dest='command', required=True)
    sub.add_parser('status')
    sub.add_parser('signals')
    doc = sub.add_parser('docs'); doc.add_argument('--name', choices=sorted(DOCS), required=True)
    return p


def next_command(root, account_state=None):
    args = ['python3', str(SCRIPTS / 'maintenance.py'), '--root', str(root)]
    if account_state:
        args += ['--account-state', str(account_state)]
    return shlex.join(args + ['status'])


def _canonical(value):
    path = Path(value)
    if not path.is_absolute() or str(path) != str(path.resolve()) or '..' in path.parts:
        raise ValueError('Use a literal absolute canonical path (no symlinks or traversal)')
    return path


def _parser(script):
    if script == 'checkpoint.py':
        parser = cp.build_parser()
    elif script == 'reserve.py':
        import reserve
        parser = reserve.build_parser()
    else:
        parser = build_parser()
    def exact(p):
        p.allow_abbrev = False
        for action in p._actions:
            if isinstance(action, argparse._SubParsersAction):
                for child in action.choices.values():
                    exact(child)
    exact(parser)
    return parser


def classify(event, root, account_state=None):
    """Return (allowed, reason); parse data only, never execute a shell here."""
    name = event.get('tool_name', '').removeprefix('tools.')
    if name in ('mcp__codex_app__get_usage_limits', 'mcp__codex_app.get_usage_limits'):
        return True, 'quota read'
    if re.sub(r'[^a-z0-9]', '', name.lower()) not in ('execcommand', 'functionsexeccommand', 'toolsexeccommand', 'bash'):
        return False, 'ordinary tool name=' + repr(name) + '; maintenance uses exec_command'
    inputs = event.get('tool_input', {})
    if isinstance(inputs, dict) and inputs.get('shell') is not None:
        return False, 'invalid maintenance scope: shell overrides are not allowed'
    command = inputs.get('cmd', inputs.get('command')) if isinstance(inputs, dict) else None
    if not isinstance(command, str) or any(c in command for c in (';', '&', '|', '>', '<', '`', '$', '\n', '\r', '\x00', '*', '?')):
        return False, 'invalid maintenance syntax: shell expansion, chains and redirects are not supported'
    try:
        argv = shlex.split(command)
        if not argv:
            raise ValueError('empty command')
        if argv[0] in ('cat', '/bin/cat', '/usr/bin/cat'):
            chosen = shutil.which(argv[0]) if argv[0] == 'cat' else argv[0]
            if not chosen or Path(chosen).resolve() not in {Path('/bin/cat').resolve(), Path('/usr/bin/cat').resolve()}:
                raise ValueError('untrusted instruction reader')
            if len(argv) != 2 or _canonical(argv[1]) not in set(DOCS.values()):
                raise ValueError('cat is limited to one named installed recovery instruction file')
            if not _canonical(argv[1]).is_file():
                raise ValueError('recovery instruction file is unavailable')
            return True, 'installed recovery instructions'
        if not re.fullmatch(r'python(?:[0-9]+(?:\.[0-9]+)*)?', Path(argv[0]).name):
            return False, 'ordinary command; only installed recovery scripts are exempt'
        chosen = shutil.which(argv[0]) if Path(argv[0]).name == argv[0] else argv[0]
        trusted = {Path(sys.executable).resolve()}
        # macOS /usr/bin/python3 is an OS launcher: sys.executable becomes
        # the CommandLineTools framework path, so Path.resolve alone differs.
        if sys.platform == 'darwin' and Path('/usr/bin/python3').is_file():
            trusted.add(Path('/usr/bin/python3').resolve())
        for runtime in ('python3', 'python'):
            found = shutil.which(runtime)
            if found:
                trusted.add(Path(found).resolve())
        if not chosen or Path(chosen).resolve() not in trusted:
            raise ValueError('untrusted Python interpreter')
        if len(argv) < 3:
            raise ValueError('script and command required')
        script = _canonical(argv[1])
        args = argv[2:]
        if script.parent != SCRIPTS:
            raise ValueError('script is outside the installed maintenance directory')
        if script.name == 'account.py':
            return _account_command(args, account_state)
        if script.name not in VERBS:
            raise ValueError('script is not a maintenance entry point')
        parser = _parser(script.name)
        # Help is read-only, including before a root is known. Its form is exact;
        # argparse alone would ignore arbitrary arguments after --help.
        if '--help' in args or '-h' in args:
            tail = list(args)
            if tail[:1] == ['--root']:
                if len(tail) < 3 or _canonical(tail[1]) != root:
                    raise ValueError('wrong maintenance workspace')
                tail = tail[2:]
            if len(tail) == 2:
                choices = next(a.choices for a in parser._actions if isinstance(a, argparse._SubParsersAction))
                if tail[0] not in choices:
                    raise ValueError('unknown subcommand; use top-level --help')
                tail = tail[1:]
            if tail not in (['--help'], ['-h']):
                raise ValueError('help must be standalone or follow one valid subcommand')
            return True, 'exact CLI help'
        flags = [a.split('=', 1)[0] for a in args if a.startswith('--')]
        if any(flags.count(f) > 1 for f in flags if f != '--capability'):
            raise ValueError('duplicate maintenance option')
        if args[:1] != ['--root'] or len(args) < 3 or _canonical(args[1]) != root:
            raise ValueError('use --root with the current canonical workspace before the subcommand')
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            try:
                parsed = parser.parse_args(args)
            except SystemExit:
                raise ValueError('invalid CLI arguments; use exact subcommand --help')
        verb = getattr(parsed, 'cmd', None) or getattr(parsed, 'command', None)
        if verb not in VERBS[script.name]:
            raise ValueError('ordinary execution or task setup is not maintenance')
        state_arg = getattr(parsed, 'account_state', None)
        if state_arg is not None and (account_state is None or _canonical(str(state_arg)) != account_state.resolve()):
            raise ValueError('foreign account-state directory')
        if script.name == 'maintenance.py':
            return True, 'read-only maintenance'
        binding, store = cp.config(root)
        store = store.resolve()
        if script.name == 'checkpoint.py' and verb in ('checkpoint', 'release', 'recover-previous', 'refresh-handoff'):
            if not getattr(parsed, 'owner', None):
                raise ValueError('mutating checkpoint maintenance requires explicit --owner')
        allowed_signals = {store / n for n in ('signals.json', 'allowance-override-signals.json')}
        if account_state is not None:
            allowed_signals.add(account_state.resolve() / 'signals.json')
        for field in ('signals', 'input', 'review'):
            raw = getattr(parsed, field, None)
            if raw is None:
                continue
            path = _canonical(str(raw))
            allowed = allowed_signals if field == 'signals' or verb == 'policy' else ({store / 'input.json'} if field == 'input' else {store / 'review.json', store / 'allowance-resume-review.json'})
            if path not in allowed:
                raise ValueError('out-of-scope ' + field + ' path')
        return True, 'validated maintenance arguments; runtime policy and ownership still apply'
    except (ValueError, IndexError, OSError, cp.Fault) as exc:
        return False, 'invalid maintenance syntax or scope: ' + str(exc)


def _account_command(args, account_state):
    if account_state is None or args[:1] != ['--state'] or len(args) < 3 or _canonical(args[1]) != account_state.resolve():
        raise ValueError('foreign account state')
    if args[2:] == ['status'] or args[2:] in (['--help'], ['status', '--help'], ['restore-hooks', '--help']):
        return True, 'account maintenance'
    if args[2:3] != ['restore-hooks'] or len(args) != 7 or set(args[3::2]) != {'--codex-home', '--backup'}:
        raise ValueError('invalid account maintenance arguments')
    values = dict(zip(args[3::2], args[4::2]))
    config = cp.read(account_state / 'config.json')
    if _canonical(values['--codex-home']) != Path(config['codex_home']).resolve():
        raise ValueError('foreign Codex home')
    backup = _canonical(values['--backup'])
    if backup.parent != account_state.resolve() or not re.fullmatch(r'hooks-temporary-backup-[A-Za-z0-9-]+\.json', backup.name):
        raise ValueError('unreviewed hook backup path')
    return True, 'exact managed hook restoration; runtime validates backup'


def status(root, account_state=None):
    import reserve
    binding, store = cp.config(root)
    try:
        saved, report = cp.inspect(root)
    except (cp.Fault, OSError, ValueError) as exc:
        # Diagnosis must stay available when current-worktree reconciliation
        # fails. Read the verified generation; do not weaken inspect/resume.
        saved, folder = cp.latest(store)
        report = {'checkpoint_id': saved['id'], 'task_id': saved['task_id'],
                  'next_action': saved['task']['next_action'], 'handoff': str(folder/'HANDOFF.md'),
                  'issues': ['current-worktree-inspection-failed: ' + str(exc)],
                  'current_fingerprint': None, 'implementation_allowed': False}
    ownership = cp.Ownership(root, binding, store)
    try:
        current = ownership.value(ownership.tip())
    except (cp.Fault, OSError, ValueError) as exc:
        current = {'owner': None, 'status': 'unknown', 'error': str(exc)}
    owner = {k: v for k, v in current.items() if k != 'token'}
    marker = cp.read(store / 'automatic-stop.json') if (store / 'automatic-stop.json').exists() else None
    journal = cp.read(store / 'router.json') if (store / 'router.json').exists() else {}
    try:
        policy = reserve.status(root)
    except (cp.Fault, OSError, ValueError) as exc:
        policy = {'status': 'invalid-or-unknown', 'error': str(exc), 'implementation_allowed': False}
    if policy.get('override'):
        policy['override'] = {k: v for k, v in policy['override'].items() if 'token' not in k}
    return {'workspace': str(root), 'binding': binding, 'checkpoint': report,
            'owner': owner, 'stop': marker, 'reserve': policy,
            'jobs': saved['task']['jobs'], 'worker': journal.get('active'),
            'implementation_allowed': False,
            'next': shlex.join(['python3', str(SCRIPTS/'maintenance.py'), '--root', str(root), 'docs', '--name', 'reserve']),
            'instruction': 'Confirm this is the intended task. A different task or owner must not be resumed to unblock repair.'}


def main():
    args = build_parser().parse_args()
    root = args.root.resolve()
    if args.command == 'docs':
        print(DOCS[args.name].read_text())
        return
    if args.command == 'signals':
        import telemetry
        _, store = cp.config(root)
        path = (args.account_state.resolve() if args.account_state else store) / 'signals.json'
        value = {'path': str(path), 'assessment': telemetry.assess(cp.read(path)),
                 'observed_at': cp.now(), 'shared_state_modified': False,
                 'next': 'If stale, use the supported get_usage_limits tool and let the existing collector refresh; never fabricate or overwrite shared readings.'}
    else:
        value = status(root, args.account_state)
    print(json.dumps(cp.redact(value), indent=2))


if __name__ == '__main__':
    try:
        main()
    except (cp.Fault, OSError, ValueError, KeyError, TypeError) as exc:
        print('Maintenance policy/state denial: ' + str(exc), file=sys.stderr)
        sys.exit(2)
