# B09 reproducible delivery runbook

This runbook builds archives from a clean frozen source commit. It never reads a private environment
file, starts services, calls a model API, creates a Git tag or uploads an artifact.

## 1. Preflight

Record the exact 40-character source commit and require a clean worktree:

```bash
git rev-parse HEAD
git status --short
python3 --version
```

Verify the fixed MemOS source and the guarded patch preimages:

```bash
cd third_party/memos
sha256sum --check SHA256SUMS
cd ../..
python3 docker/memos/apply_patchset.py \
  --source /path/to/a/freshly-extracted-memos-tree --verify-only
```

The patch check uses a new extracted tree and must not modify the tracked source archive. Existing
unit tests also verify archive, license, image digest and patch-lock identities.

## 2. Build reproducibility previews

Use two empty output directories outside the repository. Substitute the verified commit literally;
do not pass a branch name or abbreviated hash.

```bash
python3 scripts/build_b09_delivery.py build \
  --source-root . \
  --output-dir /secure/b09-preview-a \
  --candidate-commit <40-character-commit> \
  --mode handoff

python3 scripts/build_b09_delivery.py build \
  --source-root . \
  --output-dir /secure/b09-preview-b \
  --candidate-commit <40-character-commit> \
  --mode handoff
```

Compare the two reported `archive_sha256` values; they must be identical. Repeat with
`--mode submission`. The builder refuses an output directory below the source tree and refuses to
overwrite an existing artifact.

Verify each artifact and its sidecar independently:

```bash
python3 scripts/build_b09_delivery.py verify \
  --archive /secure/b09-preview-a/memscope-b09-handoff-<12-character-commit>.zip \
  --sha256-file /secure/b09-preview-a/memscope-b09-handoff-<12-character-commit>.zip.sha256
```

The verifier checks every member path, manifest entry, size and SHA-256 without extracting archive
members. The embedded manifest intentionally does not list or hash itself; the sidecar hashes the
complete ZIP and therefore remains outside it.

## 3. Handoff versus formal submission

The `handoff` package is for the tuning machine. It includes deterministic tests, deployment and
verification runbooks, public evaluation assets and templates needed to return an auditable final
candidate. It excludes `.git`, caches, local environments, runtime data, logs and credentials.

The `submission` package is deliberately smaller:

```text
solution/
├── INSTRUCTION.md
├── SDD.md
├── THIRD_PARTY_NOTICES.md
├── DELIVERY_MANIFEST.json
├── LICENSES/MemOS-Apache-2.0.txt
└── code/
```

It contains runtime/build source, exact locks, selected deployment/verification guides and no test
suite, Batch history or evaluation dataset. The tuning machine may regenerate it after approved
configuration/source changes, but must return the final source tree or unified patch.

## 4. Tuning-machine sequence

1. Compare the received handoff ZIP SHA-256 with the out-of-band sidecar/record.
2. Run the ten-minute Docker/native capability preflight and select a viable path.
3. Probe the real Chat and Embedding endpoints and measure the exact Embedding dimension.
4. Execute B08 `exercise`, `prepare-restart`, controlled restart and `verify-restart`; collect only
   sanitized resource/storage observations.
5. Run Smoke → single sample → tens of questions → full baseline before single-variable tuning.
6. Freeze the selected source and non-secret configuration, then build/verify `submission` mode.
7. Return the final ZIP/hash, baseline and tuning report, B08 evidence, configuration fingerprint
   and all source/config differences.

Do not include the B08 restart state, keys, raw logs, conversation/query content, vectors, database
files or private model responses in the return bundle.

## 5. Stop and revision conditions

Cross-user evidence, changed replay identity, lost persistence, Add at least 120 seconds, Search at
least 60 seconds, unclassified failures, credential exposure or manifest mismatch rejects the live
candidate. A required product, contract, schema, dependency, MemOS patch or worker-topology change
must return to the owning Batch for approval; packaging is not authorization to patch it.

## 6. Gate boundary and current hold

The user accepted/froze B09 Gate 2 on 2026-09-04 but explicitly prohibited generating the final
handoff ZIP and out-of-band SHA-256 while additional development and version consolidation remain.
Do not execute the final build commands, promote either preview hash, create a sidecar/tag, upload or
transfer an artifact. This hold remains until the additional scope is approved and the user gives a
new explicit artifact instruction.
