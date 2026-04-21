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

Run every command from the `autograder-work/` directory (the one that
contains `agcore/`, `autograders/`, `vendor/`, and `ag-tests/`).

First-time setup — install dependencies:

```bash
pip install -r requirements.txt
```

Grade a single student:

```bash
./autograders/ag-procedures/ag-procedures path/to/student.zip -o reports/
```

Grade a whole folder of zips at once:

```bash
./autograders/ag-procedures/ag-procedures ag-tests/inputs/ -o ag-tests/outputs/
```

Each student gets a file `<student-name>-procedures-report.pdf` inside the
output directory, plus a batch summary at `overall.pdf` listing every
student's score.

### Non-zip files are ignored

When you point the tool at a directory, anything that isn't a real `.zip`
is skipped — stray `README.txt`, `.DS_Store`, PDFs, other folders, and
macOS resource-fork siblings (`._Compiler.zip`) all get dropped silently.
You can safely run the autograder against a messy `Downloads/` folder
that mixes submissions with other files. When you point it at a single
non-zip file, it prints `ignoring non-zip input: <name>` and exits
without grading.

### If `java` / `javac` aren't on your PATH

Either export `PATH` for the session:

```bash
export PATH="/path/to/jdk/bin:$PATH"
./autograders/ag-procedures/ag-procedures ag-tests/inputs/ -o ag-tests/outputs/
```

Or point at the binaries directly without touching `PATH`:

```bash
./autograders/ag-procedures/ag-procedures ag-tests/inputs/ -o ag-tests/outputs/ \
    --java /path/to/java --javac /path/to/javac
```

If `./autograders/...` fails with a permission error, mark the wrapper
executable (`chmod +x autograders/ag-procedures/ag-procedures`) or call
it through Python directly:

```bash
python autograders/ag-procedures/grade.py ag-tests/inputs/ -o ag-tests/outputs/
```

### CLI options

```
ag-procedures INPUT [-o OUTPUT_DIR] [--java JAVA] [--javac JAVAC] [--keep-temp]
```

- `INPUT`: a `.zip` or a directory containing `.zip` files. Non-zip
  entries in a directory are silently ignored.
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

1. **At-a-glance banner** — six coloured cells at the top of page 1: Overall
   score, Build, Rubric, Tests, Checkstyle, Docs. Green / amber / red gives
   the whole verdict without scrolling.
2. **Quick Review** — summary bullets + overall score out of 100, with a
   green/amber/red band behind the score. Sits directly under the banner
   so a teacher doing a fast pass sees the 3-5 line verdict before any
   detail table.
3. **Peer Checkoff Rubric** — one row per rubric line, taken verbatim from
   the Procedures peer review sheet. Any row where the student didn't earn
   full credit is shaded red; darker red = more severe. Partial-credit rows
   are tagged **REVIEW** so a human can confirm.
4. **Internal Functional Test Cases** — ten hidden PASCAL programs that
   exercise simple procedures, argument passing, scope isolation, return
   values, recursion, parameter shadowing, return values in expressions,
   nested calls, conditional returns, and double recursion. Each failing
   row shows the exact error (timeout, runtime error, or which output line
   diverged) — **no student code is reproduced**.
5. **Checkstyle Details** — up to 20 concrete violations (file, line, rule,
   message) so the teacher can point the student at specific fixes instead
   of just saying "clean this up."
6. **Documentation Review** — one row per class and per method. Columns
   show the member, the javadoc summary, the `file:line` location, and a
   verdict. Rows flagged `REVIEW` missed the keyword-overlap threshold or
   are missing required `@param` / `@return` / `@author` / `@version` tags.
7. **Appendix: Hidden Test Suite** (final pages) — for each hidden test,
   the full PASCAL source, the expected output, and the student's *actual*
   output side-by-side. Green cell on pass, red cell on fail. This is a
   teacher-only reference; students don't see it because the zip name is
   prepended to the report file.

The report typically runs 10–14 pages: banner + quick review + rubric
(page 1), tests + checkstyle details (page 2), documentation listing
(pages 3–10), appendix (last 2–3 pages).

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
            ├── test06_shadowing.pas
            ├── test07_return_in_expr.pas
            ├── test08_nested_call.pas
            ├── test09_conditional_return.pas
            ├── test10_fibonacci.pas
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

## Tolerating student renames (role-based resolution)

The peer-review rubric names specific classes (`ProcedureCall`,
`ProcedureDeclaration`, `Environment`, `Program`, `Parser`) and methods
(`exec`, `eval`, `declareVariable`, `setVariable`, `getVariable`,
`parseProgram`, `parseProcedureDeclaration`, `parseFactor`). Most students
follow those names, but a few will rename — `ProcedureDecl`, `Call`, `Env`,
`declareVar`, `parseProc` — and a human grading the peer review would still
recognise the renamed class as filling the same ROLE.

`agcore/role_resolver.py` reproduces that mental step. Each lab's
`config.py` declares two dictionaries:

- `CLASS_ROLES` maps a role name (e.g. `"ProcedureCall"`) to a `RoleSpec`
  with a preferred name, aliases, token sets, expected superclass, and
  required methods. The resolver scores every parsed class on a weighted
  mix of those signals and returns the highest scorer.
- `METHOD_ALIASES` maps `(class_role, method_role)` tuples to an ordered
  sequence of acceptable method names — first hit wins.

Rubric checkers then call `g.class_for_role("ProcedureCall")` and
`g.method_for_role("ProcedureCall", "eval")` instead of literal
`class_by_name("ProcedureCall")` / `method("ProcedureCall", "eval")`.
A student who writes `class ProcCall extends Expression { public int
evaluate(Environment env) { ... } }` still fulfils the role and still
earns rubric credit — the autograder doesn't zero a student out for a
stylistic rename.

A lab that genuinely needs strict-name matching simply leaves
`class_roles` and `method_aliases` empty in its `LabConfig`; the
fallback path is plain exact-name lookup.

## Tuning the strictness

- Keyword overlap thresholds live in `autograders/ag-procedures/config.py`
  under `CLASS_KEYWORDS` and `METHOD_KEYWORDS`. Each entry is
  `(keyword_list, minimum_overlap_count)`. Raising the number = stricter.
- `MIN_METHOD_DESCRIPTION_WORDS` in `config.py` (default `0`) flags docs
  whose description prose is below N words. Raise to 3 or 5 if you want
  to catch one-word "TODO" stubs.
- The `check_method` call inside `proximity_rule` uses
  `require_return=True`; flip it to `False` on a per-call basis to relax
  `@return` enforcement.
- `require_pre_post=True` on `check_method` would make `@precondition`
  and `@postcondition` mandatory — currently off because students often
  document pre/post in prose and mechanical enforcement is too noisy.
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
