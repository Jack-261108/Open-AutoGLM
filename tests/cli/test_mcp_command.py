"""Offline tests for the `phone-agent mcp` subcommand dispatch in main()."""

import pytest

import main as main_entry
import phone_agent.mcp_server as mcp_server

_REAL_RUN_MCP_COMMAND = mcp_server.run_mcp_command


class FakeConnection:
    @staticmethod
    def list_devices():
        return []


class FakeFactory:
    def get_connection_class(self):
        return FakeConnection

    def list_devices(self):
        return []


@pytest.fixture(autouse=True)
def mcp_must_not_start(monkeypatch):
    monkeypatch.setattr(
        mcp_server,
        "run_mcp_command",
        lambda args: pytest.fail("non-mcp invocation must not start the MCP server"),
    )


def test_mcp_subcommand_delegates(monkeypatch):
    received = {}
    monkeypatch.setattr(
        mcp_server, "run_mcp_command", lambda args: received.setdefault("args", args)
    )
    monkeypatch.setattr(
        main_entry,
        "ModelClient",
        lambda *a, **k: pytest.fail("mcp command must not create a model client"),
    )

    main_entry.main(["mcp", "--device-id", "dev1"])

    assert received["args"] == ["--device-id", "dev1"]


def test_regular_task_does_not_dispatch_to_mcp(monkeypatch):
    monkeypatch.setattr(main_entry, "set_device_type", lambda device_type: None)
    monkeypatch.setattr(main_entry, "get_device_factory", lambda: FakeFactory())
    monkeypatch.setattr(
        main_entry,
        "ModelClient",
        lambda *a, **k: pytest.fail("device list must not create a model client"),
    )

    # Any non-"mcp" first argument keeps the original CLI path.
    main_entry.main(["--list-devices"])


def test_run_mcp_command_parses_listen_and_transport(monkeypatch):
    monkeypatch.setattr(mcp_server, "_validate_environment", lambda did: "dev1")
    monkeypatch.setattr(mcp_server, "set_device_type", lambda dt: None)

    created = {}
    ran = {}

    class MockServer:
        def run(self, transport="stdio"):
            ran["transport"] = transport

    def fake_create_server(toolkit, host="127.0.0.1", port=8000):
        created["host"] = host
        created["port"] = port
        return MockServer()

    monkeypatch.setattr(mcp_server, "create_server", fake_create_server)

    # 1. Test --listen 0.0.0.0:8888 defaults to streamable-http
    res = _REAL_RUN_MCP_COMMAND(["--device-id", "dev1", "--listen", "0.0.0.0:8888"])
    assert res == 0
    assert created["host"] == "0.0.0.0"
    assert created["port"] == 8888
    assert ran["transport"] == "streamable-http"

    # 2. Test --transport sse --port 9000
    res = _REAL_RUN_MCP_COMMAND(
        ["--device-id", "dev1", "--transport", "sse", "--port", "9000"]
    )
    assert res == 0
    assert created["port"] == 9000
    assert ran["transport"] == "sse"


