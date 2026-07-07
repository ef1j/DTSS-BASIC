"""Regenerate dbasic2.py (Python 2.7 fork) from dbasic.py."""

HEAD = '''#!/usr/bin/env python2
"""
dbasic2.py -- Python 2.7 fork of dbasic.py, for legacy machines.

An interpreter for Dartmouth BASIC, Fourth Edition (1968).  This file is
a maintained-in-parallel fork of dbasic.py (the primary, Python 3
version) with small compatibility shims so it runs under Python 2.7 on
machines without python3.  It also runs unmodified under Python 3 and
must always produce byte-identical output to dbasic.py (the test suite
checks this: tests/test_dbasic.py, Python2Fork).

This file is generated from dbasic.py by a mechanical transform; edit
dbasic.py and regenerate (or mirror the change by hand).

Usage:
    python2 dbasic2.py PROGRAM         batch mode: run PROGRAM, output to stdout
    python2 dbasic2.py                 interactive DTSS-style session
    python2 dbasic2.py --library DIR   override the program library directory

Python 2.7 or 3.x, standard library only.

See README.md for the DEVIATIONS list (every intentional departure from
the 1968 manual) and a provenance note.
"""

from __future__ import division, print_function
'''

SHIMS = '''
try:                            # Python 2.7 compatibility
    input = raw_input           # noqa: F821  (input() evaluates on Py2)
except NameError:
    pass

try:
    _cpu_time = time.process_time
except AttributeError:          # Python 2.7
    _cpu_time = time.clock


def _time_seed():
    try:
        return time.time_ns()
    except AttributeError:      # Python 2.7
        return int(time.time() * 1e9)

'''

with open('dbasic.py') as f:
    src = f.read()

# replace the shebang + module docstring with the fork's header
parts = src.split('"""', 2)
assert len(parts) == 3, 'expected a module docstring'
body = parts[2]

# insert the compatibility shims right after the import block
marker = '\nimport time\n'
assert marker in body
body = body.replace(marker, marker + SHIMS, 1)

# Python 2.7 substitutions (each must occur exactly once, except iround note)
subs = [
    ('super().__init__(msg)', 'super(BasicError, self).__init__(msg)', 1),
    ('t0 = time.process_time()', 't0 = _cpu_time()', 1),
    ('(time.process_time() - t0)', '(_cpu_time() - t0)', 1),
    ('time.time_ns() % (RND_M - 2)', '_time_seed() % (RND_M - 2)', 1),
    ('        os.makedirs(self.libdir, exist_ok=True)',
     '        if not os.path.isdir(self.libdir):\n'
     '            os.makedirs(self.libdir)', 1),
    ('subscripts deterministic and identical to the dbasic2.py fork.',
     'subscripts deterministic and identical to dbasic.py.', 1),
]
for old, new, count in subs:
    assert body.count(old) == count, 'expected %d of %r, found %d' % (
        count, old, body.count(old))
    body = body.replace(old, new)

with open('dbasic2.py', 'w') as f:
    f.write(HEAD + body)
print('dbasic2.py regenerated')
