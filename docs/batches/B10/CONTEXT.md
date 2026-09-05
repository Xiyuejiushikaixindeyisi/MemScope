# B10 context manifest

```yaml
batch: B10
name: Baseline Comprehensive Audit & Pre-Tuning Closure
historical_baseline: 4ed49dd06dbb38b3faa46de3c77e446ffcc07b96
implementation_start: ca470eb475d3d3af15fef6bed5ebc5547d8c4bab
candidate_branch: batch/b10-baseline-closure
gate_1: approved_and_implemented_2026-09-05
gate_2: pending
final_artifacts: prohibited_until_post_tuning_user_approval
```

## Facts inherited without rewriting history

- B00–B09 remain frozen at `main@4ed49dd06dbb38b3faa46de3c77e446ffcc07b96`.
- Three post-B09 commits on `main` added Linux deployment/build-source work. B10 retains their
  functional intent but does not reinterpret them as a new accepted Batch.
- B08's real exercise, restart-persistence and resource evidence was accepted only as a transferred
  obligation, not as a live pass.
- No B09 final ZIP, image release or tag was created.

## B10 workflow override

The development machine now owns source deployment, dependency installation, real reachable-API
testing, baseline evaluation, tuning, final image construction and final ZIP generation. The
organizer review machine is a load-and-run target only. It receives prebuilt Linux/amd64 images and
runtime configuration instructions; it does not install Python dependencies or build/pull images.

Development and organizer APIs may differ while both remain OpenAI compatible. The organizer's
confirmed non-secret profile is Chat `GLM-V5_1-DX`, Embedding `bge-m3` dimension 1024 and Huawei
intranet HTTP base `http://aigateway.huawei.com/v1`. External reranking remains disabled until its
exact wire contract is tested.

## Audit closure routing

Gate 1 implements the tuning-start blockers: candidate governance, Docker-context secret exclusion,
single-source build configuration, release-only Compose, source/image identity binding, organizer
load/run/verify scripts, current workflow documentation, explicit license status, port/version
alignment and deterministic delivery verification.

Product-semantic improvements such as explicit Update/Forget behavior, distributed transaction
closure, semantic contradiction handling and the empty-extraction crash window are not silently
changed in B10. They remain documented candidate risks for evidence-led tuning or a separately
approved product Batch.
