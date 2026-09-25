"""Shared offline fakes for Android and iOS agent tests."""

from collections import deque
from copy import deepcopy
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from phone_agent.model import ModelResponse


@dataclass
class FakeScreenshot:
    base64_data: str
    width: int = 1080
    height: int = 2400
    is_sensitive: bool = False
    is_fallback: bool = False


class FakeModelClient:
    def __init__(self, *results):
        self.results = deque(results)
        self.requests = []

    def request(self, messages):
        self.requests.append(deepcopy(messages))
        result = self.results.popleft()
        if isinstance(result, BaseException):
            raise result
        return result


class FakeActionHandler:
    def __init__(self, result=None):
        self.calls = []
        self.result = result or SimpleNamespace(
            success=True,
            should_finish=False,
            message=None,
        )

    def execute(self, action, width, height):
        self.calls.append((deepcopy(action), width, height))
        return self.result


@pytest.fixture
def response_factory():
    def make(
        *,
        thinking="thinking",
        action="do(action='Back')",
        parsed_action=None,
        raw_content="debug response",
    ):
        return ModelResponse(
            thinking=thinking,
            action=action,
            raw_content=raw_content,
            parsed_action=parsed_action,
        )

    return make


@pytest.fixture
def fake_model_client_factory():
    return lambda *results: FakeModelClient(*results)


@pytest.fixture
def fake_action_handler():
    return FakeActionHandler()


@pytest.fixture
def screenshot_factory():
    return lambda data: FakeScreenshot(base64_data=data)


@pytest.fixture
def image_urls():
    def collect(messages):
        urls = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if item.get("type") == "image_url":
                    urls.append(item["image_url"]["url"])
        return urls

    return collect
