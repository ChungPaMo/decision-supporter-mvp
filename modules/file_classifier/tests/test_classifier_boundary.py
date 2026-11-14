import pytest
from pydantic import ValidationError
from contracts.interfaces.modules import ClassificationInput
from file_classifier import classify


def test_no_fake_classification():
    request = ClassificationInput(filename='synthetic.csv', sha256='0' * 64,
                                  sheets=[{'name': 'S', 'columns': ['code'], 'sample_rows': [['001']]}])
    with pytest.raises(NotImplementedError): classify(request)


def test_classifier_rejects_paths_and_unbounded_samples():
    with pytest.raises(ValidationError):
        ClassificationInput(filename='../private.csv', sha256='0' * 64, sheets=[])
    with pytest.raises(ValidationError):
        ClassificationInput(filename='a.csv', sha256='0' * 64,
                            sheets=[{'name': 'S', 'columns': ['a'], 'sample_rows': [['1']] * 21}])
