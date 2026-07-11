# Conjuring Dartmouth BASIC, Fourth Edition: the prompt record

The complete sequence of user prompts that produced this interpreter, in
order, grouped by session date. Prompts are reproduced verbatim (typos
included); entries marked ⌘ are slash-command invocations rather than
free-text prompts, and entries marked ⏸ interrupted work in progress.
Shell commands typed directly into the session (`ls`, `git config --list`,
`gh auth login`, …) are omitted.

The work happened in two stages. First, in a chat conversation, a single
prompt produced the build specification (`SPEC_dartmouth_basic_v4.md`) —
the document that fixed the project's shape before any code existed:
Python on stock Linux, the normative 1968 manual, the LOVE/FTBALL
acceptance tests, and the resolution of the prompt's own open question
(interpreter-per-program vs. whole-system emulation) as the spec's §2
"one tool, two modes" design — a batch interpreter and a DTSS-style
command environment (`LIST`, `NEW`, `OLD`, …) sharing one core. All
implementation then moved to the Claude Code CLI on a remote machine,
with the spec checked into the repository; every prompt from #1 onward
was issued there.

## Prologue (chat session) — generating the specification

**0.**
> Let's write a tight spec for Fable. It should run on Linux from a
> normal terminal command line. One question is whether I just want to
> run an interpreter for each program or emulate the whole system with
> LIST, NEW, OLD, etc.

*(→ `SPEC_dartmouth_basic_v4.md`, which answered the question with both:
batch mode as the primary, reproducible interface and the interactive
DTSS command environment as a thin layer over the same interpreter core)*

## 2026-07-06 — bootstrap and first fidelity corrections

**1.** ⌘ `/init`
*(generate CLAUDE.md for the repository, which at that point contained
only `SPEC_dartmouth_basic_v4.md`)*

**2.** ⏸
> I uploaded the relevant PDF files, which are in Dartmouth BASIC
> Manuals. We can now build the spec. Ignore the dhq-journal directory.

**3.** ⌘ `/model fable`, then:
> now implement based on specs

*(→ dbasic.py, REPL, library fixtures, tests T1–T4, README, packaging;
all 57 initial tests passing)*

**4.** ⌘ `/fewer-permission-prompts`

**5.**
> What is the time calculation based on?

**6.**
> yes, use process_time instead

**7.**
> A minor tweak... in a print statement, the float exponent has a space,
> e.g. 2.91349 E-2 not 2.91349E-2.

**8.**
> The error is inconsistent with the documentation: list
> ```
> NONAME   20:44      07/06/26
>
> 10 PRINT LOG(0)
> 20 END
> READY
> run
>
> NONAME   20:44      07/06/26
>
> LOG OF NON-POSITIVE ARGUMENT IN 10
> READY
> ```

*(→ discovery and implementation of the manual's §2.8 warn-and-continue
arithmetic semantics)*

**9.**
> Interesting that the max column is 75. On my ASR-33 it is 72.

**10.**
> No, it's important to run this as originally implemented. I'm not sure
> what the behavior should be if there is no program loaded. This is what
> another system implements:
> ```
> DARTMOUTH TIME-SHARING SYSTEM
> BASIC AND ALGOL, AS DESCRIBED BY T. E. KURTZ
>
> READY
> list
> READY
> new
> NEW PROGRAM NAME--
> READY
> list
> READY
> ```

**11.**
> Interestingly, my LOVE program has an END mid-way in the program.

**12.**
> Let's enforce the manual rules. An END statement mid-way would have
> worked with an interpreter, but not the one-pass compiler that DTSS
> implemented! I will have to fix the programs...

*(→ strict `END IS NOT LAST`; bundled LOVE programs renumbered to 999)*

## 2026-07-07 — portability, publication, and completing the language

**13.**
> Is Python the right language for this project? What are other
> possibilities? Other languages that were written for building
> interpreters?

**14.**
> Can I make a version back compatible with Python 2.7? A machine I'm
> using is quite old. It doesn't have python3.

**15.** ⏸
> Hold on... I want to fork a 2.7 version and keep a clean python3
> version, too.

*(→ dbasic2.py fork, later regenerated mechanically by
`tools/make_fork.py`)*

**16.**
> Let's git this up and prepare to deploy to github and / or gitea. Only
> the Dartmouth BASIC files need to be tracked. The other background
> files in the directory can be ignored.

**17.**
> MIT license is the right way to go.

**18.**
> I created DTSS-BASIC on the site.

*(→ pushed to https://github.com/ef1j/DTSS-BASIC)*

**19.**
> Let's implement the missing MAT and DEF commands next.

*(→ all thirteen §2.6 MAT instructions with the capacity/current-dims
redimensioning model; multiple-line DEF/FNEND per §2.2)*

**20.**
> Are there any features in version 4 we haven't implemented?

**21.**
> Those changes are good, and noting the emulation limit explictly in the
> README would be helpful if anyone wanted to move beyond simply
> validating output of the code. BTW, FTBALL was written for an earlier
> version (3?) so perhaps that explains some of the differences. And I
> think Dartmouth took delivery of a larger GE machine (680?) by the time
> Version 4 was implemented. (It was the GE-635 according to Wikipedia...
> https://en.wikipedia.org/wiki/Dartmouth_BASIC)

*(→ apostrophe remarks, `IF…GO TO`, `ON…THEN`; juxtaposition reclassified
as documented §1.7.3 behavior; GE-635 correction; capacity-limits
DEVIATIONS entry)*

## 2026-07-08 — comparative evaluation and free-form source

**22.**
> We are pausing implementation on our Dartmouth BASIC Version 4
> interpreter to conduct a rigorous architectural evaluation. Before we
> touch the codebase, I want to establish a formal planning and
> gap-analysis document comparing our current interpreter's behavior
> against existing open-source preservation projects.
>
> Please review the architectural choices, assumptions, and test profiles
> of the following GitHub repositories to help design our validation
> strategy:
>
> ### 1. Comparative Reference Points
> *   **`cpp-tutor/dbasic`** (https://github.com/cpp-tutor/dbasic)
>     *   *Context:* A modern D/Yacc compiler that targets LLVM IR. It
>         uses an explicit compiler switch (`./dbasic [1-6]`) to toggle
>         keyword sets based on the historical language edition, with a
>         major current emphasis on Fourth Edition (1968) alignment.
> *   **`WA6YDQ/dbasic`** (https://github.com/WA6YDQ/dbasic)
>     *   *Context:* An interactive, C-based interpreter following 1968
>         Dartmouth rules, but with declared structural "exceptions"
>         (e.g., it explicitly breaks historical compliance by banning
>         internal whitespace, requiring `GOTO` instead of `GO TO`, and
>         substituting `**` for the original `^` power token).
>
> ### 2. Algorithmic & Output Benchmarks
> *   **`maurymarkowitz/Illustrating-BASIC`**
>     (https://github.com/maurymarkowitz/Illustrating-BASIC)
>     *   *Context:* A curated codebase derived from Donald Alcock's 1977
>         text, providing clean, structural examples specifically
>         tailored to historical BASIC syntax parameters (such as `MAT`
>         matrix functions and matrix loops).
> *   **`timereshared/project-tpk`**
>     (https://github.com/timereshared/project-tpk)
>     *   *Context:* Archives implementations of Donald Knuth's TPK
>         baseline mathematical algorithm executed on emulated vintage
>         mainframes—including real Dartmouth DTSS system printouts—to
>         evaluate compiler/interpreter I/O, array behavior, and
>         mathematical evaluation correctness.
>
> ---
>
> ### Your Task: Generate a "Dartmouth BASIC v4 Comparative Planning
> Document"
>
> Please analyze these references and output a comprehensive planning
> report divided into the following sections:
>
> 1.  **Lexer & Tokenization Discrepancies:** Contrast how `cpp-tutor`
>     handles classic Dartmouth free-form whitespace formatting (e.g.,
>     `15LETG=A*E-B*D`) versus `WA6YDQ`'s modernized, space-delimited
>     string restriction. Define how our current architecture stacks up
>     and what design approach we must document to remain authentic.
> 2.  **Syntax & Semantic Variances:** Create a comparative matrix
>     analyzing how these projects handle historical deviations like
>     multi-character variables (e.g., `A0`, `C3` vs. standard `A-Z`),
>     exponentiation characters (`^` vs. `**`), and non-equality
>     operators (`<>` vs. `!=`).
> 3.  **Algorithmic Verification Framework:** Propose a strategy for
>     using `timereshared/project-tpk`'s DTSS terminal outputs and
>     `maurymarkowitz`'s math matrices as a non-executed "visual diff"
>     benchmark to verify our interpreter's functional evaluation path.
> 4.  **The "Compliance Boundary" Policy:** Outline a draft specification
>     policy for our project detailing when our interpreter should
>     strictly replicate original 1968 GE-225/DTSS operational behaviors
>     and when it is acceptable to adopt modern concessions (like
>     `WA6YDQ` did).
>
> Do not write or alter any code. Focus entirely on structural analysis,
> edge-case definitions, and comparative design strategy.

*(→ `PLAN_comparative_validation.md`; discovery of the free-form-lexing
gap G1 and the bare-line-number question G2)*

**23.**
> Let's update the README to reflect the differences between existing
> efforts and our own. I want to stay as true to V4 as possible here. It
> looks like there's good separation between the exsiting work and ours.

**24.**
> llustrating basic cites https://github.com/maurymarkowitz/RetroBASIC

**25.**
> Is it feasible to implement the ignored spaces outside quoted strings?

**26.**
> Let's do G1.

*(→ free-form carving lexer; crunched-LOVE2 byte-identity test; COT
discovered in §1.2 and added)*

**27.**
> I don't believe G2. How are blank lines input? As you point out, it
> erases a current line.

*(→ corrected analysis: DTSS never stored blank numbered lines — bare
line numbers are deletion commands at entry; batch loading reframed as
terminal-entry replay)*

## 2026-07-11 — this document

**28.**
> Can you dump all of the prompts I used to conjure Version 4 BASIC to an
> md file?
