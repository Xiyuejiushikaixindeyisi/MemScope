# ADR 0005: B04 three-service Compose runtime

- Status: Accepted/Frozen after B04 Gate 2
- Date: 2026-09-02
- Decision owner: user-approved B04 Gate 1 and Gate 2

## Context

MemOS `v2.0.32` uses Neo4j Community as its graph store and Qdrant as the nested vector
store in the selected default configuration. The organizer receives source in `solution.zip`
and builds it; a Dockerfile and Compose file are allowed optional delivery artifacts. No hosted
database is provided. Embedding/rerank packaging and exact organizer model IDs remain pending.

The evaluation requirement currently guaranteed by the user is self-consistency during one
container deployment lifecycle: Add and Search occur without requiring cross-deployment data
migration. The service must nevertheless be reproducible on a separate Linux Docker host.

## Decision

B04 uses one Compose deployment entry with exactly three single-purpose containers:

- `memos`: the pinned upstream MemOS API runtime;
- `neo4j`: Neo4j Community graph persistence;
- `qdrant`: vector persistence used by the Neo4j Community MemOS backend.

This is “one Compose delivery,” not “one container.” Compose owns dependency order, health,
networking, restart policy and four named volumes. No host ports are published in B04; the future
contest `memory-api` remains the only intended public service and is added in B05. All B04 traffic
is on an internal bridge network, so the running services cannot download models or packages.

MemOS receives no working model endpoint in B04. Its OpenAI-shaped LLM and embedding clients use an
explicit loopback discard endpoint, rerank uses local cosine, and chat/internet/preference/
activation/scheduler features are disabled. B04 readiness proves infrastructure initialization,
not Add/Search or model capability.

MemOS source is bundled as an unmodified deterministic Git archive at tag `v2.0.32`, commit
`185ebdb925911b55c13b7efe666b74e2e292e484`, with SHA-256, license and image digest locks.

The image build applies two narrow, text-guarded compatibility patches to the extracted copy while
leaving that archive unchanged: the B04 tokenizer default becomes configurable/offline, and disabled
scheduler shutdown tolerates an absent I/O-loop thread. Any upstream text drift fails the build.

## Why not one container with multiple processes

A single container could launch MemOS, Neo4j and Qdrant under a supervisor, but it would combine
three process lifecycles, three log streams, readiness ordering and database shutdown semantics.
It would also require a custom init/supervisor and make fault isolation and restart verification
harder. No confirmed organizer rule requires that compression. The three-container layout is the
simplest reproducible representation of the fixed MemOS architecture and still has one deployment
command.

If the final runner later requires one image/one container, that is a new deployment constraint and
triggers a separate topology review. B04 does not silently implement or promise it.

## Persistence boundary

Named volumes prove data survives `docker compose restart` and container recreation inside the
same Compose project on the same Docker host. The competition guarantee still required by the user
is only one deployment lifecycle; no cross-host backup, volume export or data migration contract is
claimed. A clean-room Gate 2 run builds and starts from a fresh directory to prove the source
package is not coupled to this checkout.

## Consequences

- Database readiness is meaningful: authenticated `cypher-shell` for Neo4j, a Qdrant TCP probe,
  MemOS HTTP health, and a separate aggregate verifier.
- A generated Neo4j password is required outside source control; there is no usable default.
- Runtime is offline, while image build still requires registry, Debian package and Python package
  access or an equivalent pre-populated cache.
- B05 must introduce the selected embedding endpoint/model/dimension and model egress. Changing the
  vector dimension requires recreating the B04 test volumes or migrating collections explicitly.
- Rerank remains optional until quality evidence justifies an external reranker.

## Revisit conditions

Revisit when the organizer publishes a one-container-only rule, an external database interface,
architecture restrictions, package/image limits, offline-build requirements, or model-weight
licensing/packaging rules.
