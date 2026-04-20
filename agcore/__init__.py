"""
agcore: shared engine for the ATCS Compilers autograder family.

Each lab-specific autograder (autograders/ag-<lab>/grade.py) plugs lab-specific
config into the generic pipeline implemented here. Modules:

    extractor          - unzip the student submission and locate Compiler/
    checkstyle_runner  - shell out to checkstyle.jar and parse violations
    javadoc_parser     - walk Java sources and extract method/class doc info
    proximity          - score documentation against expected keyword sets
    java_runner        - compile and run the student's interpreter
    rubric             - dataclasses describing rubric items + grading state
    report             - render the colour-coded blanksheet PDF
    grader             - top-level orchestrator that ties everything together
"""
