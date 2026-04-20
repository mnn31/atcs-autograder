# ATCS Compilers Autograder

A reusable, lab-pluggable autograder for the ATCS Compilers & Interpreters
sequence. The first lab wired up is **Procedures**
(`autograders/ag-procedures/`); adding another lab is a matter of writing a
new `config.py` + test suite next to it.

Every student submission is a `.zip` of their `Compiler/` folder; the tool
produces a colour-coded PDF "blanksheet" report that mirrors the peer
checkoff rubric, runs a hidden functional test suite, reviews every javadoc
with keyword-proximity and `@`-tag checks, and finishes with a single quick
review box and overall score.

The blanksheet is **deliberately identical** across students so the teacher
can scan for red cells and move on.

## What you need

| Tool         | Why                                             |
| ------------ | ----------------------------------------------- |
| Python 3.8+  | the autograder itself                           |
| `reportlab`  | PDF output                                      |
| `javalang`   | parsing student Java into AST records           |
| A JDK        | `javac`/`java` for compiling & running students |

The bundled `vendor/checkstyle-10.14.0-all.jar` + `vendor/checkstyle.xml` are
shipped with this repo — no download step.

```bash
pip install -r requirements.txt
```

## Quick start (Procedures lab)

Grade a single student:

```bash
./autograders/ag-procedures/ag-procedures student.zip -o reports/
```

Grade a whole folder of zips at once:

```bash
./autograders/ag-procedures/ag-procedures ~/Downloads/submissions/ -o reports/
```

Each student gets a file `<studentzipname>_procedures_report.pdf` inside the
output directory.

### CLI options

```
ag-procedures INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
```

- `INPUT`: a `.zip` or a directory of `.zip`s.
- `-o, --output`: output directory (default `./reports/`).
- `--java / --javac`: override auto-detected binaries.
- `--keep-temp`: keep extracted temp dirs for debugging.

## How a student submission is shaped

Students zip the same `Compiler/` folder they've been building up:

```
Compiler/
    ast/*.java           # Statement, Expression, ProcedureDeclaration, ...
    parser/*.java        # Parser.java (main class), ParserTester.java, ...
    scanner/*.java
    environment/*.java
    checkstyle.xml       # optional; we use our bundled copy either way
```

The zip can either contain `Compiler/` as its top-level folder *or* be a zip
of the folder's contents — the extractor normalises both. Stray `__MACOSX/`
junk is ignored.

## What goes in the report

1. **Peer Checkoff Rubric** — one row per rubric line, taken verbatim from
   the Procedures peer review sheet. Any row where the student didn't earn
   full credit is shaded red; darker red = more severe.
2. **Internal Functional Test Cases** — five hidden PASCAL programs that
   exercise simple procedures, argument passing, scope isolation, return
   values, and recursion. Each failing row shows the exact error (timeout,
   runtime error, or which output line diverged) — **no student code is
   reproduced**.
3. **Documentation Review** — one row per class and per method. Columns
   show the member, the javadoc summary, and a verdict. Rows flagged
   `REVIEW` missed the keyword-proximity threshold or are missing required
   `@param` / `@return` / `@author` / `@version` tags.
4. **Quick Review** — summary bullets + overall score out of 100, with a
   green/amber/red band behind the score.

The report is capped well under 10 pages: rubric on page 1, tests on page 2,
documentation listing + quick review on page 3+ (grows with the number of
methods, but no class-by-class blowups).

## Layout

```
autograder-work/
├── README.md
├── requirements.txt
├── .gitignore
├── vendor/
│   ├── checkstyle-10.14.0-all.jar
│   └── checkstyle.xml
├── agcore/                          # shared, reusable across labs
│   ├── extractor.py
│   ├── checkstyle_runner.py
│   ├── javadoc_parser.py
│   ├── proximity.py
│   ├── java_runner.py
│   ├── rubric.py
│   ├── grader.py
│   └── report.py
└── autograders/
    └── ag-procedures/               # Procedures-lab specific
        ├── grade.py                 # CLI entry point
        ├── ag-procedures            # bash wrapper
        ├── config.py                # rubric + keywords + test loader
        └── tests/                   # hidden PASCAL test programs
            ├── test01_simple.pas
            ├── test02_args.pas
            ├── test03_scope.pas
            ├── test04_return.pas
            ├── test05_recursion.pas
            └── expected.json
```

## Adding a new lab

1. Make `autograders/ag-<labname>/` next to `ag-procedures/`.
2. Copy `grade.py` and tweak the `import config` line if your config lives
   elsewhere.
3. Write `config.py` — define `RUBRIC`, keyword dictionaries, a
   `build_config()` factory, and a `proximity_rule` function.
4. Drop hidden test cases + `expected.json` into `tests/`.

The shared `agcore` package stays untouched: everything lab-specific lives
under `autograders/ag-<labname>/`.

## Tuning the strictness

- Keyword proximity thresholds live in `autograders/ag-procedures/config.py`
  under `CLASS_KEYWORDS` and `METHOD_KEYWORDS`. Raising a threshold = stricter.
- The `check_method` call inside `proximity_rule` uses
  `require_return=True`; flip it to `False` on a per-call basis to relax
  `@return` enforcement.
- Rubric checkers grant partial credit proportionally; tighten by lowering
  the fractions in `_class_methods_tags`, etc.

## Known caveats

- Every submission is compiled from scratch, so big classes of students take
  real CPU time. Expect ~5-15 s per submission with a warm JVM.
- `java_runner.py` stages each test file into `Compiler/parser/` so the
  student's `main()` relative-path logic works. It cleans up after itself,
  but `--keep-temp` leaves the staged copies in place.
- The rubric has partial-credit checks. Don't treat the score as gospel —
  the point of the blanksheet is to make manual review fast, not replace it.
