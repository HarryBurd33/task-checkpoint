#!/usr/bin/env python3
"""Compatibility for previously registered hooks: always allow tool use.

0.8 does not install hooks. Old registrations can be removed with account.py
uninstall; even cached definitions cannot restore the old pause machinery.
"""
import json


def main(*args, **kwargs):
    return {}


if __name__ == '__main__':
    print(json.dumps(main()))
