import numpy as np

from investigator.domain.services.rl.outcome_tracker import _convert_numpy_types


def test_convert_numpy_types_recursively_normalizes_database_values():
    value = {
        "int": np.int64(7),
        "float": np.float64(1.25),
        "bool": np.bool_(True),
        "array": np.array([1, 2, 3]),
        "nested": [np.float32(2.5), (np.int32(4), np.bool_(False))],
    }

    converted = _convert_numpy_types(value)

    assert converted == {
        "int": 7,
        "float": 1.25,
        "bool": True,
        "array": [1, 2, 3],
        "nested": [2.5, (4, False)],
    }
    assert isinstance(converted["int"], int)
    assert isinstance(converted["float"], float)
    assert isinstance(converted["bool"], bool)
