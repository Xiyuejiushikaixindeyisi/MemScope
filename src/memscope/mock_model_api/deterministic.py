"""Stable model substitutes that never use randomized process hashing."""

import hashlib
import math

_EMBEDDING_DOMAIN = b"memscope.mock.embedding.v1\0"
_UINT32_MAX = 2**32 - 1


def deterministic_embedding(text: str, dimension: int) -> tuple[float, ...]:
    """Return one L2-normalized mock-sha256-vector-v1 embedding."""

    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if isinstance(dimension, bool) or not isinstance(dimension, int):
        raise TypeError("dimension must be an integer")
    if not 1 <= dimension <= 4096:
        raise ValueError("dimension must be between 1 and 4096")

    seed = _EMBEDDING_DOMAIN + text.encode("utf-8")
    values: list[float] = []
    counter = 0
    while len(values) < dimension:
        digest = hashlib.sha256(seed + counter.to_bytes(4, "big")).digest()
        for offset in range(0, len(digest), 4):
            integer = int.from_bytes(digest[offset : offset + 4], "big")
            values.append(2 * integer / _UINT32_MAX - 1)
            if len(values) == dimension:
                break
        counter += 1

    # Every mapped numerator is odd over the odd uint32 maximum, so no component
    # can equal zero and a non-empty vector cannot have zero norm.
    norm = math.sqrt(sum(value * value for value in values))
    return tuple(value / norm for value in values)
