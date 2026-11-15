import pytest
from pydantic import ValidationError
from contracts.interfaces.modules import ClassificationInput
from file_classifier import AVAILABLE, classify


def test_undecidable_input_is_held_with_reasons_not_guessed():
    request = ClassificationInput(filename='synthetic.csv', sha256='0' * 64,
                                  sheets=[{'name': 'S', 'columns': ['code'], 'sample_rows': [['001']]}])
    output = classify(request)
    assert AVAILABLE is True
    assert output.recommended_entity is None and output.hold and output.reasons and output.candidates == []


def test_classifier_rejects_paths_and_unbounded_samples():
    with pytest.raises(ValidationError):
        ClassificationInput(filename='../private.csv', sha256='0' * 64, sheets=[])
    with pytest.raises(ValidationError):
        ClassificationInput(filename='a.csv', sha256='0' * 64,
                            sheets=[{'name': 'S', 'columns': ['a'], 'sample_rows': [['1']] * 21}])
