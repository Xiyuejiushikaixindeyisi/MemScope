# Third-party notices

## MemOS

MemScope B04 bundles an unmodified source archive of MemOS `v2.0.32`, commit
`185ebdb925911b55c13b7efe666b74e2e292e484`, from
<https://github.com/MemTensor/MemOS>. The archive is used to build the isolated `memos`
infrastructure service. Its lock data and checksum are in
`third_party/memos/SOURCE_LOCK.json` and `third_party/memos/SHA256SUMS`.

The archive itself remains unmodified. The B04 Docker build applies two narrow, text-guarded
runtime compatibility patches to the extracted copy: an offline/configurable tokenizer default and
a disabled-scheduler shutdown guard. The exact changes are documented in
`docs/batches/B04/HANDOFF.md` and `docs/integrations/MEMOS_V2_0_32_MAP.md`.

MemOS is distributed under the Apache License, Version 2.0. A copy of its upstream
license is included at `third_party/memos/LICENSE`.

## Container images and Python packages

The B04 Compose runtime uses the official Python, Neo4j Community Edition, and Qdrant
images pinned by OCI index digest. The MemOS image installs the fully pinned upstream
`docker/requirements.txt` plus exact B04 transitive constraints during image build. Each dependency
remains subject to its own license. The exact image references are recorded in
`third_party/memos/SOURCE_LOCK.json`.

## B09 historical and B10 active delivery treatment

The formal B09 submission package repeats the MemOS Apache-2.0 license at
`solution/LICENSES/MemOS-Apache-2.0.txt` and retains the source copy under
`solution/code/third_party/memos/LICENSE`. The deterministic manifest records hashes for both paths.

Python packages and OCI images are resolved or pulled during build rather than copied from this
development environment. Their pinned identities do not replace their upstream license terms.

B10 changes the organizer boundary: the development machine builds the final project images and
places them, together with the fixed Neo4j and Qdrant images, in one offline TAR. The organizer only
loads and runs that bundle. The B10 solution ZIP still includes the fixed MemOS source archive,
source/hash locks and Apache-2.0 text so the image's third-party provenance remains reviewable.
Python dependencies are installed into the images on the development machine from one explicitly
selected HTTPS package index; the organizer performs no dependency resolution.

No root license has been selected for original MemScope source. `LICENSE_STATUS.md` makes this status
explicit. This notice records third-party attribution only and does not grant a new license for
original project code.
