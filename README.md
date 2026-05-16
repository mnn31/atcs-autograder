# ATCS Compilers Autograder

A reusable, lab-pluggable autograder for the ATCS Compilers & Interpreters
sequence. Seven labs are wired up today, all sharing the same orchestrator,
PDF blanksheet, and per-rubric airtightness rules.

Each student submission is a `.zip`. The tool extracts it, runs the
lab's structural and behavioural checks, and emits a colour-coded PDF
report that mirrors the official peer-review checkoff sheet row for
row. The blanksheet layout is deliberately identical across students
so a teacher can scan for red cells without re-orienting per
submission.

---

## Labs covered

| Lab            | Wrapper                        | Submission shape           | Total |
|----------------|--------------------------------|----------------------------|-------|
| Scanner        | `autograders/ag-scanner/`      | `scanner/`                 | 100   |
| Parser         | `autograders/ag-parser/`       | `scanner/` + `parser/`     | 100   |
| AST            | `autograders/ag-ast/`          | full `Compiler/` tree      | 100   |
| Procedures     | `autograders/ag-procedures/`   | full `Compiler/` tree      | 100   |
| MIPS           | `autograders/ag-mips/`         | folder of `.asm` files     | 52    |
| Subroutines    | `autograders/ag-subroutines/`  | folder of `.asm` files     | 85    |
| CodeGen        | `autograders/ag-codegen/`      | full `Compiler/` tree      | 100   |

Totals match the official peer-review sheet for each lab. Adding
another lab is a matter of dropping a new `config.py` + tests next to
the existing ones.

### What each lab grades

- **Scanner** — does the student's `scanner.Scanner` produce the
  right token stream? Tokenises a small bank of input files via a
  synthesised `_AGScannerTester`; checks documentation, the
  multi-char tokens (`<=`, `>=`, `<>`, `:=`), period-as-EOF + the
  `hasNext()` contract, single-line comment handling, and the four
  `$/^` error-recovery scenarios from the rubric.
- **Parser** — does the student's parser EXECUTE Pascal as it
  parses? The synthesised `_AGParserTester` calls
  `parser.parseStatement()` in a loop while `scanner.hasNext()`
  is true and matches WRITELN output against `parserTest0..4`.
- **AST** — does the rewritten parser BUILD AST nodes that exec
  correctly? `_AGASTTester` parses each statement and calls
  `stmt.exec(env)` on a shared `Environment`. Tests:
  `parserTest6` (IF + WHILE) and `parserTest4.5ForLoopReadln`
  (READLN + FOR + downward WHILE).
- **Procedures** — does the student's interpreter correctly run
  a hidden test suite of PASCAL programs (procedures with args,
  scope, return values, recursion, mutual recursion)?
  `_AGTester.java` drives the resolved Parser / Program /
  Environment so a hardcoded test filename in the student's own
  `ParserTester` can't make every hidden test silently re-run the
  same file.
- **MIPS** — for each rubric exercise (`simple`, `add`/`mult`,
  `evenodd`, `loops`, `array`, an open-ended program, ...) did
  the student deliver a documented `.asm` whose stdout under MARS
  4.5 matches the expected substrings?
- **Subroutines** — same shape as MIPS, plus structural checks
  the rubric calls out: `max3` must `jal max2`, `fact` must be
  recursive with stack discipline, and the linked-list row is
  REVIEW-tagged with the heap-vs-stack approach the autograder
  detected.
- **CodeGen** — does the student's Pascal -> MIPS emitter
  produce assembly that, when fed back to MARS, prints the right
  thing for the lab-required programs (`parserTest9.txt` and
  `max.txt`)? `_AGCodeGenTester.java` drives the parser + emitter
  to write a `.asm`; the runner then executes that asm under MARS
  and matches stdout.

---

## Install (5 minutes)

### 1. Prerequisites

- **Python 3.8+**
- **A JDK** with both `java` and `javac` on `PATH`. The macOS
  default `java` is fine, but it does not include `javac` on its
  own — you have to install a full JDK.

macOS (Homebrew):

```bash
brew install python openjdk@17
# Homebrew prints a line telling you to add openjdk to PATH; run it now.
# On Apple Silicon it looks like:
echo 'export PATH="/opt/homebrew/opt/openjdk@17/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

Ubuntu / Debian:

```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv openjdk-17-jdk
```

Windows: install Python from [python.org](https://www.python.org/downloads/)
and a JDK from [Adoptium](https://adoptium.net/). Use Git Bash or WSL
for the commands below.

Verify both are on your `PATH`:

```bash
python3 --version     # Python 3.8 or newer
java -version
javac -version        # must NOT say "command not found"
```

If `javac` is missing and `java` works, you installed the JRE only —
go back and install the JDK (`openjdk-17-jdk` on Ubuntu, `openjdk@17`
on macOS).

### 2. Clone and install Python deps

```bash
git clone https://github.com/mnn31/atcs-autograder.git
cd atcs-autograder/autograder-work

python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` is two lines: `reportlab` (PDF output) and
`javalang` (Java AST parsing). The checkstyle jar, MARS 4.5
simulator jar, and the checkstyle config are all bundled in
`vendor/`.

All commands from here run from inside `autograder-work/`.

### 3. Smoke test

Drop one student zip somewhere and run the matching lab:

```bash
./autograders/ag-procedures/ag-procedures path/to/Compiler.zip \
    -o ag-tests/procedures/outputs/
```

You should see one line per grading stage and then:

```
[ag-procedures]   -> ag-tests/procedures/outputs/firstname-lastname-procedures-report.pdf  (XX.X%)
```

Open that PDF. If the banner, Quick Review box, and rubric table are
all rendered, the install is working.

---

## Per-lab input/output layout

By convention each lab gets its own `ag-tests/<lab>/inputs/` and
`ag-tests/<lab>/outputs/` pair. The `ag-tests/` root is gitignored
so committing zips here will not accidentally push student work into
the repo.

```
ag-tests/
├── scanner/
│   ├── inputs/        # student Scanner.zip files
│   └── outputs/       # generated PDF reports + overall.pdf
├── parser/
│   ├── inputs/
│   └── outputs/
├── ast/
│   ├── inputs/
│   └── outputs/
├── procedures/
│   ├── inputs/
│   └── outputs/
├── mips/
│   ├── inputs/
│   └── outputs/
├── subroutines/
│   ├── inputs/
│   └── outputs/
└── codegen/
    ├── inputs/
    └── outputs/
```

Each wrapper accepts either a single zip or a directory of zips; in
the directory case a batch summary `overall.pdf` is produced
alongside the per-student reports.

---

## Grading submissions

Single student (one zip):

```bash
./autograders/<wrapper>/<wrapper> path/to/Student.zip \
    -o ag-tests/<lab>/outputs/
```

Whole folder of zips:

```bash
./autograders/<wrapper>/<wrapper> ag-tests/<lab>/inputs/ \
    -o ag-tests/<lab>/outputs/
```

Concrete examples (one per lab):

```bash
./autograders/ag-scanner/ag-scanner      ag-tests/scanner/inputs/      -o ag-tests/scanner/outputs/
./autograders/ag-parser/ag-parser        ag-tests/parser/inputs/       -o ag-tests/parser/outputs/
./autograders/ag-ast/ag-ast              ag-tests/ast/inputs/          -o ag-tests/ast/outputs/
./autograders/ag-procedures/ag-procedures ag-tests/procedures/inputs/  -o ag-tests/procedures/outputs/
./autograders/ag-mips/ag-mips            ag-tests/mips/inputs/         -o ag-tests/mips/outputs/
./autograders/ag-subroutines/ag-subroutines ag-tests/subroutines/inputs/ -o ag-tests/subroutines/outputs/
./autograders/ag-codegen/ag-codegen      ag-tests/codegen/inputs/      -o ag-tests/codegen/outputs/
```

Each student gets a file named `<first>-<last>-<lab>-report.pdf` in
the output directory. The student name is taken from the `@author`
tag in the class-level javadoc (for Java labs) or the `# @author`
line in the .asm header (for asm labs), so reports stay consistent
even when the zip filename is weird.

### Non-zip files are ignored

When a wrapper is pointed at a directory, anything that isn't a real
`.zip` is skipped: stray `README.txt`, `.DS_Store`, PDFs, other
folders, and macOS resource-fork siblings (`._Compiler.zip`) all get
dropped silently. You can safely run the autograder against a messy
`Downloads/` folder.

### If `java` / `javac` aren't on your PATH

Either fix your `PATH` (preferred), or point at the binaries
directly:

```bash
./autograders/ag-procedures/ag-procedures ag-tests/procedures/inputs/ \
    -o ag-tests/procedures/outputs/ \
    --java /path/to/java --javac /path/to/javac
```

`ag-mips` and `ag-subroutines` only need `--java` (no `--javac`):

```bash
./autograders/ag-mips/ag-mips ag-tests/mips/inputs/ \
    -o ag-tests/mips/outputs/ \
    --java /path/to/java
```

If `./autograders/...` fails with a permission error, mark the
wrapper executable (`chmod +x autograders/<wrapper>/<wrapper>`) or
invoke Python directly:

```bash
python3 autograders/ag-procedures/grade.py \
    ag-tests/procedures/inputs/ -o ag-tests/procedures/outputs/
```

### CLI options

```
ag-scanner      INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
ag-parser       INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
ag-ast          INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
ag-procedures   INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
ag-mips         INPUT [-o OUTPUT_DIR] [--java JAVA]                 [--keep-temp]
ag-subroutines  INPUT [-o OUTPUT_DIR] [--java JAVA]                 [--keep-temp]
ag-codegen      INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
```

- `INPUT` — a `.zip` or a directory containing `.zip` files. Non-zip
  entries in a directory are silently ignored.
- `-o, --output` — output directory (default `./reports/`).
- `--java` / `--javac` — override auto-detected binaries.
- `--keep-temp` — keep extracted temp dirs for debugging a weird
  submission.

---

## What a student submission looks like

### Scanner (lab 1)

A folder containing just the `scanner/` package — typically:

```
Compiler/scanner/
    Scanner.java
    ScanErrorException.java
    ScannerTester.java         # optional; autograder uses its own
    ScannerTest.txt            # optional; autograder ships its own
    scannerTestAdvanced.txt    # optional
```

The autograder synthesises `scanner/_AGScannerTester.java` so the
student's hardcoded test filename in their own `ScannerTester`
cannot make every hidden test silently re-run the same baked-in
file.

### Parser (lab 3)

A folder containing the `scanner/` package and a new `parser/`
package:

```
Compiler/
    scanner/Scanner.java
    parser/Parser.java
    parser/ParserTester.java   # optional; synthetic driver wins
```

`parser.Parser` is a top-down recursive descent parser that
EXECUTES Pascal as it parses — `parseStatement` is `void` and
side-effects WRITELN output. `_AGParserTester` calls
`parseStatement` in a loop until `scanner.hasNext()` goes false.

### AST (lab 4) and later (Procedures, CodeGen)

Students zip the full `Compiler/` folder they have been building
up:

```
Compiler/
    ast/*.java           # Statement, Expression, Number, Variable,
                         # BinOp, Writeln, Assignment, Block, If,
                         # While, Readln, RepeatUntil, ...
    parser/*.java        # Parser, ParserTester / CompilerTester
    scanner/*.java
    environment/*.java   # Environment (and optionally Global/Local
                         # split)
    emitter/*.java       # only in CodeGen lab
    checkstyle.xml       # optional; bundled copy is used either way
```

The zip can contain `Compiler/` as its top-level folder *or* be a
zip of the folder's contents — the extractor normalises both.
`__MACOSX/` junk is ignored.

Students put their `public static void main(String[])` in wildly
different places: inside `parser.Parser`, inside `parser.ParserTester`,
inside a top-level `Main` or `Driver`. The grader scans the
submission, scores every candidate, and probes them in order. The
synthetic per-lab driver is preferred when present.

### Subroutines and MIPS (asm labs)

Students zip a folder of `.asm` files. Filename matching is fuzzy:
a student who saved `factorial.asm` as `factor.asm` or `ex_fact.asm`
still gets credit for the `fact` row.

Subroutines expects: `max2.asm` (with prompt + greater-of-two
message; works on negatives), `max3.asm` (must `jal max2`),
`fact.asm` (recursive + push/pop `$ra`), `fib.asm` (recursive),
and a linked-list deliverable (`sumlist.asm` / `linkedlist.asm` /
`newlistnode.asm`).

MIPS expects: `simple.asm` (Exercise 2), `mult.asm` or `add.asm`
(Exercise 4 — either is enough), `evenodd.asm` (Exercise 5),
`loops.asm` (Exercise 6), one Next-section program (`array.asm`
plus a `guessingGame` variant), and one open-ended "more
interesting" program.

---

## What goes in the report

The blanksheet layout is identical across all labs. The fine-grained
sections vary because each lab grades a fundamentally different
artifact.

1. **At-a-glance banner** — coloured cells at the top of page 1
   summarising each major rubric category. Green / amber / red
   gives the whole verdict without scrolling. Cell count varies by
   rubric size (4–7 cells typical).
2. **Quick Review** — summary bullets + overall score with a green /
   amber / red band behind the score. Sits directly under the banner
   so a fast pass sees the 3–5 line verdict before any detail
   table.
3. **Rubric** — one row per rubric line, severity-shaded. Partial-
   credit rows are tagged **REVIEW** so a human can confirm.
4. **Per-deliverable detail** —
   - Java labs (Scanner / Parser / AST / Procedures / CodeGen):
     an "Internal Functional Test Cases" table listing every
     hidden test, what was fed in (stdin if any), expected
     output, and the student's actual output.
   - Asm labs (MIPS / Subroutines): an `.asm` file inventory plus
     a per-exercise verification section showing the stdin we
     piped in, the expected substrings, and the student's
     printed output.
5. **Checkstyle Details** (Java labs only) — up to 20 concrete
   violations (file, line, rule, message).
6. **Documentation Review** (Java labs only) — one row per class
   and one row per method, listing missing tags or missing prose.
7. **Appendix: Hidden Test Suite** (Procedures only) — for each
   hidden PASCAL program, the expected behaviour and the
   student's actual output side-by-side.

Java-lab reports typically run 8–14 pages. Asm-lab reports run
3–5 pages because there is no per-method documentation listing.

---

## Layout

```
autograder-work/
├── README.md
├── requirements.txt
├── .gitignore
├── vendor/
│   ├── checkstyle-10.14.0-all.jar      # used by every Java lab
│   ├── checkstyle.xml                  # used by every Java lab
│   └── Mars4_5.jar                     # used by every asm-running lab
├── agcore/                              # shared, reusable across labs
│   ├── extractor.py                    # zip handling for every lab
│   ├── rubric.py                       # rubric items, severity model
│   ├── report.py                       # Java-lab PDF renderer
│   ├── grader.py                       # Java-lab orchestrator + dispatch
│   ├── synthetic_tester.py             # per-submission Java drivers
│   ├── scanner_runner.py               # ag-scanner test runner
│   ├── codegen_runner.py               # ag-codegen test runner
│   ├── checkstyle_runner.py            # used by every Java lab
│   ├── javadoc_parser.py               # used by every Java lab
│   ├── proximity.py                    # documentation scoring
│   ├── role_resolver.py                # student-rename tolerance
│   ├── java_runner.py                  # javac + java orchestration
│   ├── mars_runner.py                  # MARS jar orchestration
│   ├── asm_header_parser.py            # .asm header doc parsing
│   ├── mips_grader.py                  # asm-lab orchestrator
│   └── mips_report.py                  # asm-lab PDF renderer
├── autograders/
│   ├── ag-scanner/        # config.py + grade.py + ag-scanner + tests/
│   ├── ag-parser/         # config.py + grade.py + ag-parser   + tests/
│   ├── ag-ast/            # config.py + grade.py + ag-ast      + tests/
│   ├── ag-procedures/     # config.py + grade.py + ag-procedures + tests/
│   ├── ag-mips/           # config.py + grade.py + ag-mips     + tests/
│   ├── ag-subroutines/    # config.py + grade.py + ag-subroutines + tests/
│   └── ag-codegen/        # config.py + grade.py + ag-codegen  + tests/
└── ag-tests/                            # gitignored; per-lab inputs/outputs
```

Each `autograders/<lab>/` folder has the same shape: a `config.py`
that declares the rubric, role/file matchers, hidden tests, and a
`build_config()` factory; a `grade.py` orchestrator; a bash wrapper
named after the lab; and a `tests/` folder holding test inputs and
an `expected.json` describing them.

---

## Adding a new lab

1. Make `autograders/ag-<labname>/` next to the existing ones.
2. Pick the closest existing orchestrator shape:
   - Java source tree with hidden inputs and stdout matching:
     `ag-procedures` / `ag-ast` / `ag-codegen`.
   - Pure asm files run through MARS:
     `ag-mips` / `ag-subroutines`.
3. Copy that lab's `grade.py` and tweak `import config`.
4. Write `config.py`: declare `CLASS_ROLES` / `METHOD_ALIASES` (for
   Java labs) or `EXERCISES` / `ROLE_TESTS` (for asm labs), then
   write the rubric checkers, and finish with a `build_config()`
   factory that returns the right `LabConfig` / `MipsLabConfig`.
5. If the lab needs a new synthetic Java driver shape, add a
   factory in `agcore/synthetic_tester.py` and a dispatch case in
   `agcore/grader.py:_maybe_build_synthetic_tester`. The existing
   kinds (`scanner`, `parser`, `ast`, `procedures`, `codegen`)
   cover most patterns.
6. If the lab needs a custom test-pass/fail rule (e.g. the
   `prefix_then_error` mode the Scanner lab uses for the
   ScanErrorException case), add a runner under `agcore/` and
   wire it via `LabConfig.test_runner`.

The shared `agcore` modules stay untouched for run-of-the-mill new
labs — everything lab-specific lives under `autograders/ag-<labname>/`.

---

## Student-rename tolerance

The peer-review rubrics name specific classes and methods; students
often rename. The autograder reproduces the mental step a human
grader takes when they recognise a renamed class as filling the
same role.

**Java labs (role-based class + method resolution).** Each lab's
`config.py` declares a `CLASS_ROLES` dict mapping a rubric role
name (`"ProcedureCall"`, `"Environment"`, `"Statement"`, ...) to a
`RoleSpec` (preferred name, aliases, name-token sets, expected
superclass, required methods, preferred directory). `METHOD_ALIASES`
maps `(class_role, method_role)` pairs to an ordered list of
acceptable method names. `agcore/role_resolver.py` scores every
parsed class on these signals and returns the highest scorer; the
first matching alias wins for methods. A student who writes
`class ProcCall extends Expression { public int eval(Environment env) { ... } }`
resolves just like the canonical `ProcedureCall.eval`.

For the Procedures lab specifically, `Environment` can resolve to a
single class with a parent pointer OR to a `GlobalEnvironment` +
`LocalEnvironment` split — both shapes are accepted, and the
declareVariable / setVariable / getVariable check aggregates across
every env-like class.

**Asm labs (filename + content fuzzy matching).** Each `EXERCISES`
entry carries a list of preferred basenames, loose name-token
matchers, and substrings to look for in the file body. The
orchestrator scores every candidate file and binds the highest
scorer. A student who saved `loops.asm` as `range.asm` still earns
the loops-exercise credit.

---

## Airtightness (unparseable / missing-file fallbacks)

Every rubric checker that depends on AST-resolved classes or methods
(Java labs) or matched files (asm labs) is built so a single broken
input cannot cascade into "everything is missing" zeros.

- Java labs add a text-level grep fallback when `javalang` can't
  parse a file, so a student whose `Parser.java` has a missing
  semicolon still gets credit for methods that visibly exist in
  the file.
- Asm labs score per-exercise rows independently — a missing
  `array.asm` does not affect the `evenodd.asm` row, and so on.
- Rubric rows are also mutually independent: a student missing
  `ProcedureCall` still gets the full 5 pts for
  `ProcedureDeclaration`, and vice versa.

One broken piece does not cascade into unrelated rows.

---

## How synthetic Java drivers work

For every Java-source lab, the autograder generates a fresh
`_AG*Tester.java` per submission, drops it into the student's tree
under the right package, compiles it alongside the student's code,
and locks it as the main class for the hidden test suite.

| Lab        | Synthesised driver         | Drives                                       |
|------------|----------------------------|----------------------------------------------|
| Scanner    | `_AGScannerTester`         | scan one file, print one token per line      |
| Parser     | `_AGParserTester`          | loop `parser.parseStatement()` until EOF     |
| AST        | `_AGASTTester`             | loop parseStatement + `stmt.exec(env)`       |
| Procedures | `_AGTester`                | parseProgram + `program.exec(env)`           |
| CodeGen    | `_AGCodeGenTester`         | parseProgram + emit asm to `args[1]`         |

This bypasses the student's own `ParserTester` / `ScannerTester` /
`CompilerTester` for the hidden run, which means a hardcoded test
filename in the student's tester cannot make every hidden test
silently re-run the same baked-in file. The student's tester is
left intact — only the hidden suite uses the synthetic driver.

If synthesis cannot produce a confident driver (no Parser-shaped
class with a recognisable parse method, for instance), the
orchestrator falls back to probing the student's own
`public static void main(String[])` candidates in score order.

---

## How asm-lab scoring works

The rubric goes exercise-by-exercise. There is no separate test
layer: each row's job is "for this exercise, did the student
deliver a properly documented `.asm` that produces the expected
output?".

Per-exercise rows are typically split:

- **25%** for the file being present in the submission.
- **25%** for a complete header comment block (`# @author`,
  `# @version`, a description).
- **50%** for the program's runtime behaviour — stdin is piped
  via the JVM, MARS 4.5 assembles and runs the program, and
  stdout is matched case-insensitively against expected
  substrings in order. Substring matching (rather than exact
  line equality) means students who decorate output with prompts
  ("Enter a number: ") still pass.

Some exercises run multiple verification cases (e.g. evenodd is
exercised with both an even and an odd input). These are not
separate tests, just multiple eyes on the same deliverable. The
behavioural sub-score is the proportion of cases that pass.

Beyond the per-exercise rows the asm rubrics also include:

- **Header docs across all `.asm` files** — proportional credit.
- **Comment density** (MIPS) — average `#`-lines /
  total-non-blank-lines across files with instructions. Lab text
  says "comment every 2 or 3 lines"; the rubric's threshold is
  40% (full) / 25% (half) / below 25% (zero). Deliberately
  generous.
- **Open-ended "more interesting" program** (MIPS) — REVIEW row:
  file exists + has a header + assembles cleanly. Creativity is
  not autogradable; the teacher should skim the file.
- **Linked-list approach** (Subroutines) — REVIEW row that
  surfaces which approach was detected (`syscall 9` ⇒ heap, `$sp`
  manipulation in node context ⇒ stack) so the teacher can
  circle the right rubric option.

---

## Tuning the strictness

Each lab's strictness lives in its `config.py`, not in `agcore`.

**Java labs (Scanner / Parser / AST / Procedures / CodeGen)**

- `CLASS_KEYWORDS` / `METHOD_KEYWORDS` set the keyword-overlap
  thresholds for documentation proximity. Lower the threshold
  to be more permissive.
- `MIN_METHOD_DESCRIPTION_WORDS` (default `0`) flags too-short
  prose. Raise to `3`–`5` to catch one-word "TODO" stubs.
- Most rubric checkers grant partial credit proportionally;
  tightening means lowering the fractions inside the relevant
  checker (e.g. `_class_methods_tags` in ag-procedures).

**Asm labs (MIPS / Subroutines)**

- Each `MipsTestSpec` is one verification case for an exercise.
  Its `expected_substrings` list is what stdout must contain (in
  order, case-insensitively). Add or remove substrings to make
  a case stricter or looser.
- Add or remove cases per exercise to widen or narrow the
  verification. Single-case exercises rely on one input; multi-
  case exercises exercise the same `.asm` with multiple inputs.
- `min_pass_for_full` on `_scored_exercise_row(...)` lets an
  exercise earn full credit when at least N cases pass — used
  by MIPS Exercise 4 because either multiplication OR addition
  is acceptable.
- Comment-density thresholds live in `_comment_density_row`.

---

## Known caveats

- **Java labs**: every submission is compiled from scratch, so
  big trees take real CPU time. Expect ~5–15 s per submission
  with a warm JVM; the AST and Procedures labs are the slowest.
- **Asm labs**: each test invocation spawns a fresh JVM running
  the MARS jar. Expect ~1–2 s per test, so a typical submission
  runs ~10–15 s through all rubric rows.
- **The score is not gospel.** The rubric has partial-credit and
  REVIEW rows by design. The point of the blanksheet is to make
  manual review fast, not replace it — always skim the PDF
  before publishing a grade.
