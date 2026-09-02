# ADR 0001: Python Toolchain and Project Layout

- Status: Accepted for B00 implementation
- Decision date: 2026-09-02
- Scope: B00 engineering foundation

## Context

MemScope needs a deterministic no-key development path and must remain evolvable for a stronger
baseline and currently unknown finals requirements. The fixed MemOS v2.0.32 upstream supports
Python 3.10～3.13 and uses FastAPI/Uvicorn.

## Decision

- Use CPython 3.11.16 and declare `requires-python = ">=3.11,<3.12"`.
- Use a `src/memscope` package layout.
- Use uv/uv_build 0.12.9 and commit `uv.lock`.
- Pin direct runtime and development dependencies; frozen sync is mandatory.
- Align FastAPI, Pydantic, Pydantic Settings and Uvicorn with versions resolved by the fixed MemOS
  lock where practical.
- Use standard-library logging rather than adding a structured-logging dependency in B00.

## Consequences

- The current machine needs an isolated Python 3.11 and uv before tests can run.
- B00 can run without MemOS or organizer credentials.
- Later deployment work must decide how the fixed toolchain and artifacts are made available in
  offline or Compose-restricted evaluation environments.
- Changing Python, package manager, build backend or direct pins requires a new review.

## Dependency and license record

The B00 direct runtime dependencies are FastAPI (MIT), Pydantic (MIT), Pydantic Settings (MIT)
and Uvicorn (BSD-3-Clause). Development dependencies are not shipped as runtime requirements.
Actual package metadata and all transitive dependencies must be checked after lock generation;
B09 remains responsible for the complete `THIRD_PARTY_NOTICES.md`.
