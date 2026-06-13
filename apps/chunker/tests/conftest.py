import pytest

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """
    Automatically mock AWS environment variables for all tests.
    """
    monkeypatch.setenv("AWS_SQS_STAGE_1_URL", "https://sqs.eu-central-1.amazonaws.com/123456789012/stage-1")
    monkeypatch.setenv("AWS_SQS_STAGE_2_URL", "https://sqs.eu-central-1.amazonaws.com/123456789012/stage-2")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "eu-central-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mock-secret-key")
    monkeypatch.setenv("CONTINUOUS_POLL", "false")

class MockTokenizer:
    def encode(self, text: str) -> list:
        # Simplistic word-based token encoding for mock tests
        return text.split()

    def decode(self, tokens: list) -> str:
        # Simplistic word-based token decoding for mock tests
        return " ".join(tokens)

@pytest.fixture(autouse=True)
def mock_transformers_tokenizer(monkeypatch):
    """
    Prevent outbound requests to Hugging Face Hub during tests by mocking AutoTokenizer.
    """
    try:
        from transformers import AutoTokenizer
        monkeypatch.setattr(AutoTokenizer, "from_pretrained", lambda *args, **kwargs: MockTokenizer())
    except ImportError:
        pass
