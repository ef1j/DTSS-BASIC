# Build Spec: Dartmouth BASIC (Fourth Edition, 1968) Interpreter

## 1. Objective

Implement a faithful reimplementation of **Dartmouth BASIC, Fourth Edition (1968)** — the
dialect available on the Dartmouth Time-Sharing System (DTSS) in 1968–69 — as a
command-line program that runs on Linux. The purpose is to run period-accurate BASIC
programs from that era (in particular a reconstruction of Joshua Spahn's 1969 `LOVE`
program) and reproduce their teleprinter output exactly.

This is a **language reimplementation**, not a hardware or OS emulation. Ground every
language decision in the authoritative manual (see §4). Where the manual is silent or
ambiguous, choose the behavior that makes the acceptance tests (§8) pass, and record the
choice in a DEVIATIONS section of the README.

### Non-goals (do NOT implement)
- No GE-235 / DATANET-30 hardware emulation; no cycle timing; no multi-user time-sharing.
- No microcomputer/BASIC-80 features that postdate 1968: **no multiple statements per line**
  (no `:` separator), no `MID$`/`LEFT$`/`RIGHT$`/`SEG$` substring functions, no `PRINT USING`,
  no `LINE INPUT`, no HP-isms (`LIN`, bracket substrings).
- No GUI. Terminal only.

## 2. Design decision: one tool, two modes

Provide a single executable that supports both:

- **Batch mode** (primary, for reproducibility): `dbasic PROGRAM` loads a program file,
  runs it, writes output to stdout, exits with code 0 (or non-zero on BASIC error). This is
  what test scripts and the paper's reproducibility use.
- **Interactive mode** (authenticity): `dbasic` with no file argument starts a DTSS-style
  session with the classic command environment (§7): the user types numbered lines to build
  a program and issues commands like `RUN`, `LIST`, `NEW`, `OLD`, `SAVE`.

The interpreter core is shared; the interactive command environment is a thin REPL on top.

## 3. Runtime & packaging constraints

- Language: **Python 3.8+**, standard library only. **No third-party dependencies.**
- Deliverable runs directly on a stock Linux box: `python3 dbasic.py ...`, and also installs
  a `dbasic` console entry point via a minimal `pyproject.toml` (optional but preferred).
- Single module or a small package; must be readable and documented.
- Input is ASCII, treated case-insensitively for keywords; the system historically expected
  uppercase, so uppercase input must always work; accepting lowercase is a permitted convenience.

## 4. Authoritative sources (provided in the repo)

- **`196801_BASIC_4th_Edition.pdf`** — the *BASIC, Fourth Edition* manual (1 Jan 1968). This is
  the normative language reference. Implement statements, functions, `PRINT` formatting,
  `CHANGE`, arrays, and error behavior as documented here.
- Test corpus — bundle these into the build repo (source files currently live in the author's
  archive at the paths noted): the **Spahn reconstruction** program (`LOVE-spahn-recreated/love-spahn-v3`),
  the **reference output image** `LOVE.txt` (`LOVE-listings/LOVE.txt`), and **FTBALL**
  (`Dartmouth BASIC programs/ftball.txt`, Kemeny's program, smoke test).

Verified facts from the manual that MUST hold (do not "modernize" these):
- `IF <expr> <rel> <expr> THEN <line-number>` — the target of THEN is **only a line number**,
  never a statement (§1.7.5).
- One statement per line.
- Numeric variables are a single letter or a letter followed by a single digit (`A`, `X`, `A0`–`A9`).
- Strings: scalar string variables (`A$`) and **string vectors** (`V$(...)`, a list of strings)
  exist; the **`CHANGE`** statement converts a string to/from a numeric vector of character
  codes. There is **no substring function**.
- `ON <expr> GO TO <line>, <line>, ...` (computed branch) exists.
- Relational operators include `<`, `<=`, `=`, `>=`, `>`, `<>` (also written `#`).

## 5. Language semantics

### 5.1 Program model
- A program is a set of numbered source lines (1–99999). Lines are stored by number and
  executed in ascending numeric order regardless of entry order. Re-entering a line number
  replaces it; entering a bare line number deletes it (interactive mode).
- Exactly one statement per line. Reject `:`-separated multi-statements with an error.

### 5.2 Data & variables
- Numbers: floating point (double is fine). No separate integer type.
- Numeric variables: a single letter, or a letter followed by a single digit (`A`, `X`, `A0`–`Z9`).
- Arrays (manual §1.7.8): declared with `DIM`, **one or two dimensions**. If an array is used
  **without** a `DIM`, it is auto-allocated with **every subscript ranging 0 through 10**, and
  **subscripts are 0-based**. A subscript beyond the allocated bound (i.e. > 10 when no `DIM`
  was given) is a subscript error. Subscripts may be any numeric expression, e.g. `B(I+K)`,
  `Q(A(3,7), B-C)`.
- A single letter may name both a simple variable and an array in the same program, but **not
  both a 1-D list and a 2-D table**.
- String variables: `A$`. String vectors (lists of strings): `V$(n)`, declared with `DIM`.
  No string matrices (2-D string arrays).

### 5.3 Statements to implement (per the manual)
`LET` (assignment; the `LET` keyword is required), `READ`, `DATA`, `RESTORE`, `PRINT`,
`GO TO` (accept both `GO TO` and `GOTO`), `ON ... GO TO`, `IF ... THEN <line>`,
`FOR ... TO ... [STEP] / NEXT`, `DIM`, `DEF FN<x>(...)` (single-expression user functions),
`GOSUB` / `RETURN`, `INPUT`, `CHANGE`, `REM`, `STOP`, `END`. Implement `MAT` matrix statements
(`MAT READ`, `MAT PRINT`, `MAT` assignment/arithmetic) if documented in the manual; if time-
boxed, `MAT` may be deferred and listed as a known gap (it is not needed for the acceptance
tests).

### 5.3a Statement semantics (key points)
- `LET` — assignment; the keyword is **required** (`LET X = ...`).
- `READ` / `DATA` / `RESTORE` — values from all `DATA` statements form pools consumed in
  line-number order. **Numeric and string `DATA` are kept in two separate pools** (manual §2.7):
  reading a numeric variable draws from the numeric pool, a string variable from the string
  pool, independently. `RESTORE` resets the read pointer(s) to the start. Reading past the end
  is an error ("out of data").
- `FOR v = a TO b [STEP c]` / `NEXT v` — evaluate a, b, c once on entry; `STEP` defaults to 1;
  iterate while (c ≥ 0 and v ≤ b) or (c < 0 and v ≥ b); `NEXT` adds c and re-tests. Loops must
  be properly nested (manual §1.7.7).
- `GOSUB <line>` / `RETURN` — subroutine call/return using a return-address stack (nestable).
- `ON <expr> GO TO <l1>,<l2>,…` — evaluate expr, take its integer part n, and branch to the
  n-th line number (n = 1 selects the first). n out of range is an error.
- `DEF FN<letter>(<var>) = <expr>` — one-argument, single-expression user function.
- `INPUT <vars>` — prompt with `?`, read comma-separated values from the terminal (stdin).
- `STOP` halts execution (equivalent to reaching `END`); `END` terminates the program.
- `REM` — comment to end of line.

### 5.4 Expressions & functions
- Operators: `+ - * / ^` (`^` = exponent; the manual also prints it as `↑`), unary minus,
  parentheses.
- Precedence, high to low: `^` > unary `-` > `* /` > `+ -` > relational.
- Relational operators: `<`, `<=`, `=`, `>=`, `>`, `<>` (not-equal also written `#`). Used by `IF`.
- Built-in functions (manual §1.2, §2.2): `SIN COS TAN ATN EXP LOG ABS SQR INT RND SGN`.
  - `INT(x)` = greatest integer ≤ x: `INT(2.35)=2`, `INT(-2.35)=-3`, `INT(12)=12`.
  - `RND` takes **no argument** and returns a value strictly between 0 and 1. The sequence is
    **repeatable**: two RUNs of the same program produce the same sequence (the generator is
    reseeded to the same start each RUN). The idiom `INT(A*RND+B)` yields integers B..A+B-1.
  - `SGN(x)` = −1, 0, or +1.
  - `NUM` and `DET` are matrix functions — implement only alongside `MAT`.
- User-defined functions: `DEF FN<letter>(<var>) = <expression>` — a single-line function of
  one argument (e.g. `DEF FNT(X) = SQR(ABS(X)) + 5*X^3`).
- `TAB(n)` is used only inside `PRINT` (see §5.5).

### 5.5 PRINT — implement exactly as specified (manual §1.7.3, §2.1)
This is the most fidelity-critical part; the LOVE image depends on it.

Line model: the teleprinter line is **75 columns wide, divided into five zones of 15 columns**
each. Columns are numbered 0–74.

Item separators:
- **Comma (`,`)** — advance to the start of the **next 15-column zone**. If the fifth zone was
  just filled, advance to the first zone of the **next line**.
- **Semicolon (`;`)** — packed output, and behavior differs by item type:
  - A **quoted string (label)** followed by `;` is printed **with no space after it** — so
    consecutive strings concatenate directly. `PRINT "TIME-";"SHAR";"ING"` → `TIME-SHARING`.
    **`PRINT "L";` therefore emits exactly `L` with nothing added** (this is what lets the LOVE
    letters pack into the image).
  - A **number** followed by `;` is printed as: a leading `-` if negative or a **single leading
    space if non-negative**, then the numeric value (§5.5a), then **one trailing space**.
- Items must be separated by `,` or `;` (no two adjacent items without a separator).

Newline behavior:
- A `PRINT` ends with a newline **unless its last symbol is a `,` or `;`**, in which case the
  next `PRINT` continues on the **same physical line**.
- `PRINT` with no items emits a newline (blank line) / completes a partially filled line.

`TAB(n)` (as a PRINT item):
- `n` may be any expression; take its integer part and reduce **modulo 75** to 0–74. Move the
  print position **forward** to that column. If the position is **already at or past** column
  `n`, the `TAB` is **ignored** (never moves backward, never starts a new line).

Fidelity: preserve exact spaces and newlines; never trim trailing spaces from a printed line.

### 5.5a Numeric output format (manual §2.1)
1. An **integer** prints with no decimal point. An integer of **more than 8 digits** prints in
   E-notation as: one digit, `.`, five digits, `E`, signed exponent (e.g. 32437580259 →
   `3.24376E+10`).
2. A non-integer prints with at most **six significant digits**.
3. A magnitude **< 0.1** uses E-notation unless its significant part fits as a six-place decimal
   (e.g. `.03456`).
4. **Trailing zeros after the decimal point are dropped**, and a bare trailing decimal point is
   not printed.
(These rules only affect programs that print numbers; the LOVE tests print string literals and
spaces, so T1/T2 mainly exercise the `;` string-packing rule above.)

### 5.6 CHANGE
- `CHANGE A$ TO N` fills numeric array `N` with `N(0)=length` and `N(1..len)=character codes`.
- `CHANGE N TO A$` builds a string from codes, using `N(0)` as the length.
- Use the character-code table from the manual.

### 5.7 Errors
- BASIC's design goal was clear, friendly errors. On a runtime or syntax error, print a concise
  message naming the line number and stop execution. Provide a reasonable, documented set
  (undefined line, subscript out of range, out of DATA, type mismatch, etc.).

## 6. I/O
- Program output goes to stdout. `INPUT` reads from stdin (line-buffered). In batch mode a
  program that reaches `INPUT` with no stdin available should error cleanly rather than hang.
- Preserve exact spacing and newlines from `PRINT` (do not strip trailing spaces) — the visual
  fidelity of character-art output depends on it.

## 7. Interactive command environment (DTSS-style)
When started with no program argument, present a prompt and support these commands
(model them on the manual's "Using the Time-Sharing System" section):
- `NEW <name>` — start a new, empty named program (clears workspace).
- `OLD <name>` — load a named program from the library into the workspace.
- `SAVE` / `UNSAVE` — save the current workspace to the library / remove it.
- `LIST [n1[-n2]]` — list the program (optionally a line range).
- `RUN` — execute the current workspace program.
- `SCRATCH` — erase the workspace (keep the name).
- `RENAME <name>` — rename the workspace.
- `CATALOG` (`CAT`) — list saved programs.
- `BYE` (`GOODBYE`) — exit.
- Typing a line beginning with a number adds/replaces that line; a bare line number deletes it.
- Program names: uppercase, ≤ 6 characters, letters/digits (match the historical constraint).
- Library location: a directory (default `./library`, override with `--library DIR`), one plain
  text file per program, filename = program name (no extension), CR/LF or LF both accepted on read.

## 8. Acceptance tests (definition of done)

Provide an automated test runner (`make test` or `python3 -m pytest`, stdlib `unittest` is fine).

**T1 — LOVE reconstruction (the key test).** Running the provided `LOVE` program in batch mode
must emit 36 rows that reproduce the negative-space image in `LOVE.txt`. Because this
reconstruction lets the letters *flow* (they do not lock to columns), compare the
**space / non-space mask** of each row to `LOVE.txt` — every position that is a space in the
reference must be a space in the output and vice versa. All 36 rows must match. (This test
fails if `PRINT ";"` packing, `FOR/NEXT`, `READ/DATA`, `IF...THEN <line>`, or the letter-cycling
`ON`/`IF`-ladder logic is wrong, so it exercises the core.)

**T2 — Column-locked variant.** Provide a short test program that fills text by absolute column
(the Ahl method) and confirm it reproduces `LOVE.txt` **exactly, character for character**.
This pins numeric/`DATA` handling and exact `PRINT` packing.

**T3 — Unit tests** for: `PRINT` zones vs. packed `;`; trailing-`;` newline suppression;
`FOR/NEXT` with `STEP` and boundary conditions; one- and two-dimensional arrays and bounds;
`GOSUB/RETURN` nesting; `ON ... GO TO`; `CHANGE` round-trip (`A$`→codes→`A$`); string-vector
indexing; `IF ... THEN <line>` (and rejection of `THEN <statement>`); rejection of multi-
statement lines.

**T4 — Smoke test.** `ftball.txt` loads and runs to an interactive prompt without crashing
(it uses `INPUT`; feed canned input on stdin).

## 9. Deliverables & repo layout
```
dbasic.py                 # or a small package
pyproject.toml            # optional console-script entry point, no deps
README.md                 # usage, examples, and a DEVIATIONS section
tests/                    # T1–T4 plus fixtures
library/                  # sample programs incl. LOVE
```
README must document: how to run both modes; every intentional deviation from the manual and
why; and a short "provenance" note (see §10).

## 10. Provenance & honesty note (for the README and any scholarly use)
State plainly that this is a **modern reimplementation of the Dartmouth BASIC Fourth Edition
language, built from the 1968 manual** — not the original DTSS software (the 1968 compiler does
not survive) and not the DTSS operating system. It is a tool for demonstrating that period-
accurate programs run and produce the expected output under Fourth-Edition semantics; it is
evidence of feasibility, not of what any historical author actually wrote.
