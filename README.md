# ATCS Compilers Autograder

A reusable, lab-pluggable autograder for the ATCS Compilers & Interpreters
sequence. Two labs are currently wired up:

- **Procedures** (`autograders/ag-procedures/`) — grades a `Compiler/`
  folder of Java sources implementing a Pascal interpreter.
- **MIPS** (`autograders/ag-mips/`) — grades a folder of `.asm` files
  for Lab 5 (MIPS assembly), running each in the bundled MARS 4.5
  simulator and matching stdout against expected substrings.

Adding another lab is a matter of writing a new `config.py` + test
suite next to those.

Every student submission is a `.zip`. The tool produces a colour-coded
PDF "blanksheet" report that mirrors the peer checkoff rubric, runs a
hidden functional test suite, and finishes with a quick review box and
overall score. Both labs share the same banner / Quick Review / rubric
layout so a teacher who can skim one can skim the other.

The blanksheet is **deliberately identical** across students so the
teacher can scan for red cells and move on.

---

## Install from scratch (5 minutes)

If you're on a fresh machine with nothing but a terminal, run the steps
in order. Everything below is copy-paste.

### 1. Install the two prerequisites

You need **Python 3.8+** and a **Java Development Kit (JDK)** with both
`java` and `javac`. The bundled `java` shipped with macOS is fine, but
it does not include `javac` on its own — you have to install a full
JDK. (The MIPS lab on its own only needs `java`, but the Procedures
lab needs `javac` to compile student code, so installing the JDK is
the simplest path that covers both labs.)

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
python3 --version     # should print Python 3.8 or newer
java -version         # should print a runtime version
javac -version        # should print a compiler version (NOT "command not found")
```

If `javac` is missing and `java` works, you installed the JRE only — go
back and install a JDK (`openjdk-17-jdk` on Ubuntu, `openjdk@17` on
macOS).

### 2. Clone the repo

```bash
git clone https://github.com/mnn31/atcs-autograder.git
cd atcs-autograder/autograder-work
```

All commands from here run from inside `autograder-work/` (the folder
that contains `agcore/`, `autograders/`, `vendor/`, and `ag-tests/`).

### 3. Install the Python dependencies

Using a virtual environment is optional but recommended so you don't
touch your system Python:

```bash
python3 -m venv .venv
source .venv/bin/activate      # on Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

`requirements.txt` is two lines — `reportlab` (PDF output) and
`javalang` (Java AST parsing). Everything else is bundled: the
checkstyle jar, the MARS 4.5 simulator jar, and the checkstyle config
all live in `vendor/`.

### 4. Smoke test

Drop a student's submission zip somewhere and run the appropriate lab:

```bash
# Procedures (Java Compiler/ folder):
./autograders/ag-procedures/ag-procedures path/to/Compiler.zip \
    -o ag-tests/procedures/outputs/

# MIPS (.asm files):
./autograders/ag-mips/ag-mips path/to/MIPS.zip \
    -o ag-tests/mips/outputs/
```

You should see one line per grading stage and then:

```
[ag-procedures]   -> ag-tests/procedures/outputs/firstname-lastname-procedures-report.pdf  (XX.X%)
```

Open that PDF. If the banner, Quick Review box, and rubric table are
all there, the install is working.

---

## Per-lab input/output layout

Submissions for each lab live under their own folder, and reports
land next to them:

```
ag-tests/
├── procedures/
│   ├── inputs/        <- student Compiler.zip files for the Procedures lab
│   └── outputs/       <- generated PDF reports + overall.pdf
└── mips/
    ├── inputs/        <- student MIPS.zip files for the MIPS lab
    └── outputs/       <- generated PDF reports + overall.pdf
```

`ag-tests/` is gitignored, so committing zips here won't accidentally
push student work into the repo.

---

## Grading submissions

### Procedures lab

```bash
# Single student:
./autograders/ag-procedures/ag-procedures path/to/student.zip \
    -o ag-tests/procedures/outputs/

# Whole folder:
./autograders/ag-procedures/ag-procedures ag-tests/procedures/inputs/ \
    -o ag-tests/procedures/outputs/
```

### MIPS lab

```bash
# Single student:
./autograders/ag-mips/ag-mips path/to/student.zip \
    -o ag-tests/mips/outputs/

# Whole folder:
./autograders/ag-mips/ag-mips ag-tests/mips/inputs/ \
    -o ag-tests/mips/outputs/
```

Each student gets a file `<first>-<last>-<lab>-report.pdf` inside the
output directory, plus a batch summary at `overall.pdf` listing every
student's score. The student name comes from the `@author` tag in the
class-level javadoc (Procedures) or the `# @author` line in the .asm
header (MIPS), so reports stay consistent even if the zip filename is
weird.

### Non-zip files are ignored

When you point either tool at a directory, anything that isn't a real
`.zip` is skipped — stray `README.txt`, `.DS_Store`, PDFs, other
folders, and macOS resource-fork siblings (`._Compiler.zip`) all get
dropped silently. You can safely run the autograder against a messy
`Downloads/` folder.

### If `java` / `javac` aren't on your PATH

Either fix your `PATH` (preferred):

```bash
export PATH="/path/to/jdk/bin:$PATH"
./autograders/ag-procedures/ag-procedures ag-tests/procedures/inputs/ \
    -o ag-tests/procedures/outputs/
```

or point at the binaries directly without touching `PATH`:

```bash
./autograders/ag-procedures/ag-procedures ag-tests/procedures/inputs/ \
    -o ag-tests/procedures/outputs/ \
    --java /path/to/java --javac /path/to/javac
```

ag-mips only needs `--java` (no `--javac`):

```bash
./autograders/ag-mips/ag-mips ag-tests/mips/inputs/ \
    -o ag-tests/mips/outputs/ \
    --java /path/to/java
```

If `./autograders/...` fails with a permission error, mark the wrapper
executable (`chmod +x autograders/ag-procedures/ag-procedures`) or
call it through Python directly:

```bash
python3 autograders/ag-procedures/grade.py \
    ag-tests/procedures/inputs/ -o ag-tests/procedures/outputs/
python3 autograders/ag-mips/grade.py \
    ag-tests/mips/inputs/ -o ag-tests/mips/outputs/
```

### CLI options

```
ag-procedures INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
ag-mips       INPUT [-o OUTPUT_DIR] [--java JAVA]                 [--keep-temp]
```

- `INPUT`: a `.zip` or a directory containing `.zip` files. Non-zip
  entries in a directory are silently ignored.
- `-o, --output`: output directory (default `./reports/`).
- `--java / --javac`: override auto-detected binaries.
- `--keep-temp`: keep extracted temp dirs for debugging.

---

## How a student submission is shaped

### Procedures

Students zip the same `Compiler/` folder they've been building up:

```
Compiler/
    ast/*.java           # Statement, Expression, ProcedureDeclaration, ...
    parser/*.java        # Parser.java, ParserTester.java, ...
    scanner/*.java
    environment/*.java
    checkstyle.xml       # optional; we use our bundled copy either way
```

The zip can either contain `Compiler/` as its top-level folder *or* be
a zip of the folder's contents — the extractor normalises both. Stray
`__MACOSX/` junk is ignored.

Students put their `public static void main(String[])` in wildly
different places: inside `parser.Parser`, inside `parser.ParserTester`,
inside a top-level `Main` or `Driver`, etc. The grader scans the
submission, scores every candidate, and probes them in order — so a
student whose main lives in `ParserTester` is still graded correctly.
The Quick Review box notes which main class actually ran when it
wasn't the default.

### MIPS

Students zip a folder of `.asm` files. The expected exercises (per Lab
5 PDF) are:

- `simple.asm` — Exercise 2 sample 2+3 program
- something like `mult.asm` / `add.asm` — Exercise 4 (read inputs +
  compute + print)
- `evenodd.asm` — Exercise 5
- `loops.asm` — Exercise 6
- one Next-section program: `array.asm` (sum/avg/min/max) and either
  `guessingGame.asm` variant
- one "more interesting MIPS program of your own choice"

Students name files inconsistently (`parity.asm` instead of
`evenodd.asm`, `range.asm` instead of `loops.asm`, etc.). The grader
fuzzy-matches each rubric exercise to a student file using preferred
basenames, name-token sets, and content substrings, so a student who
renamed a file still gets credit. The leftover unmatched `.asm` is
treated as the "interesting" open-ended program.

---

## What goes in the report

Both labs share the same overall layout. The fine-grained sections
differ because they grade fundamentally different things.

1. **At-a-glance banner** — five (MIPS) or six (Procedures) coloured
   cells at the top of page 1. Green / amber / red gives the whole
   verdict without scrolling.
2. **Quick Review** — summary bullets + overall score with a green /
   amber / red band behind the score. Sits directly under the banner
   so a teacher doing a fast pass sees the 3–5 line verdict before
   any detail table.
3. **Rubric** — one row per rubric line, severity-shaded. Partial-
   credit rows are tagged **REVIEW** so a human can confirm.
4. **Per-test detail** —
   - Procedures: an "Internal Functional Test Cases" table for the
     ten hidden PASCAL programs.
   - MIPS: an `.asm` file inventory + a per-exercise stdin / expected
     / actual stdout appendix.
5. **(Procedures only) Checkstyle Details** — up to 20 concrete
   violations (file, line, rule, message).
6. **(Procedures only) Documentation Review** — one row per class
   and per method.
7. **Appendix: Hidden Test Suite** (final pages) — for each hidden
   test, the expected behaviour and the student's *actual* output
   side-by-side. Green cell on pass, red cell on fail.

A typical Procedures report runs 10–14 pages; MIPS reports run 3–5
pages because there's no per-method documentation listing.

---

## Layout

```
autograder-work/
├── README.md
├── requirements.txt
├── .gitignore
├── vendor/
│   ├── checkstyle-10.14.0-all.jar      # used by ag-procedures
│   ├── checkstyle.xml                  # used by ag-procedures
│   └── Mars4_5.jar                     # used by ag-mips
├── agcore/                              # shared, reusable across labs
│   ├── extractor.py                    # zip handling, both labs
│   ├── rubric.py                       # rubric items, severity
│   ├── report.py                       # Procedures PDF renderer
│   ├── grader.py                       # Procedures orchestrator
│   ├── checkstyle_runner.py            # ag-procedures only
│   ├── javadoc_parser.py               # ag-procedures only
│   ├── proximity.py                    # ag-procedures only
│   ├── role_resolver.py                # ag-procedures only
│   ├── java_runner.py                  # ag-procedures only
│   ├── mars_runner.py                  # ag-mips only
│   ├── asm_header_parser.py            # ag-mips only
│   ├── mips_grader.py                  # MIPS orchestrator
│   └── mips_report.py                  # MIPS PDF renderer
├── autograders/
│   ├── ag-procedures/
│   │   ├── grade.py
│   │   ├── ag-procedures               # bash wrapper
│   │   ├── config.py
│   │   └── tests/                      # PASCAL programs + expected.json
│   └── ag-mips/
│       ├── grade.py
│       ├── ag-mips                     # bash wrapper
│       ├── config.py
│       └── tests/                      # reserved for future per-test
│                                       #   files; current setup keeps
│                                       #   stdin inline in config.py
└── ag-tests/                            # gitignored
    ├── procedures/
    │   ├── inputs/                     # student zips
    │   └── outputs/                    # generated PDFs
    └── mips/
        ├── inputs/                     # student zips
        └── outputs/                    # generated PDFs
```

---

## Adding a new lab

1. Make `autograders/ag-<labname>/` next to the existing autograders.
2. Decide which orchestrator shape fits — Procedures-style (Java
   source tree + javadoc) or MIPS-style (flat .asm + simulator
   runner). Most labs will fit one of those two patterns.
3. Copy the closest existing `grade.py` and tweak its `import config`.
4. Write `config.py` — define the rubric, role/file matchers, hidden
   tests, and a `build_config()` factory that returns the right
   `LabConfig` / `MipsLabConfig`.

The shared `agcore` modules stay untouched: everything lab-specific
lives under `autograders/ag-<labname>/`.

---

## Tolerating student renames

Both labs do this differently because the source shape is different.

**Procedures (role-based class + method resolution).** The peer-review
rubric names specific classes (`ProcedureCall`, `ProcedureDeclaration`,
`Environment`, `Program`, `Parser`) and methods (`exec`, `eval`,
`declareVariable`, ...). Students often rename — `ProcedureDecl`,
`Call`, `Env`, `declareVar`, `parseProc` — and a human grading the
peer review would still recognise the renamed class as filling the
same ROLE.

`agcore/role_resolver.py` reproduces that mental step. Each lab's
`config.py` declares a `CLASS_ROLES` dict mapping a role name to a
`RoleSpec` (preferred name, aliases, token sets, expected superclass,
required methods). The resolver scores every parsed class on a
weighted mix of those signals and returns the highest scorer.

**MIPS (filename + content fuzzy matching).** Students name their
`.asm` files inconsistently. Each `EXERCISES` entry in
`autograders/ag-mips/config.py` carries a list of preferred basenames,
loose name-token matchers, and substrings to look for in the file
body. The orchestrator scores every candidate and binds the highest
scorer. A student who saved `loops.asm` as `range.asm` still earns
the loops-exercise credit.

---

## Airtight rubric (unparseable / missing-file fallbacks)

Every rubric checker that depends on AST-resolved classes or methods
(Procedures) or matched files (MIPS) is built so a single broken
input can't cascade into "everything is missing" zeros. Procedures
adds a text-level grep fallback when javalang can't parse a file.
MIPS scores per-exercise rows independently so a missing `array.asm`
doesn't affect the `evenodd.asm` row, and so on.

Rubric rows are also mutually independent: a student missing
`ProcedureCall` still gets the full 5 pts for `ProcedureDeclaration`,
and vice versa. One broken piece does not cascade into unrelated
rows.

---

## How MIPS scoring works

Per-exercise rubric rows are split:

- **25%** for the file being present in the submission.
- **25%** for a complete header comment block (`# @author`,
  `# @version`, a description).
- **50%** for the program's runtime behaviour — stdin is piped in
  via the JVM, MARS 4.5 assembles + runs the program, and stdout is
  matched case-insensitively against expected substrings *in order*.
  Substring matching (rather than exact line equality) means students
  who decorate output with prompts ("Enter a number: ") still pass.

The rubric also includes:

- **Header docs across all .asm files** — proportional credit.
- **Comment density** — average `#`-lines / total-non-blank-lines
  across files with instructions. Lab text says "comment every 2 or
  3 lines"; the rubric's threshold is 40% (full) / 25% (half) / below
  25% (zero). A soft signal, deliberately generous.
- **Open-ended "more interesting" program** — REVIEW row: file
  exists + has a header + assembles cleanly. Creativity is not
  autogradable; the teacher should skim the file.

---

## Tuning the strictness

### Procedures

- Keyword overlap thresholds live in
  `autograders/ag-procedures/config.py` under `CLASS_KEYWORDS` and
  `METHOD_KEYWORDS`.
- `MIN_METHOD_DESCRIPTION_WORDS` (default `0`) flags too-short
  description prose.
- Rubric checkers grant partial credit proportionally; tighten by
  lowering the fractions in `_class_methods_tags`, etc.

### MIPS

- Each `MipsTestSpec` in `autograders/ag-mips/config.py` lists its
  expected substrings. Add or remove substrings to make a row
  stricter or looser. Order matters (substrings must appear in
  stdout in the listed order).
- The `min_pass_for_full` arg on `_scored_exercise_row(...)` lets a
  row earn full credit when at least N specs pass — used for
  Exercise 4 because either multiplication OR addition is acceptable.
- Comment-density thresholds live in `_comment_density_row`.

---

## Known caveats

- Procedures: every submission is compiled from scratch, so big
  classes take real CPU time. Expect ~5–15 s per submission with a
  warm JVM.
- MIPS: each test invocation spawns a fresh JVM running the MARS jar.
  Expect ~1–2 s per test, so a typical submission takes ~10–15 s
  through all rubric rows.
- The rubric has partial-credit checks. Don't treat the score as
  gospel — the point of the blanksheet is to make manual review
  fast, not replace it.
