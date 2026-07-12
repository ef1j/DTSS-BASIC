# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

A faithful reimplementation of **Dartmouth BASIC, Fourth Edition (1968)** as a
single-module Python CLI interpreter (`dbasic.py`), built to run period-accurate
1968–69 DTSS-era BASIC programs — most notably a reconstruction of Joshua
Spahn's `LOVE` program — and reproduce their teleprinter output exactly.

The **normative sources** are `SPEC_dartmouth_basic_v4.md` (the build spec) and
the scanned manual `Dartmouth-BASIC-manuals/196801_BASIC_4th_Edition.pdf`
(image-only PDF — no text layer; read pages visually; manual page N ≈ PDF page
N+4..5). Where the manual and a working period program conflict, the acceptance
tests win and the choice is recorded in README.md's DEVIATIONS section — keep
that list in sync with any behavior change.

The other top-level directories (`LOVE-listings/`, `Dartmouth BASIC programs/`,
`Ahl-BASIC-Games/`, `Spahn-bio/`, `dhq-journal/`, etc.) are the author's
research archive, not part of the deliverable; don't modify them.

## Commands

- Run the tests: `make test` (= `python3 -m unittest discover -s tests -v`;
  pytest also works: `python3 -m pytest tests/`)
- Run a single test class/method:
  `python3 -m unittest tests.test_dbasic.T2ColumnLocked -v`
- Run a program in batch mode: `python3 dbasic.py library/LOVE`
- Interactive DTSS session: `python3 dbasic.py` (`--library DIR` to relocate
  the program library)

Constraints: Python 3.8+, **standard library only** — no third-party runtime or
test dependencies.

**Two interpreter files, kept in sync:** `dbasic.py` (primary, clean Python 3)
and `dbasic2.py` (a Python 2.7 fork for the author's legacy machine — same
code plus `__future__` imports and small shims). **After changing dbasic.py,
regenerate the fork with `make fork`** (runs `tools/make_fork.py`, a
mechanical transform — its substitution list asserts exact occurrence counts,
so it fails loudly if dbasic.py drifts from its expectations; update the list
when adding py3-only constructs). The `Python2Fork` tests enforce
byte-identical output under Python 3 always, and under `python2` when
available. Avoid py3-only syntax (no f-strings in either file; `%`-formatting
is the house style). **Py2 semantic traps to avoid in shared code:**
`math.floor` returns a *float* on Python 2 — wrap in `int()` whenever the
result feeds `round(x, n)`, a `%.*f` width, an index, or a slice; `/` between
ints is floor division there (the fork's `from __future__ import division`
handles this, but don't rely on int/int `/` anyway); `round()` half-ties
differ (use `iround`).

## Architecture

Everything lives in `dbasic.py` (~1000 lines), deliberately one module:

- **Lexer/Parser** — free-form carving lexer + recursive-descent `Parser`.
  Source is space-insensitive outside quotes (DTSS behavior): spaces are
  deleted per statement at compile time, then keywords are carved from
  letter runs longest-first (`LEX_KEYWORDS`); V4's letter+optional-digit
  variable names make this unambiguous. Statements parse to plain tuples,
  expressions to nested AST tuples (`('bin','+',l,r)` etc.). Precedence:
  `^` > unary `-` > `*` `/` > `+` `-` (and `A^B^C` is left-associative,
  manual p. 12). `REM` and `DATA` are handled from raw text *before* the
  space-strip (unquoted DATA strings keep interior spaces).
- **`Program`** — compile step: parses every line, builds the **two separate
  DATA pools** (numeric and string — genuinely independent, manual §2.7),
  registers `DEF` functions and `DIM`s, statically pairs FOR/NEXT (proper
  nesting enforced; map used for zero-trip skips), verifies every referenced
  line number exists, requires an `END`.
- **`Interp`** — runtime: walks lines in ascending numeric order; statements
  return `None` (fall through), `('goto', line)`, or `('after', line)`.
  Runtime FOR stack tolerates GOTO-abandoned inner loops; GOSUB stack for
  RETURN. Fresh fixed-seed Lehmer RNG per run makes `RND` repeatable across
  runs *and* Python versions (a correctness requirement — don't "improve" it).
- **`Printer`** — the teleprinter model and the highest-fidelity-risk area
  (T1/T2 depend on it): 75-column line, five 15-column zones, `,` zone
  advance, `;` packing (strings emit nothing extra — `PRINT "L";` is exactly
  `L`; numbers are sign-or-space + value + one trailing space), trailing
  `,`/`;` suppresses the newline, `TAB` is forward-only mod 75, lines break
  before an item that would cross column 75, trailing spaces never trimmed.
  Numeric formatting (`fmt_mag`) implements manual §2.1's four rules exactly
  (≤8-digit integers plain, `3.24376 E+10` E-notation — with a space before
  the E, per the manual's teletype samples — 6 significant digits, <0.1
  rules, trailing zeros dropped).
- **`Repl`** — thin DTSS-style command environment (NEW/OLD/SAVE/REPLACE/
  UNSAVE/LIST/LISTNH/RUN/SCRATCH/RENAME/CATALOG/LENGTH/BYE) over the same
  `Program`/`Interp` core; batch and interactive must never duplicate
  execution logic.
- `CHANGE` uses ASCII codes (that *is* the manual's §2.7 table: space=32,
  A–Z=65–90).

## Fidelity rules that are easy to break

- `IF … THEN` takes **only a line number** — rejecting `THEN <statement>` is
  tested (T3).
- Exactly one statement per line; `:` must be **rejected**, not supported.
- Documented tolerances for period programs (see README DEVIATIONS): line
  number 0 and `RND(dummy-arg)` — both used by FTBALL (1965, written under
  an earlier BASIC edition). PRINT item juxtaposition is NOT a tolerance:
  it's documented manual behavior (§1.7.3 type (c)), as are `IF … GO TO`,
  `ON … THEN`, and end-of-line `'` remarks (§2.5, not on DATA lines).
  `END` however is strict per the manual:
  present, unique, and the **last line** (`END IS NOT LAST` otherwise) —
  DTSS was a one-pass compiler, so trailing DATA after END is rejected;
  the bundled LOVE programs have END renumbered to 999 for this reason.
- Non-goals: no `MID$`-family, no `PRINT USING`, no multi-statement lines, no
  GUI. `MAT` (all thirteen §2.6 instructions, plus string-vector forms and
  `NUM`/`DET`) and multiple-line `DEF`/`FNEND` (§2.2) are implemented. Key
  MAT invariants: arrays carry `decl` (capacity bounds, fixed) and `cur`
  (current logical dims, changed by redimensioning); the buffer is allocated
  once at full capacity and redimensioning only changes the stride, which
  reproduces the manual's element-relocation behavior; MAT ops work on
  indices 1..m ignoring row/column 0.
- Runtime arithmetic anomalies are **warnings, not errors** (manual §2.8):
  the interpreter prints the manual's message (`DIVISION BY ZERO`, `LOG OF
  ZERO`, `LOG OF NEGATIVE NUMBER`, `SQUARE ROOT OF A NEGATIVE NUMBER`,
  `OVERFLOW`, `UNDERFLOW`, `EXP TOO LARGE`, `ZERO TO A NEGATIVE POWER`,
  `ABSOLUTE VALUE RAISED TO POWER`), supplies the documented value
  (±1.70141E+38 for ∞, 0 for underflow, ABS-variants otherwise), and
  **continues**. Only the §2.8 "program stops" errors are fatal (`OUT OF
  DATA`, `SUBSCRIPT ERROR`, `RETURN BEFORE GOSUB`, `ON EVALUATED OUT OF
  RANGE`, `MISMATCHED STRING OPERATION`, …). Don't invent message text —
  use the manual's vocabulary.
- Batch mode: program output on stdout only; warnings and errors on stderr,
  exit 1 only for fatal errors. Interactive mode prints warnings inline.

## Tests (tests/test_dbasic.py)

T1: `library/LOVE` output rows 5–40 must match the space/non-space mask of all
36 rows of `tests/fixtures/LOVE.txt`. T2: `library/LOVE2` (column-locked
variant, letter = column mod 4 into "LOVE") must equal `LOVE.txt` **character
for character** — this pins the PRINT engine; treat any change that touches it
as suspect until T2 passes. T3: unit tests pinning exact output strings
(including numeric formats like `' 1  2 -3 \n'`). T4: FTBALL smoke on canned
stdin (exit 0 or 1 both acceptable — canned input may run out — but never a
traceback). Tests run the interpreter as a subprocess, so they exercise real
batch-mode behavior including exit codes and stderr.
