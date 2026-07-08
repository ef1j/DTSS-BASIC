# Dartmouth BASIC v4 — Comparative Planning & Gap-Analysis Document

*Status: draft for review — no code changes accompany this document.*
*Prepared against dbasic commit `3bf0abb`; all reference-repository claims
below were verified against the repositories' actual sources on 2026-07-08,
not taken from their READMEs alone.*

## 0. Reference points: what each project actually is

Verified characteristics, with corrections to received descriptions noted.

**`cpp-tutor/dbasic`** — a compiler in the **D language** (hand-written
lexer `LexerImpl.d`, generated parser in `autogen/Parser.d`) targeting
**textual LLVM IR**, linked against a small C runtime. Editions are selected
by a numeric CLI argument; **editions 1–4 are currently implemented** (the
First-through-Sixth range is roadmap, not current). Its keyword table is
edition-tagged (e.g. `MAT` family = Second Edition, `RESTORE`/`INPUT` =
Third, `CHANGE`/`ON`/`TAB`/`RANDOMIZE` = Fourth) and using a keyword above
the selected edition is a compile error — a genuinely interesting
"historical linting" capability we lack. Its test corpus is
`examples/example-p<NN>.bas`: the manuals' own page-numbered examples.
Release notes claim a full Fourth Edition implementation with one failing
example.

**`WA6YDQ/dbasic`** — an interactive **C** interpreter, self-described as
following 1968 rules **with declared exceptions**, and the exceptions are
substantial: keywords must be space-delimited (run-together source is
rejected), `GOTO` only (no `GO TO`), `**` for exponentiation instead of
`^`, `!=` accepted alongside `<>`, variables restricted to bare `A`–`Z`
(no `A0`-style names), **no MAT support**, plus *additions* that postdate
1968 entirely: `LEFT$`/`RIGHT$`/`MID$`/`CHR$`, string concatenation with
`+`, and C-style logical operators (`&`, `|`, with `^` reassigned to XOR).
It is best read as a usability-oriented retro dialect, not a preservation
artifact — which makes it our most useful *anti-model* (§4).

**`maurymarkowitz/Illustrating-BASIC`** — transcriptions of the programs
in Donald Alcock's *Illustrating BASIC* (1977), a book written against
"Dartmouth BASIC Version 4" as Alcock knew it. Includes substantial MAT
programs (`matmul.bas`, `cramers.bas`) and clean numeric/algorithmic
programs (`cosine.bas`, `areacalc.bas`, `roman`, `bestwayhome`). Caveats:
(a) the corpus also exercises **`PRINT USING`**, which is *not* in the
1 January 1968 manual (it arrives with later/commercial BASICs) and is an
explicit non-goal of our spec — the repo's "V4" label is looser than ours;
(b) sources were hand-transcribed from hand-lettered listings, so each
program needs vetting against the 1968 manual before being admitted as a
fixture.

**`maurymarkowitz/RetroBASIC`** (cited by Illustrating-BASIC as its
runtime; same author) — a C interpreter built with lex/yacc whose goal is
the *union* of era dialects (MS, Dartmouth V4, HP Timeshared, Tiny, DEC)
behind per-dialect switches: `--array-base` (default 1 — note Dartmouth is
0-based), `--random` seeding, optional HP-style string slicing, and a
static-analysis mode that prints feature-usage statistics across vintage
programs. Variable names are capped at two characters to support MS-style
"crunched" (space-free) source. For our purposes: (a) it is the reference
runtime the Alcock corpus was normalized against, so Tier-C disagreements
should be triangulated ours-vs-RetroBASIC-vs-manual; (b) its statistics
mode is a model worth borrowing if the paper ever needs corpus-wide
feature-frequency claims; (c) its union-dialect posture is the structured
version of what WA6YDQ does ad hoc — useful, but the complement of a
single-edition fidelity tool.

**`timereshared/project-tpk`** — implementations of the Trabb Pardo–Knuth
algorithm (read 11 numbers; for each, in reverse, compute √|x| + 5x³;
print value or `TOO LARGE` if > 400) across vintage systems, **with actual
execution transcripts from a revived DTSS** (`listings/Dartmouth
DTSS/basic_execution.txt` carries a 2025 session header — this is output
from real restored DTSS software, not a re-implementation). This is the
only reference that gives us *ground-truth DTSS output* we did not
produce ourselves.

---

## 1. Lexer & tokenization discrepancies

### The ground truth

Historical DTSS BASIC was **free-form**: spaces were insignificant outside
quoted strings, so `15LETG=A*E-B*D` and `FORI=1TO10` were legal. This is
the single largest *lexical* authenticity question for any reimplementation.

### How cpp-tutor achieves it (verified in `LexerImpl.d`)

Its lexer skips runs of spaces as a non-token, then — the key move —
matches any run of **two or more letters** as a candidate KEYWORD and
resolves it by **prefix-carving**: the maximal alphabetic run `LETG` is
tested with `startsWith` against the keyword table, matches `LET`, and
only `len("LET")` characters are consumed, leaving `G` to be re-lexed as an
identifier (`[A-Z][0-9]?`). A run matching no keyword prefix falls through
to single-letter identifier matching. So `15LETG=A*E-B*D` and `1TO10`
tokenize correctly with no pre-pass. Note its relational set is
`<> <= < >= >` — it lacks the manual's `#` synonym, which we support.

### How WA6YDQ handles it

It doesn't, by design: keywords must be whitespace-delimited, and the
README declares this as an intentional break with 1968 practice.

### Where our interpreter stands

We are **between the two, closer to WA6YDQ on this axis**: our tokenizer
is whitespace-*tolerant* (any spacing between tokens, `IF X >=  100`,
`SIN (X)`) but whitespace-*requiring* at keyword boundaries — the id regex
`[A-Z][A-Z0-9]*\$?` consumes maximal runs, so `LETG` lexes as one unknown
identifier and fails with `ILLEGAL INSTRUCTION`, and `TO10` fails inside
FOR. Nothing in our acceptance corpus exercises free-form input (the LOVE
reconstruction, FTBALL, and the manual's printed examples are all
conventionally spaced), which is why this gap has been invisible.

### Design position to document (and later decide)

- **Option A (authentic):** strip spaces outside quotes at load time, then
  lex with keyword-prefix carving (cpp-tutor's technique fits our
  regex-tokenizer structure; `REM`/`DATA` raw-text handling and quoted
  strings are unaffected because stripping respects quotes).
- **Option B (status quo, documented):** keep delimiter-required lexing and
  add a DEVIATIONS entry stating that free-form run-together source —
  legal on DTSS — is rejected here.
- Recommendation: **A**, gated by T1/T2 byte-identity as regression proof,
  scheduled as its own change; until then, B's DEVIATIONS entry should be
  added so the gap is on the record.

### Discovered gap: blank numbered lines

The TPK source that *runs on revived DTSS* contains lines `110` and `130`
that are **line numbers followed by nothing**. Real DTSS accepts them;
our loader stores an empty statement and fails at compile with `ILLEGAL
INSTRUCTION`. Proposed behavior: accept and treat as no-ops in files
(batch), while retaining the interactive rule that a bare number *typed at
the console* deletes that line. Until fixed, TPK cannot run unmodified —
this is the first concrete blocker for §3 Tier A.

---

## 2. Syntax & semantic comparative matrix

| Feature | 1968 manual (normative) | **ours** | cpp-tutor (ed. 4) | WA6YDQ |
|---|---|---|---|---|
| Variable names | letter or letter+digit (`A`, `A0`–`Z9`) | ✅ same | ✅ `[A-Z][0-9]?` | ❌ `a`–`z` only |
| String variables | `A$` scalars, `A$()` vectors, no substrings | ✅ same, `CHANGE` for codes | partial (`$` token; strings present) | ❌ modern: `MID$` family, `+` concat |
| Exponentiation | `^` (printed `↑`) | ✅ `^` | ✅ `^` | ❌ `**`; `^` reassigned to XOR |
| Not-equal | `<>` *and* `#` | ✅ both | ⚠️ `<>` only | ❌ `<>` and `!=` |
| `GO TO` spelling | `GO TO` and `GOTO` | ✅ both | ✅ `GO`+`TO` tokens | ❌ `GOTO` only |
| `IF … GO TO` / `ON … THEN` | both legal (§1.7.6) | ✅ both | unverified | ❌ n/a |
| Free-form spacing | spaces insignificant | ❌ delimiters required (§1 above) | ✅ prefix-carving | ❌ declared exception |
| MAT statements | thirteen (§2.6) + string forms (§2.7) | ✅ all, with capacity/`cur` redim model | ✅ (`Mat.d`; edition-gated) | ❌ none |
| `NUM` / `DET` | after MAT INPUT / INV | ✅ | ✅ (edition-tagged) | ❌ |
| Multi-line `DEF`/`FNEND` | §2.2 | ✅ | unverified | ❌ |
| `RND` | no argument; repeatable per RUN; `RANDOMIZE` | ✅ + tolerated dummy arg | ✅ keyword (ed. 4 gated) | ⚠️ modern rand |
| Arithmetic anomalies | §2.8 warn-and-continue, ±1.70141E+38 | ✅ | ❌ (LLVM float semantics) | ❌ |
| Error vocabulary | §2.8 messages | ✅ | partial | ❌ own messages |
| `END` last / unique | enforced (one-pass compiler) | ✅ | unverified | ❌ n/a |
| Line 0 | not permitted (1–99999) | ⚠️ tolerated (FTBALL, pre-V4) | unverified | unverified |
| Blank numbered lines | accepted by revived DTSS | ❌ rejected (gap, §1) | ❌ likely rejected | ❌ |
| Multi-statement lines / `:` | absent | ✅ rejected | ✅ absent | ✅ absent |
| Edition gating | n/a (manual is one edition) | ❌ V4 only | ✅ CLI switch 1–4 | ❌ |

Take-aways: we and cpp-tutor are the two projects in genuine V4 territory,
with complementary strengths — they gate features by edition and lex
free-form; we model the teleprinter, §2.8 warning semantics, the DATA-pool
split, CHANGE, multi-line DEF, and MAT redimensioning/relocation, and we
pin output byte-exactly. WA6YDQ is disjoint from our goals on nearly every
row that matters.

---

## 3. Algorithmic verification framework

Three tiers, ordered by evidentiary strength of the reference output.

### Tier A — revived-DTSS transcripts (project-tpk): strongest evidence

`basic_execution.txt` is real DTSS output. Protocol:

1. **Chrome mask.** Session framing differs across DTSS eras and must be
   excluded from comparison: the 2025 revival prints `OLD TPK` / `RUN`, a
   header with `JUN 23, 2025`-style dates, and `TIME 0. SECS`, whereas the
   1968 manual's sessions show `READY`, `10/20/67`-style dates, and
   `TIME:  .06 SECS.` (ours follows the manual). Comparison therefore
   covers **program output body only**: from the first program-generated
   line (`RESULTS ARE`) to the last (`TOO LARGE`), byte-exact, trailing
   spaces significant.
2. **Expected body agreement.** The transcript's numerics — ` 399.886`,
   `-4`, ` 6`, ` 322`, ` 41.4142`, ` 136.732` — follow exactly the §2.1
   sign-space/6-significant-digit rules our formatter implements, so we
   should match byte-for-byte on every line. Any divergence is a finding
   about `fmt_mag` or expression evaluation.
3. **Precision policy.** GE-635 arithmetic was 36-bit; ours is IEEE
   double. Divergence confined to the 6th significant digit is recorded,
   not failed (precedent: HILMAT's determinant, manual `1.65342 E-7` vs
   our `1.65344 E-7`, where ours is closer to the true value). Divergence
   earlier than the 6th digit fails.
4. **Blocker:** the TPK source's blank numbered lines (§1) must be
   resolved before this program runs unmodified.

### Tier B — manual-page examples (adopt cpp-tutor's corpus structure)

cpp-tutor's `example-p<NN>.bas` naming — the manuals' own examples, keyed
by page — is the right shape for a fixtures corpus, and we have already
hand-verified several against the 1968 scans (POWERS p. 42, RNDNOS p. 43,
MATRIX p. 60 byte-exact, HILMAT p. 61, CHANGE p. 67). Formalize: a
`tests/fixtures/manual/` corpus of page-cited programs with expected
outputs transcribed from the scans (transcription rules: slashed `Ø` → `O`,
preserve column positions and trailing spaces, note any scan ambiguity in
a sidecar comment). Each becomes a T3-style exact-output test.

### Tier C — Illustrating-BASIC (Alcock): breadth, with vetting

Use as a *breadth* corpus for MAT and numeric behavior (`matmul.bas`,
`cramers.bas`, `cosine.bas`, …), admitted per-program after vetting
against the 1968 manual: programs using `PRINT USING` or other post-1968
constructs are excluded as out of scope (documented non-goal), and
remaining programs get expected outputs by hand-verified mathematics
(Cramer's rule solutions, matrix products), since the book's printed
outputs are typeset, not teletype captures.

### Cross-implementation triangulation (non-executed → executed)

For any program in Tiers B/C, a disagreement between our interpreter and
cpp-tutor edition-4 output is a *flag*, not a verdict — both projects have
independent bug surfaces — adjudicated by the manual. Value: their LLVM
float pipeline and our Python doubles agreeing to 6 significant digits is
strong evidence the evaluation path (precedence, function semantics, FOR
boundaries) is right in both. Candidate starter set: TPK, MATRIX (p. 60),
HILMAT, matmul, cramers.

---

## 4. The Compliance Boundary policy (draft specification)

*(Terminology note: by the Fourth Edition era the DTSS hardware was a
GE-635 with a DATANET-30 front end; the GE-225/235 was the original 1964
machine. The policy below uses "DTSS operational behavior" to mean the
system as documented in the 1 Jan 1968 manual.)*

### Normative hierarchy (conflict-resolution order)

1. The **1968 manual's prose** is normative for language semantics.
2. The manual's **teletype sample outputs** override its prose where they
   conflict (established precedent: `1.34218 E+8` with a space, chosen
   over the prose's `3.24376E+10`).
3. **Period programs and genuine DTSS transcripts** (revived-DTSS runs
   included) may establish behaviors the manual omits (established
   precedents: blank-line handling; `END IS NOT LAST` enforcement argued
   from the one-pass compiler). They may *not* override the manual where
   the manual speaks.
4. The build spec's acceptance tests decide residual cases; every choice
   made under rules 2–4 is recorded in README DEVIATIONS.

### Compliance classes

- **STRICT (replicate, no exceptions):** statement semantics; the
  75-column/five-zone PRINT model and §2.1 numeric formatting; `;`
  packing; TAB mod 75; §2.8 error vocabulary and warn-vs-stop split;
  ±1.70141E+38 / underflow-to-0 supplied values; two independent DATA
  pools; MAT dimension/capacity/relocation conventions; `END` present,
  unique, last; one statement per line; repeatable `RND`; ASCII `CHANGE`
  codes. Anything a 1968 program's *output* can witness is in this class.
- **TOLERATED (earlier-edition idioms, enumerated & evidence-cited):**
  line number 0 and `RND(dummy)` — admitted because a bundled period
  program (FTBALL, 1965) requires them; each tolerance names its witness
  program in DEVIATIONS. New tolerances require a period witness, not
  convenience.
- **MODERN CONCESSIONS (allowed only where invisible to program
  output):** lowercase input folded to uppercase outside strings;
  batch-mode stderr/exit-code conventions; the library as a host
  directory; readline editing; no echo of piped input. Test: a 1968
  program's stdout must be byte-identical with the concession present or
  absent.
- **NOT EMULATED (declared, out of scope):** machine capacity and timing —
  the nine-digit constant limit, `OUT OF ROOM`, the §2.9 space rule,
  constant quotas, string-space reservation, `USELESS LOOP`/`TIME UP`
  watchdogs, 36-bit arithmetic, teletype speed, and the 72-column
  physical carriage of the Model 33/35 vs the software's 75-column line.
  Consequence (already in DEVIATIONS): we validate *output*, not
  historical *feasibility*; feasibility claims need a separate §2.9
  check.
- **REJECTED MODERNISMS (never, they change the language):** the WA6YDQ
  class of changes — `**` for `^`, `!=`, keyword-delimiter requirements
  *as a language rule*, `MID$`-family functions, string `+`, logical
  operators, multi-statement lines, `PRINT USING`. The discriminator vs
  "concessions": these alter what programs are valid or what they output.
  WA6YDQ's `**` swap is the canonical example — it silently breaks every
  historical program containing `^`.

### Decision rule (one sentence)

> A departure from 1968 behavior is acceptable **iff** it cannot change
> any 1968-valid program's teleprinter output **and** cannot make a
> 1968-invalid program run silently; otherwise it is either a documented,
> witness-backed tolerance or it is out of bounds.

---

## 5. Gap register & proposed actions (no code yet — for sign-off)

| # | Gap / action | Source of evidence | Class | Priority |
|---|---|---|---|---|
| G1 | ~~Free-form lexing~~ **DONE** — Option A implemented (space-strip + keyword carving); crunched-LOVE2 byte-identity test added; DEVIATIONS 16 documents the three edges. COT added alongside (found in §1.2 during the same manual pass). | DTSS practice; manual §1.5 line-number rule; cpp-tutor technique | STRICT | ✅ complete |
| G2 | Blank numbered lines rejected in batch files | TPK source runs on revived DTSS | TOLERATED→STRICT | P1 — small change |
| G3 | Adopt TPK as Tier-A fixture with chrome-mask diff | project-tpk transcript | validation | P2 (after G2) |
| G4 | Formalize `tests/fixtures/manual/` page-cited corpus | cpp-tutor corpus shape; our hand-verified examples | validation | P2 |
| G5 | Vet & admit Alcock MAT/numeric programs (excl. `PRINT USING`) | Illustrating-BASIC | validation | P3 |
| G6 | Document session-chrome era variance (READY/dates/TIME formats) | 1968 manual vs 2025 revival transcript | documentation | P3 |
| G7 | Edition-gating of keywords (cpp-tutor-style `--edition` lint) | cpp-tutor | out of scope for v4 tool; note as possible future work | P4 |
| G8 | DEVIATIONS entry for G1 if Option B chosen | — | documentation | with G1 |

*Prepared for review; on approval, G1/G2 become the first implementation
work items after the pause.*
