# OmaMods contributor guide

## Git

- Always use `master` as the default branch. Never assume, create, switch to,
  or recreate `main`.
- Base new work from `master`.

## Code style

- Functions: 4–20 lines. Split longer functions.
- Files: under 500 lines. Split by responsibility.
- One thing per function and one responsibility per module (SRP).
- Names: specific and unique. Avoid `data`, `handler`, and `Manager`.
  Prefer names with fewer than five grep hits in the codebase.
- Types: explicit. No `any`, `Dict`, or untyped functions.
- No code duplication. Extract shared logic into a function or module.
- Prefer early returns over nested conditionals. Use at most two indentation
  levels.
- Exception messages must include the offending value and expected shape.

## Comments

- Keep existing comments during refactors because they carry intent and
  provenance.
- Write why, not what. Skip comments such as `// increment counter` above
  `i++`.
- Public functions need docstrings with intent and one usage example.
- Reference issue numbers or commit SHAs when a line exists because of a
  specific bug or upstream constraint.

## Tests

- Tests must run through one documented project command. Define and document
  that command when the first implementation is added.
- Every new function gets a test. Bug fixes get a regression test.
- Mock external I/O (API, database, filesystem) with named fake classes, not
  inline stubs.
- Tests must be F.I.R.S.T.: fast, independent, repeatable, self-validating,
  and timely.

## Dependencies

- Inject dependencies through a constructor or parameter, not a global or
  import.
- Wrap third-party libraries behind a thin interface owned by this project.

## Structure

- Follow the framework convention in use.
- Prefer small, focused modules over god files.
- Use predictable paths such as `controller/model/view` or `src/lib/test`.

## Formatting

- Use the language default formatter (`cargo fmt`, `gofmt`, `prettier`,
  `black`, or `rubocop -A`). Do not discuss style beyond that.

## Logging

- Use structured JSON for debugging and observability logs.
- Use plain text only for user-facing CLI output.
