"""Golden and validation tests for mock-sha256-vector-v1."""

import math

import pytest

from memscope.mock_model_api.deterministic import deterministic_embedding


def test_embedding_has_frozen_golden_values_and_unit_norm() -> None:
    result = deterministic_embedding("MemScope", 5)

    assert result == pytest.approx(
        (
            0.2744013071400943,
            -0.6432208085551459,
            -0.07369529978878124,
            -0.654749244456455,
            -0.27720631983094285,
        )
    )
    assert math.sqrt(sum(value * value for value in result)) == pytest.approx(1.0)
    assert deterministic_embedding("MemScope", 5) == result
    assert deterministic_embedding("不同", 5) != result
    assert len(deterministic_embedding("", 9)) == 9


@pytest.mark.parametrize(
    ("text", "dimension", "error"),
    [
        (1, 2, TypeError),
        ("a", True, TypeError),
        ("a", 1.0, TypeError),
        ("a", 0, ValueError),
        ("a", 4097, ValueError),
    ],
)
def test_embedding_rejects_invalid_inputs(
    text: object, dimension: object, error: type[Exception]
) -> None:
    with pytest.raises(error):
        deterministic_embedding(text, dimension)  # type: ignore[arg-type]
