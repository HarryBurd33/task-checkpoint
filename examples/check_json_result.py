#!/usr/bin/env python3
"""Independent strict JSON oracle. No inference, network or model instructions."""
import json
import os
from pathlib import Path
import sys


def parse(text):
    def unique(items):
        result={}
        for key,value in items:
            if key in result:raise ValueError('Duplicate JSON key')
            result[key]=value
        return result
    return json.loads(text,object_pairs_hook=unique,parse_constant=lambda x: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


if __name__=='__main__':
    actual=parse(Path(os.environ['CHECKPOINT_RESULT']).read_text())
    expected=parse(Path(sys.argv[1]).read_text())
    if json.dumps(actual,sort_keys=True,separators=(',',':')) != json.dumps(expected,sort_keys=True,separators=(',',':')):
        raise SystemExit('Exact independent JSON acceptance failed')
