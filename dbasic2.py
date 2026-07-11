#!/usr/bin/env python2
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


import math
import os
import re
import sys
import time

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



def iround(v):
    """Round half away from zero.

    round() would be banker's rounding; an explicit rule keeps array
    subscripts deterministic and identical to dbasic.py.
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
        super(BasicError, self).__init__(msg)
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

# Vocabulary for the carving lexer, tried longest-first at each position.
LEX_KEYWORDS = tuple(sorted((
    'RANDOMIZE', 'RESTORE$', 'RESTORE', 'CHANGE', 'RANDOM', 'RETURN',
    'GOSUB', 'FNEND', 'INPUT', 'PRINT', 'THEN', 'STEP', 'GOTO', 'NEXT',
    'READ', 'STOP', 'DATA', 'LET', 'DIM', 'DEF', 'END', 'FOR', 'MAT',
    'TAB', 'NUM', 'DET', 'ZER', 'CON', 'IDN', 'TRN', 'INV', 'RND',
    'SIN', 'COS', 'TAN', 'COT', 'ATN', 'EXP', 'LOG', 'ABS', 'SQR',
    'INT', 'SGN', 'REM', 'ON', 'IF', 'TO', 'GO',
), key=len, reverse=True))

NUM_TOKEN_RE = re.compile(r'(?:\d+\.?\d*|\.\d+)(?:E[+-]?\d+)?')
OP_TOKEN_RE = re.compile(r'<=|>=|<>|[#<>=+\-*/^(),;:]')


def tokenize(text, line=None):
    """Tokenize one (space-stripped) statement.

    DTSS BASIC source is free-form -- spaces outside quoted strings have
    no meaning, so 15LETG=A*E-B*D is legal.  Identifiers are therefore
    carved keyword-first: because Fourth Edition variables are one letter
    plus an optional digit, any longer letter run in valid source must
    decompose into keywords, function names and FN-names, which makes
    space-free source unambiguous.
    """
    toks = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in ' \t':
            i += 1
            continue
        if ch == '"':
            j = text.find('"', i + 1)
            if j < 0:
                raise BasicError("ILLEGAL FORMAT (UNCLOSED QUOTE)", line)
            toks.append(('str', text[i + 1:j]))
            i = j + 1
            continue
        m = NUM_TOKEN_RE.match(text, i)
        if m:
            toks.append(('num', m.group()))
            i = m.end()
            continue
        if 'A' <= ch <= 'Z':
            kw = None
            for k in LEX_KEYWORDS:
                if text.startswith(k, i):
                    kw = k
                    break
            if kw is not None:
                toks.append(('id', kw))
                i += len(kw)
                continue
            if (text.startswith('FN', i) and i + 2 < n
                    and 'A' <= text[i + 2] <= 'Z'):
                toks.append(('id', text[i:i + 3]))
                i += 3
                continue
            j = i + 1
            if j < n and (text[j].isdigit() or text[j] == '$'):
                j += 1
            toks.append(('id', text[i:j]))
            i = j
            continue
        m = OP_TOKEN_RE.match(text, i)
        if m:
            toks.append(('op', m.group()))
            i = m.end()
            continue
        raise BasicError("ILLEGAL CHARACTER '%s'" % ch, line)
    return toks


def strip_spaces_outside_quotes(s):
    """Delete spaces outside quoted strings: DTSS source is free-form."""
    out, inq = [], False
    for ch in s:
        if ch == '"':
            inq = not inq
            out.append(ch)
        elif ch in ' \t' and not inq:
            continue
        else:
            out.append(ch)
    return ''.join(out)


def upcase_outside_quotes(s):
    out, inq = [], False
    for ch in s:
        if ch == '"':
            inq = not inq
            out.append(ch)
        else:
            out.append(ch if inq else ch.upper())
    return ''.join(out)


def strip_remark(text):
    """Cut an end-of-line ' remark (manual sec. 2.5), respecting quotes.

    Not applied to DATA lines: the manual notes that on a line ending in
    an unquoted string the apostrophe becomes part of the string.
    """
    inq = False
    for i, ch in enumerate(text):
        if ch == '"':
            inq = not inq
        elif ch == "'" and not inq:
            return text[:i]
    return text


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

BUILTINS = {'SIN', 'COS', 'TAN', 'COT', 'ATN', 'EXP', 'LOG', 'ABS', 'SQR',
            'INT', 'SGN'}
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
        if v == 'NUM':          # components entered by the last MAT INPUT
            return ('numfn',)
        if v == 'DET':          # determinant from the last MAT ... = INV( )
            return ('detfn',)
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
        if FN_RE.match(v):
            # LET FNM = ... : the temporary value of a multiple-line DEF
            return ('fnvar', v)
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


def _mat_name(p, line, strings_ok=False):
    nk, nv = p.next()
    if nk == 'id' and NUMVAR_RE.match(nv):
        return nv
    if strings_ok and nk == 'id' and STRVAR_RE.match(nv):
        return nv
    raise BasicError("ILLEGAL VARIABLE IN MAT", line)


def parse_mat(p, line):
    """The thirteen MAT instructions of manual sec. 2.6 (and their
    string-vector forms from sec. 2.7)."""
    k, v = p.next()
    if k != 'id':
        raise BasicError("ILLEGAL FORMAT IN MAT", line)

    if v == 'READ':
        items = []
        while True:
            name = _mat_name(p, line, strings_ok=True)
            dims = None
            if p.accept_op('('):
                dims = [p.expression()]
                if p.accept_op(','):
                    if name.endswith('$'):
                        raise BasicError(
                            "NO STRING MATRICES (ONE SUBSCRIPT ONLY)", line)
                    dims.append(p.expression())
                p.expect_op(')')
            items.append((name, dims))
            if not p.accept_op(','):
                break
        p.end_of_statement()
        return ('MATREAD', items)

    if v == 'PRINT':
        # the separator AFTER each matrix selects its format:
        # ';' packed, ',' zones; absent: zones (column format for vectors)
        items = []
        while True:
            name = _mat_name(p, line, strings_ok=True)
            sep = p.accept_op(',', ';')
            fmt = 'packed' if sep == ';' else 'zone' if sep == ',' else 'plain'
            items.append((name, fmt))
            if sep is None or p.at_end():
                break
        p.end_of_statement()
        return ('MATPRINT', items)

    if v == 'INPUT':
        name = _mat_name(p, line, strings_ok=True)
        p.end_of_statement()
        return ('MATINPUT', name)

    # MAT <target> = <rhs>
    if not NUMVAR_RE.match(v):
        raise BasicError("ILLEGAL VARIABLE IN MAT", line)
    target = v
    p.expect_op('=')
    pk, pv = p.peek()
    if pk == 'op' and pv == '(':
        # MAT C = (K) * A : scalar multiplication
        p.next()
        ex = p.expression()
        p.expect_op(')')
        p.expect_op('*')
        rhs = ('scal', ex, _mat_name(p, line))
    elif pk == 'id':
        p.next()
        if pv in ('ZER', 'CON', 'IDN'):
            dims = None
            if p.accept_op('('):
                dims = [p.expression()]
                if p.accept_op(','):
                    dims.append(p.expression())
                p.expect_op(')')
            rhs = ('fill', pv, dims)
        elif pv in ('TRN', 'INV'):
            p.expect_op('(')
            name = _mat_name(p, line)
            p.expect_op(')')
            rhs = ('trn' if pv == 'TRN' else 'inv', name)
        elif NUMVAR_RE.match(pv):
            if p.accept_op('+'):
                rhs = ('add', pv, _mat_name(p, line))
            elif p.accept_op('-'):
                rhs = ('sub', pv, _mat_name(p, line))
            elif p.accept_op('*'):
                rhs = ('mul', pv, _mat_name(p, line))
            else:
                rhs = ('copy', pv)
        else:
            raise BasicError("ILLEGAL MAT FUNCTION", line)
    else:
        raise BasicError("ILLEGAL FORMAT IN MAT", line)
    p.end_of_statement()
    return ('MATASSIGN', target, rhs)


def parse_statement(text, line):
    """Parse one statement (line-number already removed) into a tuple."""
    stripped = text.strip()
    if stripped.startswith('REM'):
        return ('REM',)
    if stripped.startswith('DATA'):
        # raw text: unquoted DATA strings may contain spaces and
        # apostrophes (so no ' remark is possible here, per sec. 2.5)
        idx = text.upper().index('DATA') + 4
        return ('DATA', text[idx:])
    text = strip_remark(text)
    text = strip_spaces_outside_quotes(text)
    toks = tokenize(text, line)
    if not toks:
        raise BasicError("ILLEGAL INSTRUCTION", line)
    p = Parser(toks, line)
    k, v = p.next()
    if k != 'id':
        raise BasicError("ILLEGAL INSTRUCTION", line)

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
        # "THEN may be used in an ON statement" (manual sec. 1.7.6)
        if not p.accept_id('GOTO') and not p.accept_id('THEN'):
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
        # "IF X > 5 THEN 200 may also be written IF X > 5 GO TO 200"
        # (manual sec. 1.7.6)
        if not p.accept_id('THEN') and not p.accept_id('GOTO'):
            p.expect_id('GO')
            p.expect_id('TO')
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
        if p.accept_op('='):
            ex = p.expression()
            p.end_of_statement()
            return ('DEF', fv, params, ex)
        # no '=': a multiple-line DEF, terminated by FNEND (manual sec. 2.2)
        p.end_of_statement()
        return ('DEFML', fv, params)

    if v == 'FNEND':
        p.end_of_statement()
        return ('FNEND',)

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
        return parse_mat(p, line)

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

        # DEF registration (a DEF may occur anywhere, sec. 2.2), including
        # multiple-line DEF ... FNEND bodies.  region maps each line to the
        # enclosing multiple-line DEF (or None): transfers may not cross a
        # DEF boundary in either direction.
        self.fns = {}
        self.fnend_of = {}
        self.region = {}
        open_def = None
        for n in self.order:
            s = self.stmts[n]
            if s[0] == 'DEF':
                if s[1] in self.fns:
                    raise BasicError("FUNCTION %s DEFINED TWICE" % s[1], n)
                self.fns[s[1]] = {'ml': False, 'params': s[2],
                                  'expr': s[3], 'line': n}
            elif s[0] == 'DEFML':
                if open_def is not None:
                    raise BasicError("NESTED DEF", n)
                if s[1] in self.fns:
                    raise BasicError("FUNCTION %s DEFINED TWICE" % s[1], n)
                open_def = (s[1], s[2], n)
                # the DEF line itself is "outside": jumping to it from
                # outside simply skips over the body
                self.region[n] = None
                continue
            elif s[0] == 'FNEND':
                if open_def is None:
                    raise BasicError("FNEND WITHOUT DEF", n)
                name, params, start = open_def
                self.fns[name] = {'ml': True, 'params': params,
                                  'start': start, 'end': n}
                self.fnend_of[start] = n
                self.region[n] = name
                open_def = None
                continue
            self.region[n] = open_def[0] if open_def else None
        if open_def is not None:
            raise BasicError("UNFINISHED DEF", open_def[2])

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
        # and may not straddle a multiple-line DEF boundary.
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
            elif s[0] == 'DEFML':
                stack.append(('<DEF>', n))
            elif s[0] == 'FNEND':
                if stack and stack[-1][0] != '<DEF>':
                    raise BasicError("FOR WITHOUT NEXT", stack[-1][1])
                if stack:
                    stack.pop()
        if stack:
            raise BasicError("FOR WITHOUT NEXT", stack[-1][1])

        # All referenced line numbers must exist, and no transfer may cross
        # into or out of a multiple-line DEF (manual sec. 2.2)
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
                if self.region.get(n) != self.region.get(t):
                    raise BasicError("TRANSFER INTO OR OUT OF DEF", n)

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


def _invert(m, n):
    """Invert the n-by-n matrix m (a list of lists, destroyed) by
    Gauss-Jordan elimination with partial pivoting.

    Returns (inverse, determinant); (None, 0.0) if singular -- inverting
    a singular matrix must not stop the program (manual sec. 2.6).
    """
    inv = [[1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    det = 1.0
    for col in range(n):
        pivot = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[pivot][col]) < 1e-300:
            return None, 0.0
        if pivot != col:
            m[col], m[pivot] = m[pivot], m[col]
            inv[col], inv[pivot] = inv[pivot], inv[col]
            det = -det
        p = m[col][col]
        det *= p
        for j in range(n):
            m[col][j] /= p
            inv[col][j] /= p
        for r in range(n):
            if r == col:
                continue
            factor = m[r][col]
            if factor == 0.0:
                continue
            for j in range(n):
                m[r][j] -= factor * m[col][j]
                inv[r][j] -= factor * inv[col][j]
    return inv, det


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
        self.x = (_time_seed() % (RND_M - 2)) + 1


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
        self.num_val = 0.0      # NUM: components from the last MAT INPUT
        self.det_val = 0.0      # DET: determinant from the last INV
        self.rng = Rand()       # reseeded identically on every RUN
        for name, dims in prog.dims.items():
            self.arrays[name] = self._new_array(dims, 0.0)
        for name, dims in prog.sdims.items():
            self.sarrays[name] = self._new_array(dims, '')

    @staticmethod
    def _new_array(dims, fill):
        # 'decl' is the declared (capacity) bound per axis -- from DIM or
        # the automatic 10 -- and never changes; 'cur' is the current
        # logical dimension, which MAT instructions may change (sec. 2.6).
        # The buffer is allocated at full capacity once: redimensioning
        # only changes 'cur' (and hence the row stride), which reproduces
        # the manual's element-relocation behavior.
        size = dims[0] + 1
        if len(dims) == 2:
            size *= dims[1] + 1
        return {'decl': dims, 'cur': tuple(dims), 'data': [fill] * size}

    # --- variables and arrays ------------------------------------------

    def get_array(self, name, nsubs, line, string=False):
        table = self.sarrays if string else self.arrays
        arr = table.get(name)
        if arr is None:
            dims = (AUTO_BOUND,) * nsubs
            arr = self._new_array(dims, '' if string else 0.0)
            table[name] = arr
        if len(arr['decl']) != nsubs:
            raise BasicError("INCORRECT NUMBER OF SUBSCRIPTS FOR '%s'" % name, line)
        return arr

    def _flat(self, arr, idx_vals, line):
        # bounds are checked against the current dimensions: identical to
        # the declared bounds until a MAT instruction redimensions the
        # array (which may legally make an axis larger than its DIM bound,
        # within total capacity -- manual sec. 2.6 ZER(25,5) example)
        cur = arr['cur']
        ints = []
        for v in idx_vals:
            i = iround(v)
            ints.append(i)
        for i, bound in zip(ints, cur):
            if i < 0 or i > bound:
                raise BasicError("SUBSCRIPT ERROR", line)
        if len(cur) == 1:
            return ints[0]
        return ints[0] * (cur[1] + 1) + ints[1]

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
        if op == 'numfn':
            return self.num_val
        if op == 'detfn':
            return self.det_val
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
            if name == 'COT':
                s = math.sin(x)
                if s == 0:
                    self.warn("DIVISION BY ZERO", line)
                    return MAXNUM
                return self._check_range(math.cos(x) / s, line)
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
        # inside a multiple-line DEF the bare function name (no argument
        # list) denotes the temporary return value, not a recursive call
        if not arg_asts:
            for scope in reversed(self.locals):
                if name in scope:
                    return scope[name]
        if name not in self.prog.fns:
            raise BasicError("UNDEFINED FUNCTION %s" % name, line)
        fn = self.prog.fns[name]
        params = fn['params']
        if len(arg_asts) != len(params):
            raise BasicError("INCORRECT NUMBER OF ARGUMENTS FOR %s" % name, line)
        if len(self.locals) > 50:
            raise BasicError("FUNCTIONS NESTED TOO DEEPLY", line)
        args = [self.eval_num(a, line) for a in arg_asts]
        if fn['ml']:
            return self.call_multiline(name, fn, args)
        self.locals.append(dict(zip(params, args)))
        try:
            return self.eval_num(fn['expr'], fn['line'])
        finally:
            self.locals.pop()

    def call_multiline(self, name, fn, args):
        """Execute the body of a DEF ... FNEND function (manual sec. 2.2).

        The bare function name acts as a temporary variable holding the
        return value; all other non-parameter variables are global.
        """
        scope = dict(zip(fn['params'], args))
        scope[name] = 0.0
        self.locals.append(scope)
        for_depth = len(self.for_stack)
        gosub_depth = len(self.gosub_stack)
        end = fn['end']
        i = self.prog.index[fn['start']] + 1
        try:
            while True:
                ln = self.prog.order[i]
                if ln == end:
                    break
                r = self.exec_stmt(self.prog.stmts[ln], ln)
                if r is None:
                    i += 1
                elif r[1] == end:
                    break
                elif r[0] == 'goto':
                    i = self.prog.index[r[1]]
                else:   # 'after'
                    i = self.prog.index[r[1]] + 1
            return scope[name]
        finally:
            self.locals.pop()
            del self.for_stack[for_depth:]
            del self.gosub_stack[gosub_depth:]

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
        elif kind == 'fnvar':
            # LET FNM = ... : only meaningful while FNM is executing
            if isinstance(value, str):
                raise BasicError("MISMATCHED STRING OPERATION", line)
            for scope in reversed(self.locals):
                if lv[1] in scope:
                    scope[lv[1]] = value
                    return
            raise BasicError("%s ASSIGNED OUTSIDE ITS DEF" % lv[1], line)
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
        if op == 'DEFML':
            # a multiple-line DEF body executes only when called
            return ('after', self.prog.fnend_of[line])
        if op == 'FNEND':
            raise BasicError("FNEND OUTSIDE OF FUNCTION CALL", line)
        if op == 'MATREAD':
            return self.do_mat_read(s[1], line)
        if op == 'MATPRINT':
            return self.do_mat_print(s[1], line)
        if op == 'MATINPUT':
            return self.do_mat_input(s[1], line)
        if op == 'MATASSIGN':
            return self.do_mat_assign(s[1], s[2], line)
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
        if len(s) > arr['decl'][0]:
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
        if n < 0 or n > arr['decl'][0]:
            raise BasicError("SUBSCRIPT ERROR IN CHANGE", line)
        chars = []
        for i in range(1, n + 1):
            code = iround(arr['data'][i])
            if code < 0 or code > 127:
                raise BasicError("ILLEGAL CHARACTER CODE IN CHANGE", line)
            chars.append(chr(code))
        self.svars[svname] = ''.join(chars)
        return None

    # --- MAT statements (manual sec. 2.6, strings sec. 2.7) ----------------
    # Every vector has a component 0 and every matrix a row 0 and column 0,
    # but the MAT instructions ignore them; they do count toward the
    # capacity set by DIM.

    def _mat_array(self, name, line, nsubs=None):
        """Fetch (auto-creating) an array for a MAT instruction."""
        string = name.endswith('$')
        table = self.sarrays if string else self.arrays
        if name not in table and nsubs is None:
            # unseen name, shape unspecified: vectors for strings,
            # 10-by-10 matrices for numerics (sec. 2.6)
            nsubs = 1 if string else 2
        if nsubs is None:
            nsubs = len(table[name]['decl'])
        return self.get_array(name, nsubs, line, string=string)

    def _mat_redim(self, arr, dims, line):
        if len(dims) != len(arr['decl']):
            raise BasicError("DIMENSION ERROR", line)
        need = 1
        for d in dims:
            if d < 1:
                raise BasicError("DIMENSION ERROR", line)
            need *= d + 1
        # the zero rows/columns count toward the capacity limit
        if need > len(arr['data']):
            raise BasicError("DIMENSION ERROR", line)
        arr['cur'] = tuple(dims)

    def _eval_dims(self, dim_exprs, line):
        return [iround(self.eval_num(e, line)) for e in dim_exprs]

    def _mget(self, arr, i, j=None):
        if j is None:
            return arr['data'][i]
        return arr['data'][i * (arr['cur'][1] + 1) + j]

    def _mset(self, arr, i, j, v):
        if j is None:
            arr['data'][i] = v
        else:
            arr['data'][i * (arr['cur'][1] + 1) + j] = v

    def do_mat_read(self, items, line):
        for name, dim_exprs in items:
            string = name.endswith('$')
            if dim_exprs:
                arr = self._mat_array(name, line, nsubs=len(dim_exprs))
                self._mat_redim(arr, self._eval_dims(dim_exprs, line), line)
            else:
                arr = self._mat_array(name, line)
            cur = arr['cur']
            if len(cur) == 1:
                spots = [(i, None) for i in range(1, cur[0] + 1)]
            else:
                spots = [(i, j) for i in range(1, cur[0] + 1)
                         for j in range(1, cur[1] + 1)]
            for i, j in spots:
                if string:
                    if self.sptr >= len(self.prog.data_str):
                        raise BasicError("OUT OF DATA", line)
                    self._mset(arr, i, j, self.prog.data_str[self.sptr])
                    self.sptr += 1
                else:
                    if self.nptr >= len(self.prog.data_num):
                        raise BasicError("OUT OF DATA", line)
                    self._mset(arr, i, j, self.prog.data_num[self.nptr])
                    self.nptr += 1
        return None

    def _mat_item(self, v):
        if isinstance(v, str):
            self.printer.write_item(v)
        else:
            self.printer.write_item(fmt_number(v))

    def do_mat_print(self, items, line):
        pr = self.printer
        for name, fmt in items:
            arr = self._mat_array(name, line)
            cur = arr['cur']
            if pr.col > 0:
                pr.newline()
            if len(cur) == 1 and fmt == 'plain':
                # a vector prints as a column vector (sec. 2.6)
                for i in range(1, cur[0] + 1):
                    self._mat_item(self._mget(arr, i))
                    pr.newline()
                continue
            # rows of a matrix; a vector with ',' or ';' is one row
            nrows = 1 if len(cur) == 1 else cur[0]
            ncols = cur[0] if len(cur) == 1 else cur[1]
            for r in range(1, nrows + 1):
                for c in range(1, ncols + 1):
                    if len(cur) == 1:
                        self._mat_item(self._mget(arr, c))
                    else:
                        self._mat_item(self._mget(arr, r, c))
                    if fmt != 'packed' and c < ncols:
                        pr.zone_advance()
                pr.newline()
        return None

    def do_mat_input(self, name, line):
        string = name.endswith('$')
        arr = self._mat_array(name, line, nsubs=1)   # always a vector
        if len(arr['decl']) != 1:
            raise BasicError("DIMENSION ERROR", line)
        while True:
            vals = []
            more = True
            while more:
                self.printer.emit('? ')
                self.printer.flush()
                raw = self.stdin.readline()
                if raw == '':
                    raise BasicError("END OF INPUT", line)
                raw = raw.rstrip('\n').rstrip('\r').rstrip()
                self.printer.col = 0
                if not self.interactive and not self.stdin.isatty():
                    self.printer.out.write('\n')
                # a trailing & asks for more input on the next line
                more = raw.endswith('&')
                if more:
                    raw = raw[:-1]
                if raw.strip():
                    for item in split_csv(raw):
                        item = item.strip()
                        if (item.startswith('"') and item.endswith('"')
                                and len(item) >= 2):
                            vals.append(('S', item[1:-1]))
                        else:
                            vals.append(('U', item))
            if len(vals) > arr['decl'][0]:
                raise BasicError("DIMENSION ERROR", line)
            try:
                converted = []
                for typ, item in vals:
                    if string:
                        converted.append(item)
                    else:
                        if typ == 'S':
                            raise BasicError(
                                "INPUT DATA NOT IN CORRECT FORMAT", line)
                        try:
                            converted.append(float(item))
                        except ValueError:
                            raise BasicError(
                                "INPUT DATA NOT IN CORRECT FORMAT", line)
            except BasicError:
                if self.interactive:
                    self.printer.emit(
                        'INPUT DATA NOT IN CORRECT FORMAT -- RETYPE IT')
                    self.printer.newline()
                    continue
                raise
            self.num_val = float(len(converted))
            if converted:
                arr['cur'] = (len(converted),)
                for i, v in enumerate(converted, start=1):
                    self._mset(arr, i, None, v)
            return None

    def _mat_as_2d(self, arr):
        """Shape for multiplication: a vector is a column vector (n,1)."""
        cur = arr['cur']
        if len(cur) == 1:
            return cur[0], 1
        return cur

    def do_mat_assign(self, target, rhs, line):
        kind = rhs[0]

        if kind == 'fill':                      # ZER, CON, IDN
            fname, dim_exprs = rhs[1], rhs[2]
            if dim_exprs:
                arr = self._mat_array(target, line, nsubs=len(dim_exprs))
                self._mat_redim(arr, self._eval_dims(dim_exprs, line), line)
            else:
                arr = self._mat_array(target, line)
            cur = arr['cur']
            if fname == 'IDN':
                if len(cur) != 2 or cur[0] != cur[1]:
                    raise BasicError("DIMENSION ERROR", line)
                for i in range(1, cur[0] + 1):
                    for j in range(1, cur[1] + 1):
                        self._mset(arr, i, j, 1.0 if i == j else 0.0)
                return None
            v = 0.0 if fname == 'ZER' else 1.0
            if len(cur) == 1:
                for i in range(1, cur[0] + 1):
                    self._mset(arr, i, None, v)
            else:
                for i in range(1, cur[0] + 1):
                    for j in range(1, cur[1] + 1):
                        self._mset(arr, i, j, v)
            return None

        if kind == 'copy':
            src = self._mat_array(rhs[1], line)
            dst = self._mat_array(target, line, nsubs=len(src['decl']))
            self._mat_redim(dst, list(src['cur']), line)
            self._mat_map(dst, src, src, lambda a, b: a)
            return None

        if kind in ('add', 'sub'):
            a = self._mat_array(rhs[1], line)
            b = self._mat_array(rhs[2], line)
            if a['cur'] != b['cur'] or len(a['decl']) != len(b['decl']):
                raise BasicError("DIMENSION ERROR", line)
            dst = self._mat_array(target, line, nsubs=len(a['decl']))
            self._mat_redim(dst, list(a['cur']), line)
            if kind == 'add':
                self._mat_map(dst, a, b, lambda x, y: x + y)
            else:
                self._mat_map(dst, a, b, lambda x, y: x - y)
            return None

        if kind == 'scal':                      # MAT C = (K) * A
            k = self.eval_num(rhs[1], line)
            a = self._mat_array(rhs[2], line)
            dst = self._mat_array(target, line, nsubs=len(a['decl']))
            self._mat_redim(dst, list(a['cur']), line)
            self._mat_map(dst, a, a, lambda x, y: k * x)
            return None

        if kind == 'trn':
            if target == rhs[1]:
                raise BasicError("ILLEGAL MAT TRANSPOSE", line)
            a = self._mat_array(rhs[1], line)
            if len(a['cur']) != 2:
                raise BasicError("DIMENSION ERROR", line)
            m, n = a['cur']
            dst = self._mat_array(target, line, nsubs=2)
            self._mat_redim(dst, [n, m], line)
            for i in range(1, n + 1):
                for j in range(1, m + 1):
                    self._mset(dst, i, j, self._mget(a, j, i))
            return None

        if kind == 'mul':
            if target in (rhs[1], rhs[2]):
                raise BasicError("ILLEGAL MAT MULTIPLE", line)
            a = self._mat_array(rhs[1], line)
            b = self._mat_array(rhs[2], line)
            m, p = self._mat_as_2d(a)
            p2, n = self._mat_as_2d(b)
            if p != p2:
                raise BasicError("DIMENSION ERROR", line)
            dst = self._mat_array(target, line)
            if len(dst['decl']) == 1:
                if n != 1:
                    raise BasicError("DIMENSION ERROR", line)
                self._mat_redim(dst, [m], line)
            else:
                self._mat_redim(dst, [m, n], line)

            def aget(i, k):
                return (self._mget(a, i) if len(a['cur']) == 1
                        else self._mget(a, i, k))

            def bget(k, j):
                return (self._mget(b, k) if len(b['cur']) == 1
                        else self._mget(b, k, j))

            for i in range(1, m + 1):
                for j in range(1, n + 1):
                    total = 0.0
                    for k2 in range(1, p + 1):
                        total += aget(i, k2) * bget(k2, j)
                    if len(dst['cur']) == 1:
                        self._mset(dst, i, None, total)
                    else:
                        self._mset(dst, i, j, total)
            return None

        if kind == 'inv':
            a = self._mat_array(rhs[1], line)
            if len(a['cur']) != 2 or a['cur'][0] != a['cur'][1]:
                raise BasicError("DIMENSION ERROR", line)
            n = a['cur'][0]
            work = [[self._mget(a, i, j) for j in range(1, n + 1)]
                    for i in range(1, n + 1)]
            inv, det = _invert(work, n)
            self.det_val = det
            dst = self._mat_array(target, line, nsubs=2)
            self._mat_redim(dst, [n, n], line)
            for i in range(1, n + 1):
                for j in range(1, n + 1):
                    # a singular matrix does not stop the program; DET is
                    # set to 0 (sec. 2.6) and the result here is zeros
                    self._mset(dst, i, j,
                               inv[i - 1][j - 1] if inv is not None else 0.0)
            return None

        raise BasicError("ILLEGAL MAT FUNCTION", line)

    def _mat_map(self, dst, a, b, f):
        """dst = f(a, b) elementwise over the current dimensions."""
        cur = dst['cur']
        if len(cur) == 1:
            for i in range(1, cur[0] + 1):
                self._mset(dst, i, None,
                           f(self._mget(a, i), self._mget(b, i)))
        else:
            for i in range(1, cur[0] + 1):
                for j in range(1, cur[1] + 1):
                    self._mset(dst, i, j,
                               f(self._mget(a, i, j), self._mget(b, i, j)))


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
        interp = Interp(prog, sys.stdin, sys.stdout)
        interp.run()
        if interp.printer.col > 0:      # complete a partial final line
            interp.printer.newline()
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
        # the RUN header starts one space in (manual pp. 10, 24, 27, 60)
        # and is followed by two blank lines (pp. 42-45, 60, 62)
        print(" %-9s%s      %s" % (self.name, time.strftime('%H:%M'),
                                   time.strftime('%m/%d/%y')))
        print()
        print()
        t0 = _cpu_time()
        interp = Interp(prog, sys.stdin, sys.stdout, interactive=True)
        try:
            interp.run()
        except KeyboardInterrupt:
            if interp.printer.col > 0:
                interp.printer.newline()
            print("STOPPED AT USER REQUEST")
        # one carriage return before TIME, unconditionally: a partial
        # final line is completed (pp. 44-45: TIME sits directly under
        # ;-packed output), a completed one yields a blank line (p. 43)
        if interp.printer.col > 0:
            interp.printer.newline()
        else:
            print()
        print("TIME:  %.2f SECS." % (_cpu_time() - t0))
        print()                          # LF after TIME (pp. 43, 45)

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
        # one blank line after the LIST command, one after the heading,
        # and two before the READY that follows (manual p. 32)
        print()
        if heading:
            print("%-9s%s      %s" % (self.name, time.strftime('%H:%M'),
                                      time.strftime('%m/%d/%y')))
            print()
        for n in sorted(self.lines):
            if lo <= n <= hi:
                print("%d %s" % (n, self.lines[n]))
        print()
        print()

    def cmd_save(self, replace=False):
        if not os.path.isdir(self.libdir):
            os.makedirs(self.libdir)
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
