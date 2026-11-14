"""Extension point owned by 이훤. No classifier algorithm is implemented."""
from contracts.interfaces.modules import ClassificationInput, ClassificationOutput

AVAILABLE = False


def classify(request: ClassificationInput) -> ClassificationOutput:
    raise NotImplementedError('File classification is not implemented')
