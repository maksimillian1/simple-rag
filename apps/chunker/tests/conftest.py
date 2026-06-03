import pytest

@pytest.fixture(autouse=True)
def mock_env_vars(monkeypatch):
    """
    Automatically mock AWS environment variables for all tests.
    """
    monkeypatch.setenv("AWS_SQS_STAGE_1_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/stage-1")
    monkeypatch.setenv("AWS_SQS_STAGE_2_URL", "https://sqs.us-east-1.amazonaws.com/123456789012/stage-2")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "mock-access-key")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "mock-secret-key")
    monkeypatch.setenv("CONTINUOUS_POLL", "false")
