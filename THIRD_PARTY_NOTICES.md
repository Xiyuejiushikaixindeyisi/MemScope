# Third-party notices

## MemOS

MemScope B04 bundles an unmodified source archive of MemOS `v2.0.32`, commit
`185ebdb925911b55c13b7efe666b74e2e292e484`, from
<https://github.com/MemTensor/MemOS>. The archive is used to build the isolated `memos`
infrastructure service. Its lock data and checksum are in
`third_party/memos/SOURCE_LOCK.json` and `third_party/memos/SHA256SUMS`.

MemOS is distributed under the Apache License, Version 2.0. A copy of its upstream
license is included at `third_party/memos/LICENSE`.

## Container images and Python packages

The B04 Compose runtime uses the official Python, Neo4j Community Edition, and Qdrant
images pinned by OCI index digest. The MemOS image installs the fully pinned upstream
`docker/requirements.txt` during image build. Each dependency remains subject to its
own license. The exact image references are recorded in
`third_party/memos/SOURCE_LOCK.json`.
