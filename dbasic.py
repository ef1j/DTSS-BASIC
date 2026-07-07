#!/usr/bin/env python3
"""
dbasic.py -- an interpreter for Dartmouth BASIC, Fourth Edition (1968).

A modern reimplementation of the BASIC language documented in
"BASIC, Fourth Edition" (Kemeny & Kurtz, Dartmouth College Computation
Center, 1 January 1968).  This is a language reimplementation, not an
emulation of the GE-235/DTSS hardware or operating system.

Usage:
    python3 dbasic.py PROGRAM          batch mode: run PROGRAM, output to stdout
    python3 dbasic.py                  interactive DTSS-style session
    python3 dbasic.py --library DIR    override the program library directory

Python 3.8+, standard library only.  A maintained-in-parallel Python 2.7
fork for legacy machines lives in dbasic2.py; when changing this file,
mirror the change there.

See README.md for the DEVIATIONS list (every intentional departure from
the 1968 manual) and a provenance note.
"""

import math
import os
import re
import sys
import time


def iround(v):
    """Round half away from zero.

    round() would be banker's rounding; an explicit rule keeps array
    subscripts deterministic and identical to the dbasic2.py fork.
    """
    return int(math.floor(v + 0.5))

WIDTH = 75            # teleprinter line: 75 columns (manual sec. 2.1)
ZONE = 15             # five print zones of 15 columns each
MAX_LINENO = 99999
AUTO_BOUND = 10       # arrays used without DIM: subscripts 0..10 (sec. 1.7.8)

# Repeatable random sequence: the manual (sec. 2.2) requires that two RUNs
# of the same program produce the same RND sequence.  We use a fixed-seed
# Lehmer generator so the sequence is also stable across Python versions.
RND_SEED = 12345
RND_A = 16807
RND_M = 2147483647

# The GE-635's number range (manual sec. 2.8): values beyond MAXNUM
# overflow (the machine "supplies infinity", i.e. +/-1.70141E+38, and
# continues); nonzero magnitudes below MINNUM underflow to 0.
MAXNUM = 1.70141e38
MINNUM = 1.46937e-39
EXP_MAX_ARG = 88.029      # EXP argument limit (manual sec. 2.8)


class BasicError(Exception):
    """A BASIC compile-time or runtime error."""

    def __init__(self, msg, line=None):
        super().__init__(msg)
        self.msg = msg
        self.line = line

    def report(self):
        if self.line is not None:
            return "%s IN %s" % (self.msg, self.line)
        return self.msg


class StopRun(Exception):
    """Raised by END / STOP to terminate execution."""


# ----------------------------------------------------------------------------
# Lexer
# ----------------------------------------------------------------------------

TOKEN_RE = re.compile(r'''
      (?P<ws>\s+)
    | (?P<num>(?:\d+\.?\d*|\.\d+)(?:E[+-]?\d+)?)
    | (?P<str>"[^"]*")
    | (?P<id>[A-Z][A-Z0-9]*\$?)
    | (?P<op><=|>=|<>|[#<>=+\-*/^(),;:])
''', re.X)


def tokenize(text, line=None):
    toks = []
    i, n = 0, len(text)
    while i < n:
        m = TOKEN_RE.match(text, i)
        if not m:
            raise BasicError("ILLEGAL CHARACTER '%s'" % text[i], line)
        i = m.end()
        if m.lastgroup == 'ws':
            continue
        val = m.group()
        if m.lastgroup == 'str':
            val = val[1:-1]
        toks.append((m.lastgroup, val))
    return toks


def upcase_outside_quotes(s):
    out, inq = [], False
    for ch in s:
        if ch == '"':
            inq = not inq
            out.append(ch)
        else:
            out.append(ch if inq else ch.upper())
    return ''.join(out)


def split_csv(text):
    """Split on commas that are not inside quoted strings."""
    parts, cur, inq = [], [], False
    for ch in text:
        if ch == '"':
            inq = not inq
            cur.append(ch)
        elif ch == ',' and not inq:
            parts.append(''.join(cur))
            cur = []
        else:
            cur.append(ch)
    parts.append(''.join(cur))
    return parts


# ----------------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------------

BUILTINS = {'SIN', 'COS', 'TAN', 'ATN', 'EXP', 'LOG', 'ABS', 'SQR', 'INT', 'SGN'}
NUMVAR_RE = re.compile(r'^[A-Z][0-9]?$')     # A, X, A0-Z9 (sec. 1.2)
STRVAR_RE = re.compile(r'^[A-Z]\$$')         # A$ (sec. 2.7)
FN_RE = re.compile(r'^FN[A-Z]$')             # FNA-FNZ (sec. 2.2)
RELOPS = ('<=', '>=', '<>', '<', '>', '=', '#')


class Parser:
    def __init__(self, toks, line=None):
        self.toks = toks
        self.i = 0
        self.line = line

    def at_end(self):
        return self.i >= len(self.toks)

    def peek(self):
        if self.at_end():
            return (None, None)
        return self.toks[self.i]

    def next(self):
        if self.at_end():
            raise BasicError("ILLEGAL FORMAT", self.line)
        t = self.toks[self.i]
        self.i += 1
        return t

    def accept_op(self, *ops):
        k, v = self.peek()
        if k == 'op' and v in ops:
            self.i += 1
            return v
        return None

    def accept_id(self, *names):
        k, v = self.peek()
        if k == 'id' and v in names:
            self.i += 1
            return v
        return None

    def expect_op(self, op):
        if not self.accept_op(op):
            raise BasicError("ILLEGAL FORMAT ('%s' EXPECTED)" % op, self.line)

    def expect_id(self, name):
        if not self.accept_id(name):
            raise BasicError("ILLEGAL FORMAT ('%s' EXPECTED)" % name, self.line)

    def expect_lineno(self):
        k, v = self.peek()
        if k != 'num' or not v.isdigit():
            raise BasicError("ILLEGAL LINE REFERENCE", self.line)
        self.i += 1
        n = int(v)
        if not 0 <= n <= MAX_LINENO:
            raise BasicError("ILLEGAL LINE NUMBER", self.line)
        return n

    def end_of_statement(self):
        if not self.at_end():
            k, v = self.peek()
            if k == 'op' and v == ':':
                raise BasicError("ONLY ONE STATEMENT ALLOWED PER LINE", self.line)
            raise BasicError("ILLEGAL FORMAT", self.line)

    # --- expressions ---------------------------------------------------
    # Precedence (sec. 1.2): ^  >  unary -  >  * /  >  + -

    def expression(self):
        n = self.term_mul()
        while True:
            op = self.accept_op('+', '-')
            if not op:
                return n
            n = ('bin', op, n, self.term_mul())

    def term_mul(self):
        n = self.unary()
        while True:
            op = self.accept_op('*', '/')
            if not op:
                return n
            n = ('bin', op, n, self.unary())

    def unary(self):
        if self.accept_op('-'):
            return ('neg', self.unary())
        if self.accept_op('+'):
            return self.unary()
        return self.power()

    def power(self):
        n = self.primary()
        while self.accept_op('^'):
            n = ('bin', '^', n, self.pow_operand())
        return n

    def pow_operand(self):
        if self.accept_op('-'):
            return ('neg', self.pow_operand())
        if self.accept_op('+'):
            return self.pow_operand()
        return self.primary()

    def primary(self):
        k, v = self.peek()
        if k == 'num':
            self.i += 1
            value = float(v)
            if value > MAXNUM:
                raise BasicError("ILLEGAL CONSTANT", self.line)
            return ('num', value)
        if k == 'str':
            self.i += 1
            return ('str', v)
        if k == 'op' and v == '(':
            self.i += 1
            n = self.expression()
            self.expect_op(')')
            return n
        if k == 'id':
            return self.name_ref()
        raise BasicError("ILLEGAL FORMULA", self.line)

    def name_ref(self):
        k, v = self.next()
        if v == 'RND':
            # RND takes no argument (sec. 2.2); a dummy argument, as in the
            # common RND(X) idiom of period programs, is accepted and ignored.
            if self.accept_op('('):
                self.expression()
                self.expect_op(')')
            return ('rnd',)
        if v == 'TAB':
            self.expect_op('(')
            n = self.expression()
            self.expect_op(')')
            return ('tab', n)
        if v in BUILTINS:
            self.expect_op('(')
            n = self.expression()
            self.expect_op(')')
            return ('fn', v, n)
        if FN_RE.match(v):
            args = []
            if self.accept_op('('):
                if not self.accept_op(')'):
                    args.append(self.expression())
                    while self.accept_op(','):
                        args.append(self.expression())
                    self.expect_op(')')
            return ('call', v, args)
        return self.variable_ref(v)

    def variable_ref(self, v):
        if STRVAR_RE.match(v):
            if self.accept_op('('):
                idx = self.expression()
                self.expect_op(')')
                return ('sel', v, idx)
            return ('svar', v)
        if NUMVAR_RE.match(v):
            if self.accept_op('('):
                idxs = [self.expression()]
                if self.accept_op(','):
                    idxs.append(self.expression())
                self.expect_op(')')
                return ('el', v, idxs)
            return ('var', v)
        raise BasicError("ILLEGAL VARIABLE '%s'" % v, self.line)

    def lvalue(self):
        k, v = self.next()
        if k != 'id':
            raise BasicError("ILLEGAL VARIABLE", self.line)
        node = self.variable_ref(v)
        if node[0] in ('var', 'el', 'svar', 'sel'):
            return node
        raise BasicError("ILLEGAL VARIABLE", self.line)

    def relop(self):
        k, v = self.peek()
        if k == 'op' and v in RELOPS:
            self.i += 1
            # tolerate split operators such as "> =" or "< >"
            if v == '>' and self.accept_op('='):
                v = '>='
            elif v == '<' and self.accept_op('='):
                v = '<='
            elif v == '<' and self.accept_op('>'):
                v = '<>'
            if v == '#':
                v = '<>'
            return v
        raise BasicError("ILLEGAL RELATION", self.line)


def parse_data_items(text, line):
    """Parse the raw text of a DATA statement into typed items.

    Strings are recognized by starting with a letter, or by quotes
    (manual sec. 2.7); everything else must be a number.
    """
    items = []
    for raw in split_csv(text):
        s = raw.strip()
        if not s:
            raise BasicError("ILLEGAL CONSTANT IN DATA", line)
        if s[0] == '"':
            if len(s) < 2 or not s.endswith('"'):
                raise BasicError("ILLEGAL CONSTANT IN DATA", line)
            items.append(('S', s[1:-1]))
            continue
        try:
            items.append(('N', float(s)))
        except ValueError:
            if s[0].isalpha():
                items.append(('S', s))
            else:
                raise BasicError("ILLEGAL CONSTANT '%s' IN DATA" % s, line)
    return items


def parse_statement(text, line):
    """Parse one statement (line-number already removed) into a tuple."""
    stripped = text.strip()
    if stripped.startswith('REM'):
        return ('REM',)
    toks = tokenize(text, line)
    if not toks:
        raise BasicError("ILLEGAL INSTRUCTION", line)
    p = Parser(toks, line)
    k, v = p.next()
    if k != 'id':
        raise BasicError("ILLEGAL INSTRUCTION", line)

    if v == 'DATA':
        # taken from the raw text: unquoted strings may contain spaces
        idx = text.upper().index('DATA') + 4
        return ('DATA', text[idx:])

    if v == 'LET':
        lv = p.lvalue()
        p.expect_op('=')
        ex = p.expression()
        p.end_of_statement()
        return ('LET', lv, ex)

    if v == 'READ':
        lvs = [p.lvalue()]
        while p.accept_op(','):
            lvs.append(p.lvalue())
        p.end_of_statement()
        return ('READ', lvs)

    if v in ('RESTORE', 'RESTORE$'):
        which = 'B'
        if v == 'RESTORE$':
            which = 'S'                      # RESTORE$: string data only
        elif p.accept_op('*'):
            which = 'N'                      # RESTORE*: numeric data only
        p.end_of_statement()
        return ('RESTORE', which)

    if v == 'PRINT':
        entries = []
        while not p.at_end():
            if p.accept_op(','):
                entries.append(('sep', ','))
                continue
            if p.accept_op(';'):
                entries.append(('sep', ';'))
                continue
            pk, pv = p.peek()
            if pk == 'op' and pv == ':':
                raise BasicError("ONLY ONE STATEMENT ALLOWED PER LINE", line)
            # adjacent items without a separator (e.g. PRINT "GAIN OF " Y)
            # are packed as if separated by ';' -- see DEVIATIONS
            if entries and entries[-1][0] == 'item':
                entries.append(('sep', ';'))
            entries.append(('item', p.expression()))
        return ('PRINT', entries)

    if v in ('GOTO', 'GO'):
        if v == 'GO':
            p.expect_id('TO')
        n = p.expect_lineno()
        p.end_of_statement()
        return ('GOTO', n)

    if v == 'ON':
        ex = p.expression()
        if not p.accept_id('GOTO'):
            p.expect_id('GO')
            p.expect_id('TO')
        targets = [p.expect_lineno()]
        while p.accept_op(','):
            targets.append(p.expect_lineno())
        p.end_of_statement()
        return ('ON', ex, targets)

    if v == 'IF':
        e1 = p.expression()
        op = p.relop()
        e2 = p.expression()
        p.expect_id('THEN')
        pk, pv = p.peek()
        if pk != 'num':
            raise BasicError(
                "THEN MUST BE FOLLOWED BY A LINE NUMBER (NOT A STATEMENT)", line)
        n = p.expect_lineno()
        p.end_of_statement()
        return ('IF', op, e1, e2, n)

    if v == 'FOR':
        fk, fv = p.next()
        if fk != 'id' or not NUMVAR_RE.match(fv):
            raise BasicError("ILLEGAL VARIABLE IN FOR", line)
        p.expect_op('=')
        a = p.expression()
        p.expect_id('TO')
        b = p.expression()
        c = None
        if p.accept_id('STEP'):
            c = p.expression()
        p.end_of_statement()
        return ('FOR', fv, a, b, c)

    if v == 'NEXT':
        nk, nv = p.next()
        if nk != 'id' or not NUMVAR_RE.match(nv):
            raise BasicError("ILLEGAL VARIABLE IN NEXT", line)
        p.end_of_statement()
        return ('NEXT', nv)

    if v == 'DIM':
        decls = []
        while True:
            dk, dv = p.next()
            if dk != 'id':
                raise BasicError("ILLEGAL VARIABLE IN DIM", line)
            is_str = bool(STRVAR_RE.match(dv))
            if not is_str and not NUMVAR_RE.match(dv):
                raise BasicError("ILLEGAL VARIABLE IN DIM", line)
            p.expect_op('(')
            dims = [p.expect_lineno()]        # non-negative integer constant
            if p.accept_op(','):
                if is_str:
                    raise BasicError("NO STRING MATRICES (ONE SUBSCRIPT ONLY)", line)
                dims.append(p.expect_lineno())
            p.expect_op(')')
            decls.append((dv, tuple(dims)))
            if not p.accept_op(','):
                break
        p.end_of_statement()
        return ('DIM', decls)

    if v == 'DEF':
        fk, fv = p.next()
        if fk != 'id' or not FN_RE.match(fv):
            raise BasicError("ILLEGAL FUNCTION NAME IN DEF", line)
        params = []
        if p.accept_op('('):
            while True:
                ak, av = p.next()
                if ak != 'id' or not NUMVAR_RE.match(av):
                    raise BasicError("ILLEGAL VARIABLE IN DEF", line)
                params.append(av)
                if not p.accept_op(','):
                    break
            p.expect_op(')')
        if not p.accept_op('='):
            raise BasicError("MULTIPLE-LINE DEF IS NOT SUPPORTED", line)
        ex = p.expression()
        p.end_of_statement()
        return ('DEF', fv, params, ex)

    if v == 'GOSUB':
        n = p.expect_lineno()
        p.end_of_statement()
        return ('GOSUB', n)

    if v == 'RETURN':
        p.end_of_statement()
        return ('RETURN',)

    if v == 'INPUT':
        lvs = [p.lvalue()]
        while p.accept_op(','):
            lvs.append(p.lvalue())
        p.end_of_statement()
        return ('INPUT', lvs)

    if v == 'CHANGE':
        ak, av = p.next()
        if ak != 'id':
            raise BasicError("ILLEGAL FORMAT IN CHANGE", line)
        if STRVAR_RE.match(av):
            p.expect_id('TO')
            bk, bv = p.next()
            if bk != 'id' or not NUMVAR_RE.match(bv):
                raise BasicError("ILLEGAL FORMAT IN CHANGE", line)
            p.end_of_statement()
            return ('CHANGE_SN', av, bv)
        if NUMVAR_RE.match(av):
            p.expect_id('TO')
            bk, bv = p.next()
            if bk != 'id' or not STRVAR_RE.match(bv):
                raise BasicError("ILLEGAL FORMAT IN CHANGE", line)
            p.end_of_statement()
            return ('CHANGE_NS', av, bv)
        raise BasicError("ILLEGAL FORMAT IN CHANGE", line)

    if v == 'STOP':
        p.end_of_statement()
        return ('STOP',)

    if v == 'END':
        p.end_of_statement()
        return ('END',)

    if v in ('RANDOMIZE', 'RANDOM'):
        p.end_of_statement()
        return ('RANDOMIZE',)

    if v == 'MAT':
        raise BasicError("MAT STATEMENTS ARE NOT IMPLEMENTED (SEE README)", line)

    raise BasicError("ILLEGAL INSTRUCTION '%s'" % v, line)


# ----------------------------------------------------------------------------
# Compiled program
# ----------------------------------------------------------------------------

class Program:
    """A compiled program: parsed statements plus static checks."""

    def __init__(self, lines):
        self.order = sorted(lines)
        self.index = {n: i for i, n in enumerate(self.order)}
        self.stmts = {}
        for n in self.order:
            self.stmts[n] = parse_statement(lines[n], n)

        # DATA pools: numeric and string data are kept in two separate
        # blocks, consumed independently (manual sec. 2.7).
        self.data_num, self.data_str = [], []
        for n in self.order:
            s = self.stmts[n]
            if s[0] == 'DATA':
                for typ, val in parse_data_items(s[1], n):
                    (self.data_num if typ == 'N' else self.data_str).append(val)

        # DEF registration (a DEF may occur anywhere, sec. 2.2)
        self.fns = {}
        for n in self.order:
            s = self.stmts[n]
            if s[0] == 'DEF':
                if s[1] in self.fns:
                    raise BasicError("FUNCTION %s DEFINED TWICE" % s[1], n)
                self.fns[s[1]] = (s[2], s[3], n)

        # DIM declarations (position-independent; the program is compiled)
        self.dims, self.sdims = {}, {}
        for n in self.order:
            s = self.stmts[n]
            if s[0] == 'DIM':
                for name, dims in s[1]:
                    table = self.sdims if name.endswith('$') else self.dims
                    if name in table:
                        raise BasicError("'%s' DIMENSIONED TWICE" % name, n)
                    table[name] = dims

        # Static FOR/NEXT pairing; loops must be properly nested (sec. 1.7.7)
        self.next_of = {}
        stack = []
        for n in self.order:
            s = self.stmts[n]
            if s[0] == 'FOR':
                stack.append((s[1], n))
            elif s[0] == 'NEXT':
                if not stack or stack[-1][0] != s[1]:
                    raise BasicError("NEXT WITHOUT FOR", n)
                _, fline = stack.pop()
                self.next_of[fline] = n
        if stack:
            raise BasicError("FOR WITHOUT NEXT", stack[-1][1])

        # All referenced line numbers must exist
        for n in self.order:
            s = self.stmts[n]
            targets = ()
            if s[0] in ('GOTO', 'GOSUB'):
                targets = (s[1],)
            elif s[0] == 'IF':
                targets = (s[4],)
            elif s[0] == 'ON':
                targets = tuple(s[2])
            for t in targets:
                if t not in self.index:
                    raise BasicError("UNDEFINED LINE NUMBER %s" % t, n)

        # END marks the end of the source to the (one-pass) compiler: it
        # must exist, be unique, and be the last line (manual sec. 2.8).
        end_lines = [n for n in self.order if self.stmts[n][0] == 'END']
        if not end_lines:
            raise BasicError("NO END INSTRUCTION")
        if len(end_lines) > 1 or end_lines[0] != self.order[-1]:
            raise BasicError("END IS NOT LAST", end_lines[0])


# ----------------------------------------------------------------------------
# Number formatting (manual sec. 2.1)
# ----------------------------------------------------------------------------

def _fmt_e(a):
    """E-notation: one digit, point, five digits, space, E, signed exponent.

    The space before the E matches the manual's teletype sample outputs
    (e.g. "5.00548 E-2", "1.34218 E+8" in sec. 2.1/2.2).
    """
    e = math.floor(math.log10(a))
    m = a / (10.0 ** e)
    m = round(m, 5)
    if m >= 10.0:
        m /= 10.0
        e += 1
    return "%.5f E%+d" % (m, e)


def fmt_mag(a):
    """Format a non-negative magnitude per the manual's four rules."""
    if a == 0:
        return "0"
    # Rule 1: integers print without a decimal point; more than eight
    # digits switches to E-notation.
    if a == int(a) and a < 1e17:
        i = int(a)
        if len(str(i)) <= 8:
            return str(i)
        return _fmt_e(a)
    # Rule 2: at most six significant digits.
    e = math.floor(math.log10(a))
    r = round(a, 5 - e)
    if r != 0:
        e = math.floor(math.log10(r))     # rounding may bump the exponent
    if r == int(r) and r >= 1:
        i = int(r)
        if len(str(i)) <= 8:
            return str(i)
        return _fmt_e(r)
    if r >= 0.1:
        dec = 5 - e
        s = "%.*f" % (dec, r)
        s = s.rstrip('0').rstrip('.')
        return s
    # Rule 3: below 0.1, E-notation unless the significant part fits
    # within six decimal places.
    dec = 5 - e
    s = "%.*f" % (dec, r)
    s = s.rstrip('0')
    frac = s.split('.', 1)[1]
    if len(frac) <= 6:
        return s
    return _fmt_e(r)


def fmt_number(x):
    """Full printed form: sign (or leading space) + magnitude + one space."""
    return ('-' if x < 0 else ' ') + fmt_mag(abs(x)) + ' '


# ----------------------------------------------------------------------------
# Teleprinter model
# ----------------------------------------------------------------------------

class Printer:
    """Tracks the print head column; implements zones, TAB and wrapping."""

    def __init__(self, out):
        self.out = out
        self.col = 0

    def newline(self):
        self.out.write('\n')
        self.col = 0

    def emit(self, s):
        for ch in s:
            if ch == '\n':
                self.newline()
                continue
            if self.col >= WIDTH:
                self.newline()
            self.out.write(ch)
            self.col += 1

    def write_item(self, s):
        # Break the line before an item that would run past column 75
        # (observed DTSS behavior in the manual's sample outputs).
        if 0 < self.col and self.col + len(s) > WIDTH and len(s) <= WIDTH:
            self.newline()
        self.emit(s)

    def zone_advance(self):
        target = ((self.col // ZONE) + 1) * ZONE
        if target >= WIDTH:
            self.newline()
        else:
            self.emit(' ' * (target - self.col))

    def tab(self, n):
        # Forward only; ignored if the head is at or past column n.
        if self.col < n:
            self.emit(' ' * (n - self.col))

    def flush(self):
        self.out.flush()


class Rand:
    """Lehmer / MINSTD generator; values strictly between 0 and 1."""

    def __init__(self, seed=RND_SEED):
        self.x = seed

    def next(self):
        self.x = (self.x * RND_A) % RND_M
        return self.x / RND_M

    def randomize(self):
        self.x = (time.time_ns() % (RND_M - 2)) + 1


# ----------------------------------------------------------------------------
# Interpreter
# ----------------------------------------------------------------------------

class Interp:
    def __init__(self, prog, stdin, stdout, interactive=False):
        self.prog = prog
        self.stdin = stdin
        self.printer = Printer(stdout)
        self.interactive = interactive
        self.vars = {}          # numeric scalars
        self.svars = {}         # string scalars
        self.arrays = {}        # numeric arrays (a letter may name both a
        self.sarrays = {}       # string vectors  scalar and an array)
        self.locals = []        # DEF FN parameter scopes
        self.for_stack = []
        self.gosub_stack = []
        self.nptr = 0           # numeric DATA pointer
        self.sptr = 0           # string DATA pointer
        self.rng = Rand()       # reseeded identically on every RUN
        for name, dims in prog.dims.items():
            self.arrays[name] = self._new_array(dims, 0.0)
        for name, dims in prog.sdims.items():
            self.sarrays[name] = self._new_array(dims, '')

    @staticmethod
    def _new_array(dims, fill):
        size = dims[0] + 1
        if len(dims) == 2:
            size *= dims[1] + 1
        return {'dims': dims, 'data': [fill] * size}

    # --- variables and arrays ------------------------------------------

    def get_array(self, name, nsubs, line, string=False):
        table = self.sarrays if string else self.arrays
        arr = table.get(name)
        if arr is None:
            dims = (AUTO_BOUND,) * nsubs
            arr = self._new_array(dims, '' if string else 0.0)
            table[name] = arr
        if len(arr['dims']) != nsubs:
            raise BasicError("INCORRECT NUMBER OF SUBSCRIPTS FOR '%s'" % name, line)
        return arr

    def _flat(self, arr, idx_vals, line):
        dims = arr['dims']
        ints = []
        for v in idx_vals:
            i = iround(v)
            ints.append(i)
        for i, bound in zip(ints, dims):
            if i < 0 or i > bound:
                raise BasicError("SUBSCRIPT ERROR", line)
        if len(dims) == 1:
            return ints[0]
        return ints[0] * (dims[1] + 1) + ints[1]

    # --- runtime warnings (manual sec. 2.8) -------------------------------
    # Several arithmetic conditions are warnings, not errors: the machine
    # prints a message, supplies a value, and continues running.

    def warn(self, msg, line=None):
        text = "%s IN %s" % (msg, line) if line is not None else msg
        if self.interactive:
            if self.printer.col > 0:
                self.printer.newline()
            self.printer.emit(text)
            self.printer.newline()
        else:
            # keep batch stdout exactly the teleprinter program output
            sys.stderr.write(text + '\n')

    def _check_range(self, v, line):
        if math.isnan(v) or math.isinf(v) or abs(v) > MAXNUM:
            self.warn("OVERFLOW", line)
            if math.isnan(v):
                return MAXNUM
            return math.copysign(MAXNUM, v)
        if v != 0 and abs(v) < MINNUM:
            self.warn("UNDERFLOW", line)
            return 0.0
        return v

    # --- expression evaluation ------------------------------------------

    def eval(self, ast, line):
        op = ast[0]
        if op == 'num':
            return ast[1]
        if op == 'str':
            return ast[1]
        if op == 'var':
            name = ast[1]
            for scope in reversed(self.locals):
                if name in scope:
                    return scope[name]
            return self.vars.get(name, 0.0)
        if op == 'svar':
            return self.svars.get(ast[1], '')
        if op == 'el':
            arr = self.get_array(ast[1], len(ast[2]), line)
            idx = [self.eval_num(i, line) for i in ast[2]]
            return arr['data'][self._flat(arr, idx, line)]
        if op == 'sel':
            arr = self.get_array(ast[1], 1, line, string=True)
            idx = [self.eval_num(ast[2], line)]
            return arr['data'][self._flat(arr, idx, line)]
        if op == 'neg':
            return -self.eval_num(ast[1], line)
        if op == 'bin':
            return self.binop(ast[1], ast[2], ast[3], line)
        if op == 'fn':
            return self.builtin(ast[1], self.eval_num(ast[2], line), line)
        if op == 'rnd':
            return self.rng.next()
        if op == 'call':
            return self.call_fn(ast[1], ast[2], line)
        if op == 'tab':
            raise BasicError("TAB IS ONLY ALLOWED IN PRINT", line)
        raise BasicError("ILLEGAL FORMULA", line)

    def eval_num(self, ast, line):
        v = self.eval(ast, line)
        if isinstance(v, str):
            raise BasicError("MISMATCHED STRING OPERATION", line)
        return v

    def binop(self, op, l, r, line):
        a = self.eval(l, line)
        b = self.eval(r, line)
        if isinstance(a, str) or isinstance(b, str):
            raise BasicError("MISMATCHED STRING OPERATION", line)
        try:
            if op == '+':
                v = a + b
            elif op == '-':
                v = a - b
            elif op == '*':
                v = a * b
            elif op == '/':
                if b == 0:
                    # "the computer assumes the answer is +infinity ...
                    # and continues running the program"
                    self.warn("DIVISION BY ZERO", line)
                    return MAXNUM
                v = a / b
            elif op == '^':
                if a == 0 and b < 0:
                    self.warn("ZERO TO A NEGATIVE POWER", line)
                    return MAXNUM
                if a == 0 and b == 0:
                    v = 1.0
                elif a < 0 and b != int(b):
                    # (-3)^2.7 -> ABS(-3)^2.7 with a warning;
                    # (-3)^3 is correctly computed to give -27
                    self.warn("ABSOLUTE VALUE RAISED TO POWER", line)
                    v = math.pow(-a, b)
                else:
                    v = math.pow(a, b)
        except OverflowError:
            self.warn("OVERFLOW", line)
            return MAXNUM
        return self._check_range(v, line)

    def builtin(self, name, x, line):
        try:
            if name == 'SIN':
                return math.sin(x)
            if name == 'COS':
                return math.cos(x)
            if name == 'TAN':
                return self._check_range(math.tan(x), line)
            if name == 'ATN':
                return math.atan(x)
            if name == 'EXP':
                if x >= EXP_MAX_ARG:
                    self.warn("EXP TOO LARGE", line)
                    return MAXNUM
                return self._check_range(math.exp(x), line)
            if name == 'LOG':
                # warnings, not errors: the machine supplies a value and
                # continues (manual sec. 2.8)
                if x == 0:
                    self.warn("LOG OF ZERO", line)
                    return -MAXNUM
                if x < 0:
                    self.warn("LOG OF NEGATIVE NUMBER", line)
                    return math.log(-x)
                return math.log(x)
            if name == 'ABS':
                return abs(x)
            if name == 'SQR':
                if x < 0:
                    self.warn("SQUARE ROOT OF A NEGATIVE NUMBER", line)
                    return math.sqrt(-x)
                return math.sqrt(x)
            if name == 'INT':
                return float(math.floor(x))
            if name == 'SGN':
                return float((x > 0) - (x < 0))
        except OverflowError:
            self.warn("OVERFLOW", line)
            return MAXNUM
        raise BasicError("UNDEFINED FUNCTION %s" % name, line)

    def call_fn(self, name, arg_asts, line):
        if name not in self.prog.fns:
            raise BasicError("UNDEFINED FUNCTION %s" % name, line)
        params, body, defline = self.prog.fns[name]
        if len(arg_asts) != len(params):
            raise BasicError("INCORRECT NUMBER OF ARGUMENTS FOR %s" % name, line)
        if len(self.locals) > 50:
            raise BasicError("FUNCTIONS NESTED TOO DEEPLY", line)
        args = [self.eval_num(a, line) for a in arg_asts]
        self.locals.append(dict(zip(params, args)))
        try:
            return self.eval_num(body, defline)
        finally:
            self.locals.pop()

    def compare(self, op, l, r, line):
        a = self.eval(l, line)
        b = self.eval(r, line)
        if isinstance(a, str) != isinstance(b, str):
            raise BasicError("MISMATCHED STRING OPERATION", line)
        if isinstance(a, str):
            # trailing blanks are ignored in string comparison (sec. 2.7)
            a = a.rstrip(' ')
            b = b.rstrip(' ')
        if op == '=':
            return a == b
        if op == '<':
            return a < b
        if op == '>':
            return a > b
        if op == '<=':
            return a <= b
        if op == '>=':
            return a >= b
        if op == '<>':
            return a != b
        raise BasicError("ILLEGAL RELATION", line)

    # --- assignment ------------------------------------------------------

    def assign(self, lv, value, line):
        kind = lv[0]
        if kind == 'var':
            if isinstance(value, str):
                raise BasicError("MISMATCHED STRING OPERATION", line)
            self.vars[lv[1]] = value
        elif kind == 'svar':
            if not isinstance(value, str):
                raise BasicError("MISMATCHED STRING OPERATION", line)
            self.svars[lv[1]] = value
        elif kind == 'el':
            if isinstance(value, str):
                raise BasicError("MISMATCHED STRING OPERATION", line)
            arr = self.get_array(lv[1], len(lv[2]), line)
            idx = [self.eval_num(i, line) for i in lv[2]]
            arr['data'][self._flat(arr, idx, line)] = value
        elif kind == 'sel':
            if not isinstance(value, str):
                raise BasicError("MISMATCHED STRING OPERATION", line)
            arr = self.get_array(lv[1], 1, line, string=True)
            idx = [self.eval_num(lv[2], line)]
            arr['data'][self._flat(arr, idx, line)] = value
        else:
            raise BasicError("ILLEGAL VARIABLE", line)

    # --- statement execution ---------------------------------------------

    def run(self):
        order = self.prog.order
        i = 0
        try:
            while i < len(order):
                line = order[i]
                r = self.exec_stmt(self.prog.stmts[line], line)
                if r is None:
                    i += 1
                elif r[0] == 'goto':
                    i = self.prog.index[r[1]]
                elif r[0] == 'after':
                    i = self.prog.index[r[1]] + 1
        except StopRun:
            pass
        if self.printer.col > 0:
            self.printer.newline()
        self.printer.flush()

    def exec_stmt(self, s, line):
        op = s[0]
        if op == 'LET':
            self.assign(s[1], self.eval(s[2], line), line)
            return None
        if op == 'PRINT':
            return self.do_print(s[1], line)
        if op == 'IF':
            if self.compare(s[1], s[2], s[3], line):
                return ('goto', s[4])
            return None
        if op == 'GOTO':
            return ('goto', s[1])
        if op == 'FOR':
            return self.do_for(s, line)
        if op == 'NEXT':
            return self.do_next(s[1], line)
        if op == 'READ':
            return self.do_read(s[1], line)
        if op == 'GOSUB':
            if len(self.gosub_stack) > 200:
                raise BasicError("GOSUB NESTED TOO DEEPLY", line)
            self.gosub_stack.append(line)
            return ('goto', s[1])
        if op == 'RETURN':
            if not self.gosub_stack:
                raise BasicError("RETURN BEFORE GOSUB", line)
            return ('after', self.gosub_stack.pop())
        if op == 'ON':
            v = self.eval_num(s[1], line)
            n = int(math.floor(v))
            if n < 1 or n > len(s[2]):
                raise BasicError("ON EVALUATED OUT OF RANGE", line)
            return ('goto', s[2][n - 1])
        if op == 'INPUT':
            return self.do_input(s[1], line)
        if op == 'RESTORE':
            if s[1] in ('B', 'N'):
                self.nptr = 0
            if s[1] in ('B', 'S'):
                self.sptr = 0
            return None
        if op == 'CHANGE_SN':
            return self.do_change_sn(s[1], s[2], line)
        if op == 'CHANGE_NS':
            return self.do_change_ns(s[1], s[2], line)
        if op in ('END', 'STOP'):
            raise StopRun()
        if op == 'RANDOMIZE':
            self.rng.randomize()
            return None
        if op in ('REM', 'DATA', 'DIM', 'DEF'):
            return None
        raise BasicError("ILLEGAL INSTRUCTION", line)

    def do_print(self, entries, line):
        pr = self.printer
        for kind, val in entries:
            if kind == 'sep':
                if val == ',':
                    pr.zone_advance()
                continue
            if val[0] == 'tab':
                n = int(math.floor(self.eval_num(val[1], line))) % WIDTH
                pr.tab(n)
                continue
            v = self.eval(val, line)
            if isinstance(v, str):
                pr.write_item(v)
            else:
                pr.write_item(fmt_number(v))
        if not entries or entries[-1][0] != 'sep':
            pr.newline()
        return None

    def do_for(self, s, line):
        _, var, a_ast, b_ast, c_ast = s
        a = self.eval_num(a_ast, line)
        b = self.eval_num(b_ast, line)
        c = self.eval_num(c_ast, line) if c_ast is not None else 1.0
        self.vars[var] = a
        # re-entering a FOR with the same control variable abandons the
        # old loop (and anything nested inside it)
        for j, fr in enumerate(self.for_stack):
            if fr[0] == var:
                del self.for_stack[j:]
                break
        if (c >= 0 and a <= b) or (c < 0 and a >= b):
            self.for_stack.append((var, b, c, line))
            return None
        return ('after', self.prog.next_of[line])

    def do_next(self, var, line):
        # a GOTO may have abandoned inner loops; unwind to the matching FOR
        while self.for_stack and self.for_stack[-1][0] != var:
            self.for_stack.pop()
        if not self.for_stack:
            raise BasicError("NEXT WITHOUT FOR", line)
        _, limit, step, for_line = self.for_stack[-1]
        v = self.vars.get(var, 0.0) + step
        self.vars[var] = v
        if (step >= 0 and v <= limit) or (step < 0 and v >= limit):
            return ('after', for_line)
        self.for_stack.pop()
        return None

    def do_read(self, lvs, line):
        for lv in lvs:
            if lv[0] in ('svar', 'sel'):
                if self.sptr >= len(self.prog.data_str):
                    raise BasicError("OUT OF DATA", line)
                self.assign(lv, self.prog.data_str[self.sptr], line)
                self.sptr += 1
            else:
                if self.nptr >= len(self.prog.data_num):
                    raise BasicError("OUT OF DATA", line)
                self.assign(lv, self.prog.data_num[self.nptr], line)
                self.nptr += 1
        return None

    def do_input(self, lvs, line):
        while True:
            vals = []
            while len(vals) < len(lvs):
                if vals:
                    self.warn("NOT ENOUGH INPUT -- ADD MORE")
                self.printer.emit('? ')
                self.printer.flush()
                raw = self.stdin.readline()
                if raw == '':
                    raise BasicError("END OF INPUT", line)
                raw = raw.rstrip('\n').rstrip('\r')
                # the user's carriage return moved the head to column 0;
                # when input is piped, emit the newline so output is sane
                self.printer.col = 0
                if not self.interactive and not self.stdin.isatty():
                    self.printer.out.write('\n')
                for item in split_csv(raw):
                    item = item.strip()
                    if item.startswith('"') and item.endswith('"') and len(item) >= 2:
                        vals.append(('S', item[1:-1]))
                    else:
                        vals.append(('U', item))
            if len(vals) > len(lvs):
                self.warn("TOO MUCH INPUT -- EXCESS IGNORED")
            try:
                for lv, (typ, item) in zip(lvs, vals):
                    if lv[0] in ('svar', 'sel'):
                        self.assign(lv, item, line)
                    else:
                        if typ == 'S':
                            raise BasicError(
                                "INPUT DATA NOT IN CORRECT FORMAT", line)
                        try:
                            v = float(item)
                        except ValueError:
                            raise BasicError(
                                "INPUT DATA NOT IN CORRECT FORMAT", line)
                        self.assign(lv, v, line)
            except BasicError:
                if self.interactive:
                    self.printer.emit(
                        'INPUT DATA NOT IN CORRECT FORMAT -- RETYPE IT')
                    self.printer.newline()
                    continue
                raise
            return None

    def do_change_sn(self, svname, arrname, line):
        s = self.svars.get(svname, '')
        arr = self.get_array(arrname, 1, line)
        if len(s) > arr['dims'][0]:
            raise BasicError("SUBSCRIPT ERROR (STRING TOO LONG)", line)
        arr['data'][0] = float(len(s))
        for i, ch in enumerate(s):
            code = ord(ch)
            if code > 127:
                raise BasicError("ILLEGAL CHARACTER IN CHANGE", line)
            arr['data'][i + 1] = float(code)
        return None

    def do_change_ns(self, arrname, svname, line):
        arr = self.get_array(arrname, 1, line)
        n = iround(arr['data'][0])
        if n < 0 or n > arr['dims'][0]:
            raise BasicError("SUBSCRIPT ERROR IN CHANGE", line)
        chars = []
        for i in range(1, n + 1):
            code = iround(arr['data'][i])
            if code < 0 or code > 127:
                raise BasicError("ILLEGAL CHARACTER CODE IN CHANGE", line)
            chars.append(chr(code))
        self.svars[svname] = ''.join(chars)
        return None


# ----------------------------------------------------------------------------
# Program loading
# ----------------------------------------------------------------------------

LINE_RE = re.compile(r'^\s*(\d{1,5})\s*(.*)$')


def load_program_text(text):
    """Parse program-file text into a {lineno: statement-text} dict."""
    lines = {}
    for raw in text.splitlines():
        s = raw.rstrip()
        if not s.strip():
            continue
        m = LINE_RE.match(s)
        if not m:
            raise BasicError("MISSING LINE NUMBER: %s" % s.strip()[:30])
        n = int(m.group(1))
        if n > MAX_LINENO:
            raise BasicError("ILLEGAL LINE NUMBER %d" % n)
        lines[n] = upcase_outside_quotes(m.group(2)).strip()
    return lines


def run_batch(path):
    try:
        with open(path, 'r') as f:
            text = f.read()
    except OSError as e:
        sys.stderr.write("dbasic: cannot open %s: %s\n" % (path, e.strerror))
        return 2
    try:
        prog = Program(load_program_text(text))
        Interp(prog, sys.stdin, sys.stdout).run()
        return 0
    except BasicError as e:
        sys.stdout.flush()
        sys.stderr.write(e.report() + '\n')
        return 1


# ----------------------------------------------------------------------------
# Interactive DTSS-style command environment (manual Appendix A)
# ----------------------------------------------------------------------------

NAME_RE = re.compile(r'^[A-Z0-9]{1,6}$')


class Repl:
    def __init__(self, libdir):
        self.libdir = libdir
        self.name = 'NONAME'
        self.lines = {}

    # -- helpers ---------------------------------------------------------

    def _ask(self, prompt):
        sys.stdout.write(prompt)
        sys.stdout.flush()
        line = sys.stdin.readline()
        if line == '':
            raise EOFError
        return line.strip()

    def _valid_name(self, name):
        name = name.upper()
        if not NAME_RE.match(name):
            raise BasicError("ILLEGAL PROGRAM NAME (1-6 LETTERS OR DIGITS)")
        return name

    def _libpath(self, name):
        return os.path.join(self.libdir, name)

    # -- line entry --------------------------------------------------------

    def enter_line(self, s):
        m = LINE_RE.match(s)
        n = int(m.group(1))
        if n > MAX_LINENO:
            print("ILLEGAL LINE NUMBER")
            return
        body = upcase_outside_quotes(m.group(2)).strip()
        if body:
            self.lines[n] = body
        else:
            self.lines.pop(n, None)     # a bare line number deletes the line

    # -- commands ----------------------------------------------------------

    def cmd_run(self):
        prog = Program(dict(self.lines))
        print()
        print("%-9s%s      %s" % (self.name, time.strftime('%H:%M'),
                                  time.strftime('%m/%d/%y')))
        print()
        t0 = time.process_time()
        interp = Interp(prog, sys.stdin, sys.stdout, interactive=True)
        try:
            interp.run()
        except KeyboardInterrupt:
            if interp.printer.col > 0:
                interp.printer.newline()
            print("STOPPED AT USER REQUEST")
        print()
        print("TIME:  %.2f SECS." % (time.process_time() - t0))

    def cmd_list(self, args, heading=True):
        if not self.lines:
            return           # an empty workspace lists nothing, silently
        lo, hi = 0, MAX_LINENO
        if args:
            m = re.match(r'^(\d*)(?:-(\d*))?$', args.replace(' ', ''))
            if not m:
                raise BasicError("ILLEGAL LINE RANGE")
            if m.group(1):
                lo = int(m.group(1))
            if m.group(2) is not None:
                hi = int(m.group(2)) if m.group(2) else MAX_LINENO
            elif m.group(1):
                hi = MAX_LINENO if '-' in args else MAX_LINENO
        if heading:
            print("%-9s%s      %s" % (self.name, time.strftime('%H:%M'),
                                      time.strftime('%m/%d/%y')))
            print()
        for n in sorted(self.lines):
            if lo <= n <= hi:
                print("%d %s" % (n, self.lines[n]))

    def cmd_save(self, replace=False):
        os.makedirs(self.libdir, exist_ok=True)
        path = self._libpath(self.name)
        if os.path.exists(path) and not replace:
            raise BasicError("PROGRAM ALREADY SAVED, USE REPLACE")
        with open(path, 'w') as f:
            for n in sorted(self.lines):
                f.write("%d %s\n" % (n, self.lines[n]))

    def cmd_old(self, name):
        path = self._libpath(name)
        try:
            with open(path, 'r') as f:
                text = f.read()
        except OSError:
            raise BasicError("PROGRAM NOT FOUND")
        self.lines = load_program_text(text)
        self.name = name

    def cmd_catalog(self):
        try:
            names = sorted(n for n in os.listdir(self.libdir)
                           if os.path.isfile(self._libpath(n)))
        except OSError:
            names = []
        for n in names:
            print(n)

    # -- main loop -----------------------------------------------------------

    def loop(self):
        try:
            import readline  # noqa: F401  (line editing when available)
        except ImportError:
            pass
        print("DARTMOUTH BASIC, FOURTH EDITION (1968) -- REIMPLEMENTATION")
        print("READY")
        while True:
            try:
                raw = input()
            except EOFError:
                return 0
            except KeyboardInterrupt:
                print()
                continue
            s = raw.strip()
            if not s:
                continue
            if s[0].isdigit():
                self.enter_line(s)
                continue
            parts = s.split(None, 1)
            cmd = parts[0].upper()
            args = parts[1].strip() if len(parts) > 1 else ''
            try:
                if cmd in ('BYE', 'GOODBYE'):
                    return 0
                elif cmd == 'RUN':
                    self.cmd_run()
                elif cmd == 'LIST':
                    self.cmd_list(args, heading=True)
                elif cmd == 'LISTNH':
                    self.cmd_list(args, heading=False)
                elif cmd == 'NEW':
                    name = args or self._ask("NEW PROBLEM NAME-- ")
                    self.name = self._valid_name(name)
                    self.lines = {}
                elif cmd == 'OLD':
                    name = args or self._ask("OLD PROBLEM NAME-- ")
                    self.cmd_old(self._valid_name(name))
                elif cmd == 'SAVE':
                    self.cmd_save(replace=False)
                elif cmd == 'REPLACE':
                    self.cmd_save(replace=True)
                elif cmd == 'UNSAVE':
                    path = self._libpath(self.name)
                    if not os.path.exists(path):
                        raise BasicError("PROGRAM NOT SAVED")
                    os.remove(path)
                elif cmd == 'SCRATCH':
                    self.lines = {}
                elif cmd == 'RENAME':
                    name = args or self._ask("NEW NAME-- ")
                    self.name = self._valid_name(name)
                elif cmd in ('CATALOG', 'CAT'):
                    self.cmd_catalog()
                elif cmd == 'LENGTH':
                    total = sum(len("%d %s\n" % (n, t))
                                for n, t in self.lines.items())
                    print("%d CHARACTERS" % total)
                else:
                    print("WHAT?")
                    continue
            except EOFError:
                return 0
            except BasicError as e:
                print(e.report())
            print("READY")


# ----------------------------------------------------------------------------
# Entry point
# ----------------------------------------------------------------------------

def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog='dbasic',
        description='Dartmouth BASIC, Fourth Edition (1968) interpreter')
    ap.add_argument('program', nargs='?',
                    help='BASIC program file (batch mode); '
                         'omit for an interactive DTSS-style session')
    ap.add_argument('--library', default='./library', metavar='DIR',
                    help='program library directory for the interactive '
                         'session (default: ./library)')
    args = ap.parse_args(argv)
    if args.program:
        sys.exit(run_batch(args.program))
    sys.exit(Repl(args.library).loop())


if __name__ == '__main__':
    main()
