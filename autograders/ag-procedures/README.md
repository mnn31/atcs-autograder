# ag-procedures

Lab-specific autograder for the **Procedures** lab of ATCS Compilers. See
the repo-level `README.md` for installation, overall architecture, and the
report layout. This README covers the pieces that are unique to the
Procedures lab.

## Running

```bash
./ag-procedures student.zip -o reports/       # single student
./ag-procedures submissions/   -o reports/    # every .zip in a dir
```

The graded PDF is written to `reports/<zipstem>_procedures_report.pdf`.

## Hidden test cases

Five small PASCAL programs in `tests/`. Each exercises one concept the
Procedures rubric cares about:

| File                   | Exercise                                                 | Expected stdout         |
| ---------------------- | -------------------------------------------------------- | ----------------------- |
| `test01_simple.pas`    | Exercise 1: zero-arg procedure mutates a global variable | `5`                     |
| `test02_args.pas`      | Exercise 2: recursive procedure with two parameters      | `1 2 3 4` (each own ln) |
| `test03_scope.pas`     | Exercise 3: parameter scope isolation                    | `5`, `3`                |
| `test04_return.pas`    | Exercise 4: Pascal-style return values                   | `5`, `10`, `49`         |
| `test05_recursion.pas` | Recursive factorial stress test                          | `1`, `1`, `120`, `720`  |

Expected outputs live in `tests/expected.json`. Edit both the `.pas` file
and the JSON if you want to change a test.

## How the rubric maps onto checks

The rubric rows in `config.py` are kept in the same order as the peer
review sheet. Each checker is a small function in `config.py` that inspects
the parsed-up submission and returns a `CheckResult` with points earned + a
short free-text note. Severity (0..3) drives the row shade in the PDF.

Rubric item → checker:

- **AST classes** → `_has_both_ast_classes`
- **ProcedureDeclaration class/method doc** → `_class_header_tags`,
  `_class_methods_tags`
- **ProcedureDeclaration extends Statement + exec** →
  `_procdecl_extends_and_exec`
- **ProcedureDeclaration parses params + block body** →
  `_procdecl_params_and_body`
- **ProcedureCall class/method doc** → same helpers as above
- **ProcedureCall extends Expression + eval** →
  `_proccall_extends_and_eval` (scans the source file for `getProcedure`,
  `globalScope`, `declareVariable`, etc.)
- **Program class (does NOT extend Statement)** → `_program_class`
- **parseProgram + parseProcedure** → `_parse_program_and_procedure`
  (presence-check + depends on hidden tests)
- **Environment hierarchy** → `_env_hierarchy` (parent field + two ctors)
- **declareVariable / setVariable / getVariable** →
  `_env_declare_set_get`
- **Parser handles PROCEDURE + parseFactor handles calls** →
  `_parser_procedure_and_factor`
- **Testing** → `_testing_proc_tests` (fraction of hidden tests passed)

Documentation proximity is driven by `CLASS_KEYWORDS` / `METHOD_KEYWORDS`
dictionaries at the top of `config.py`. Every method not explicitly listed
gets an audit that only fails if it's missing a javadoc or its `@param` /
`@return` tags.

## Tweaking

- Stricter proximity → raise the thresholds at the top of `config.py`.
- More / different hidden tests → drop a `.pas` file into `tests/` and add
  an entry to `tests/expected.json`.
- Different checkstyle → replace `vendor/checkstyle.xml` (the jar stays
  put).

## Output contract

The PDF is the same shape for every student:

1. Header (lab name, inferred student name, graded date)
2. Peer Checkoff Rubric table (14 rows)
3. Internal Functional Test Cases table (5 rows)
4. Documentation Review table (one row per class + one per method)
5. Quick Review box (bulleted summary + overall score)

Rows failing a check are shaded light → dark red by severity. No student
code appears in the PDF.
