# dbasic — Dartmouth BASIC, Fourth Edition (1968)

`dbasic` is a command-line interpreter for **Dartmouth BASIC, Fourth Edition** —
the dialect documented in *BASIC, Fourth Edition* (John G. Kemeny and Thomas E.
Kurtz, Dartmouth College Computation Center, 1 January 1968) and available on
the Dartmouth Time-Sharing System (DTSS) in 1968–69. Its purpose is to run
period-accurate BASIC programs of that era — in particular a reconstruction of
Joshua Spahn's 1969 `LOVE` program — and reproduce their teleprinter output
exactly.

Python 3.8+, standard library only. No third-party dependencies.

## Provenance

This is a **modern reimplementation of the Dartmouth BASIC Fourth Edition
language, built from the 1968 manual**. It is *not* the original DTSS software
(the 1968 compiler does not survive) and *not* an emulation of the DTSS
operating system or its hardware (a GE-635 with DATANET-30 front end by the
Fourth Edition era; the GE-225/235 was the original 1964 machine). It is a tool for
demonstrating that period-accurate programs run and produce the expected
output under Fourth-Edition semantics; it is evidence of feasibility, not of
what any historical author actually wrote.

## Related work, and how this project differs

Several open-source projects touch Dartmouth BASIC; none has this project's
goal — **byte-exact Fourth Edition (1968) teleprinter output from the manual
as sole normative source** — which is why it exists. A detailed comparison
and validation plan is in `PLAN_comparative_validation.md`.

- **[cpp-tutor/dbasic](https://github.com/cpp-tutor/dbasic)** — a *compiler*
  (D language, targeting LLVM IR) for the early Dartmouth BASICs, with a
  command-line switch that gates keywords by historical edition (currently
  First–Fourth) and a test corpus built from the manuals' own page-numbered
  examples. The closest project in spirit; complementary rather than
  overlapping. It lexes classic free-form source (`15LETG=A*E-B*D`) and
  lints editions; it does not model the 75-column teleprinter, the §2.1
  numeric-output rules, the §2.8 warn-and-continue arithmetic, or the
  manual's error vocabulary — the fidelity surface this interpreter pins
  with byte-exact tests. It also omits the `#` not-equal synonym.
- **[WA6YDQ/dbasic](https://github.com/WA6YDQ/dbasic)** — an interactive C
  interpreter that follows 1968 rules *with declared exceptions*, and the
  exceptions redefine the language: `**` replaces `^` (breaking every
  historical program that exponentiates), `!=` is accepted, variables are
  bare `A`–`Z` only, `GO TO` must be written `GOTO`, MAT is absent, and
  post-1968 features (`MID$`-family functions, string `+`, logical
  operators) are added. A retro-styled modern dialect — a legitimate goal,
  but the opposite of this project's compliance policy, under which every
  one of those choices is a rejected modernism.
- **[maurymarkowitz/RetroBASIC](https://github.com/maurymarkowitz/RetroBASIC)**
  — a C (lex/yacc) interpreter whose goal is breadth: one runtime for
  "almost any dialect from the era" (MS, Dartmouth V4, HP Timeshared,
  Tiny, DEC), with per-dialect switches (`--array-base`, string slicing)
  and a static-statistics mode that surveys feature usage across vintage
  programs — a genuinely useful research instrument. The design trade is
  the mirror image of ours: RetroBASIC relaxes any single dialect's rules
  so that *every* dialect's programs run; this project fixes exactly one
  edition and enforces it, so that a program's running here *means*
  something about 1968. Neither substitutes for the other.
- **[maurymarkowitz/Illustrating-BASIC](https://github.com/maurymarkowitz/Illustrating-BASIC)**
  — transcriptions of the programs in Donald Alcock's *Illustrating BASIC*
  (1977), labeled "Dartmouth V4"; RetroBASIC (above, same author) is its
  intended runtime. Valuable as a breadth corpus (its MAT programs run
  here), but its dialect is looser than the 1 January 1968 manual: it
  exercises `PRINT USING`, which postdates the Fourth Edition and is a
  documented non-goal here.
- **[timereshared/project-tpk](https://github.com/timereshared/project-tpk)**
  — the Trabb Pardo–Knuth algorithm on vintage systems, including
  execution transcripts from the *revived DTSS itself*. Not an
  implementation to compare against but ground truth to validate with:
  its transcript's numeric formatting matches this interpreter's §2.1
  formatter, and its BASIC source exposed one genuine gap (blank numbered
  lines — see DEVIATIONS).

In short: existing projects modernize the dialect (WA6YDQ), compile rather
than interpret with a different fidelity surface (cpp-tutor), or supply
corpora and ground truth (Illustrating-BASIC, project-tpk). This project's
niche — a readable, dependency-free interpreter whose output is tested
character-for-character against the 1968 manual's samples and period
teleprinter captures — is not otherwise occupied.

## Usage

### Batch mode (primary, reproducible)

```
python3 dbasic.py PROGRAM
```

Loads `PROGRAM`, runs it, writes output to stdout, and exits 0 (non-zero on a
BASIC error; error messages go to stderr). `INPUT` reads from stdin; reaching
`INPUT` after stdin is exhausted is a clean error, not a hang.

```
python3 dbasic.py library/LOVE       # print the LOVE image
python3 dbasic.py library/FTBALL     # play Kemeny's 1965 football game
```

### Interactive mode (DTSS-style session)

```
python3 dbasic.py [--library DIR]
```

Starts a classic command environment. Type numbered lines to build a program
(re-entering a number replaces the line; a bare number deletes it) and use the
commands:

| Command | Effect |
|---|---|
| `NEW <name>` / `OLD <name>` | start a fresh program / load one from the library (prompts for the name if omitted) |
| `SAVE` / `REPLACE` / `UNSAVE` | save to the library (SAVE refuses to overwrite; REPLACE overwrites) / remove |
| `LIST [n1[-n2]]`, `LISTNH` | list the program (LISTNH: no heading) |
| `RUN` | run the current program |
| `SCRATCH` | erase the program, keep the name |
| `RENAME <name>` | rename the workspace |
| `CATALOG` (`CAT`) | list saved programs |
| `LENGTH` | program size in characters |
| `BYE` (`GOODBYE`) | exit |

Program names are 1–6 letters/digits (the historical constraint). The library
is a directory (default `./library`), one plain-text file per program, named
after the program; LF and CR/LF files are both accepted.

### Legacy machines (Python 2.7)

`dbasic2.py` is a maintained-in-parallel fork of `dbasic.py` for old
machines that have no `python3`:

```
python2 dbasic2.py library/LOVE
```

It differs only in small compatibility shims (`__future__` imports,
`raw_input`, `time.clock`, …) and must produce byte-identical output to
`dbasic.py`; the test suite verifies this equivalence (always under
Python 3, and additionally under `python2` when one is installed).
`dbasic.py` remains the primary, clean-Python-3 version.

### Installing a `dbasic` entry point (optional)

```
pip install .
dbasic library/LOVE
```

## Tests

```
make test                # or: python3 -m unittest discover -s tests -v
                         # or: python3 -m pytest tests/
```

The suite implements the acceptance tests of the build spec:

- **T1** — `library/LOVE` (the Spahn reconstruction, letters flow freely) must
  reproduce the space/non-space mask of all 36 rows of `tests/fixtures/LOVE.txt`.
- **T2** — `library/LOVE2` (a column-locked variant, letters pinned to
  absolute columns) must reproduce `LOVE.txt` **exactly, character for
  character**.
- **T3** — unit tests: PRINT zones vs. packed `;`, trailing-separator newline
  suppression, TAB, the manual's numeric output rules, FOR/NEXT with STEP and
  boundaries, 1-D/2-D arrays and bounds, GOSUB/RETURN nesting, ON…GO TO,
  CHANGE round-trips, string vectors, separate numeric/string DATA pools,
  IF…THEN line-number-only, rejection of multi-statement lines, RND
  repeatability, the full MAT set (including the manual's own MATRIX
  example program and its redimensioning examples), and multiple-line
  DEF/FNEND (including the manual's max and factorial examples).
- **T4** — `library/FTBALL` runs on canned stdin without crashing.

## Language summary

Statements: `LET` (keyword required), `READ` / `DATA` / `RESTORE` (also
`RESTORE*` numeric-only and `RESTORE$` string-only, per manual §2.7), `PRINT`,
`GO TO` / `GOTO`, `ON … GO TO`, `IF … THEN <line>`, `FOR … TO … [STEP]` /
`NEXT`, `DIM`, `DEF FNA`–`FNZ` (single-line with zero or more arguments, and
multiple-line `DEF` … `FNEND` per §2.2, where `LET FNx = …` sets the return
value and transfers may not cross the DEF boundary), `GOSUB` / `RETURN`,
`INPUT`, `CHANGE`, `REM`, `RANDOMIZE` (`RANDOM`), `STOP`, `END`. Two
interchangeable spellings from §1.7.6: `IF … GO TO <line>` for `IF … THEN
<line>`, and `ON … THEN` for `ON … GO TO`. Comments are `REM` lines or an
end-of-line apostrophe remark (§2.5; on a line ending in an unquoted string,
such as a `DATA` item, the apostrophe is part of the string — the manual's
own caveat). In `PRINT`, a quoted label may be juxtaposed directly against
an expression with no separator (`PRINT "THE VALUE OF X IS" X` — §1.7.3
type (c)).

The thirteen `MAT` instructions of §2.6 are implemented: `MAT READ` (with
redimensioning, e.g. `MAT READ A(M,N)`), `MAT PRINT` (`;` packed, `,` zones;
vectors print as columns by default), `MAT INPUT` (variable-length, `&`
continues on the next line, `NUM` gives the count), `MAT C = A`, `A + B`,
`A - B`, `A * B`, `(K) * A`, `TRN(A)`, `INV(A)` (with `DET`), `ZER`, `CON`,
`IDN` — including the string-vector forms of `MAT READ/PRINT/INPUT` (§2.7).
MAT instructions ignore row and column 0, which still count toward the
capacity set by `DIM`; redimensioning relocates elements exactly as the
manual describes.

Functions: `SIN COS TAN ATN EXP LOG ABS SQR INT RND SGN`, plus `TAB(n)`
inside `PRINT` and the parameterless `NUM` and `DET`. `RND` takes no
argument and yields the **same sequence on every RUN** unless the program
executes `RANDOMIZE` (manual §2.2).

PRINT follows the manual's 75-column, five-zone teleprinter model: `,`
advances to the next 15-column zone (to a new line from the fifth zone); `;`
packs — quoted strings and string values print with nothing added
(`PRINT "L";` emits exactly `L`), numbers print as sign-or-space, value, one
trailing space; a statement ending in `,` or `;` suppresses the newline;
`TAB(n)` (argument reduced mod 75) moves forward only. Trailing spaces are
never trimmed. Numeric output follows §2.1: integers up to 8 digits print
plain, larger in E-notation (`3.24376 E+10`); non-integers print at most six
significant digits; magnitudes below 0.1 use E-notation unless the
significant part fits in six decimal places; trailing zeros and a bare
decimal point are dropped.

`CHANGE A$ TO N` / `CHANGE N TO A$` convert between a string and a vector of
character codes with the length in element 0. The manual's code table
(§2.7) is ASCII: space = 32, `A`–`Z` = 65–90, `0`–`9` = 48–57.

## DEVIATIONS

Every intentional departure from the 1968 manual, and why:

1. **Line number 0 is accepted** (manual: 1–99999). Kemeny's own FTBALL
   begins with `0 REM * FTBALL *`.
2. **`RND` accepts and ignores a dummy argument** (`RND(X)`). The manual's
   `RND` takes no argument, but the `RND(X)` idiom appears in period programs
   (FTBALL); the argument is parsed and discarded, never evaluated.
   (Deviations 1–2 are tolerances for programs written under *earlier*
   editions of Dartmouth BASIC: FTBALL dates from 1965, before the Fourth
   Edition, when `RND`'s calling convention differed.)
3. **Machine capacity is not emulated.** The GE-635's limits and their
   errors are intentionally absent: the nine-digit constant limit
   (`ILLEGAL CONSTANT` fires here only above 1.70141E+38), `OUT OF ROOM`,
   `DIMENSION TOO LARGE`, `CUT PROGRAM OR DIMS`, `EXPRESSION TOO
   COMPLICATED`, `TOO MANY CONSTANTS`, the §2.9 space rule
   (C/4 + M + S < 8000), the 100-constant quota, the 60-character default
   string reservation, and the `USELESS LOOP` / `TIME UP` watchdogs.
   Programs and data are bounded only by the host machine, so a program
   that runs here might have exceeded capacity on real DTSS — anyone
   moving beyond validating program *output* toward validating historical
   *feasibility* (would this have fit and run in 1968?) must check §2.9's
   limits separately. (Note: `PRINT` label–expression juxtaposition,
   formerly listed here as a deviation, is in fact documented manual
   behavior — §1.7.3 type (c).)
4. **`END` rules are enforced as the manual specifies** — `END` must be
   present (`NO END INSTRUCTION`), unique, and the last line of the program
   (`END IS NOT LAST`, §2.8). DTSS was a one-pass *compiler*, for which
   `END` marked the end of the source; an interpreter could tolerate a
   mid-program `END`, but the historical system could not. Note that the
   bundled `LOVE` programs were renumbered accordingly (`END` moved after
   the `DATA` block, to line 999) relative to reconstruction drafts that
   placed `END` before the data.
5. **E-notation is printed with a space before the `E`** (`1.34218 E+8`),
   matching the manual's actual teletype sample outputs (§2.1, §2.2). The
   manual's prose example writes `3.24376E+10` without the space, and the
   build spec quotes that prose form; the observed output form was chosen.
6. **`MAT` and multiple-line `DEF` implementation choices** (both features
   are implemented per §2.6/§2.2; these are the points the manual leaves
   open). Inverting a singular matrix sets `DET = 0` and continues, as
   documented — the manual does not specify the result matrix's contents,
   so it is zeroed here. After a `MAT` instruction redimensions an array,
   scalar subscripts are checked against the *current* dimensions (identical
   to the `DIM` bounds until then; the manual's `ZER(25,5)`-under-`DIM
   M(20,7)` example requires an axis beyond its DIM bound to be
   addressable). `MAT A = A * B` is rejected with `ILLEGAL MAT MULTIPLE`
   per the §2.8 error list (§2.6's prose instead warns the in-place result
   would be "nonsense"). `TRN`/`INV` require matrix (not vector) operands.
7. **Arithmetic warnings behave as documented in §2.8** — the machine
   prints a message, supplies a value, and *continues running*:
   `DIVISION BY ZERO` and `ZERO TO A NEGATIVE POWER` supply +1.70141E+38;
   `OVERFLOW` supplies ±1.70141E+38; `UNDERFLOW` (magnitude below
   1.46937E-39) supplies 0; `EXP TOO LARGE` (argument ≥ 88.029) supplies
   +1.70141E+38; `LOG OF ZERO` supplies −1.70141E+38; `LOG OF NEGATIVE
   NUMBER` and `SQUARE ROOT OF A NEGATIVE NUMBER` use the absolute value;
   `ABSOLUTE VALUE RAISED TO POWER` computes `ABS(x)^y` (while `(-3)^3` is
   correctly −27). Constants larger than 1.70141E+38 are an
   `ILLEGAL CONSTANT` compile error, per §2.8. One deviation: in batch
   mode these warnings print to **stderr** so stdout remains exactly the
   teleprinter program output; in interactive mode they print inline on
   the "teletype" as on DTSS. Genuinely fatal runtime errors (`OUT OF
   DATA`, `SUBSCRIPT ERROR`, `RETURN BEFORE GOSUB`, `ON EVALUATED OUT OF
   RANGE`, `MISMATCHED STRING OPERATION`, …) stop the program as the
   manual specifies.
8. **Case-insensitive input.** The historical system expected uppercase;
   lowercase source and commands are accepted and folded to uppercase
   outside quoted strings (a permitted convenience in the build spec).
9. **Array subscript expressions are rounded to the nearest integer**
   (`B(I+K)` etc.). The manual does not specify truncation vs. rounding;
   rounding is robust against floating-point noise.
10. **Uninitialized variables read as 0 (numeric) or "" (string).**
11. **Batch error stream:** in batch mode error messages (and the §2.8
    warnings of item 7) go to stderr; fatal errors exit with status 1, so
    that stdout is exactly the teleprinter output. Messages use the
    manual's §2.8 vocabulary, in the form `MESSAGE IN <line>`. INPUT
    messages also follow §2.8: `INPUT DATA NOT IN CORRECT FORMAT -- RETYPE
    IT` (fatal in batch, where retyping is impossible), `NOT ENOUGH INPUT
    -- ADD MORE`, `TOO MUCH INPUT -- EXCESS IGNORED`.
12. **INPUT echo:** input typed at a terminal is echoed by the terminal
    itself, as on a teletype. When stdin is piped (batch), the response is
    not echoed, and a newline is emitted after each read so output stays
    well-formed. At end of stdin, `INPUT` raises `END OF INPUT`.
13. **Interactive niceties:** the workspace starts with the default name
    `NONAME` (DTSS demanded a sign-on name first); `SAVE` refuses to
    overwrite an existing file (use `REPLACE`, as on DTSS); `LIST` prints a
    DTSS-style heading (name, time, date) and `RUN` a header and a
    `TIME: … SECS.` footer (CPU time, as DTSS reported compute time).
    `LIST` on an empty workspace prints nothing; `RUN` on an empty
    workspace reports `NO END INSTRUCTION`. Unknown commands answer
    `WHAT?`.
14. **A letter may name a scalar and an array simultaneously** (per manual
    §1.7.8), and likewise `A$` may name a string scalar and a string vector;
    the manual is silent on the string case. A 1-D list and a 2-D table may
    not share a name (enforced, per the manual).
15. **The RND generator** is a fixed-seed Lehmer/MINSTD generator, chosen so
    the sequence is repeatable across runs *and* across Python versions. The
    historical generator's actual sequence is unknown; only its contract
    (repeatable, strictly between 0 and 1) is reproduced.
16. **Known gap — free-form spacing.** DTSS BASIC ignored spaces outside
    quoted strings, so `15LETG=A*E-B*D` was legal; this interpreter is
    whitespace-tolerant between tokens but requires keywords to be
    delimited, and rejects run-together source. Under evaluation (see
    `PLAN_comparative_validation.md`, item G1); no program in the bundled
    corpus is affected.
17. **Known gap — blank numbered lines.** A line number followed by
    nothing is accepted by real DTSS in stored programs (witnessed by the
    revived-DTSS TPK transcript in `timereshared/project-tpk`) but is
    currently rejected here in batch files (interactively, a bare number
    deletes the line, as on DTSS). Scheduled fix (item G2).

## Repository layout

```
dbasic.py            the interpreter (single module, Python 3)
dbasic2.py           Python 2.7 fork for legacy machines (kept in sync)
pyproject.toml       optional console-script packaging (no dependencies)
Makefile             make test / make love / make ftball
library/LOVE         Spahn reconstruction of LOVE (letters flow; test T1)
library/LOVE2        column-locked LOVE variant (exact image; test T2)
library/FTBALL       Kemeny's FTBALL (smoke test T4)
tests/               T1-T4 test suite and fixtures
tests/fixtures/LOVE.txt   reference teleprinter image (36 rows)
```
