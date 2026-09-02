# MemScope Codemap

## B00 modules

| Path | Responsibility | May depend on |
|---|---|---|
| `src/memscope/settings.py` | Typed environment configuration and sanitized load failures | Pydantic Settings, internal errors |
| `src/memscope/errors.py` | Transport-independent structured errors | Python standard library |
| `src/memscope/logging_config.py` | Idempotent JSON/console application logging | Python standard library, Settings |
| `src/memscope/app.py` | Dependency-injectable FastAPI app factory | Settings, logging, FastAPI |
| `src/memscope/main.py` | Default ASGI composition root | App factory |
| `tests/unit/` | Settings, error, logging and app behavior | Public B00 module surfaces |
| `tests/smoke/` | In-process ASGI and real Uvicorn startup checks | Installed project and locked test dependencies |

## Dependency direction

```text
main → app → settings → errors
           ↘ logging_config → settings
           ↘ FastAPI
```

Settings and errors remain framework-independent. Future business logic must not read environment
variables or bind directly to FastAPI, databases or MemOS implementations.

## Deferred ownership

- B01: contest request/response models, `/health`, `/add`, `/search`, HTTP error mapping.
- B02: Raw Store, SQLite schema/migrations, idempotency and user/cube identity mapping.
- B03+: Memory Gateway substitutes, infrastructure and real MemOS integration.

This file records navigation and dependency direction, not implementation copies.
