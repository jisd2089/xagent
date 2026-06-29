from unittest.mock import patch

import pytest

from xagent.core.tools.adapters.vibe.api_tool_adapter import (
    CustomApiTool,
    create_custom_api_tools,
)


def test_custom_api_tool_init():
    tool = CustomApiTool(
        name="my-test api",
        description="A test API",
        env={"API_KEY": "secret123", "API_KEY_BACKUP": "secret456"},
        url="https://api.example.com/hello",
        method="POST",
        headers={"Authorization": "Bearer $API_KEY"},
    )

    assert tool.name == "api_my_test_api_call"
    # Structured originating-server identity, normalized once via the SSOT,
    # so a scoped mcp:<server> selector matches this wrapper by equality.
    assert tool.source_server == "my_test_api"
    assert tool.metadata.source_server == "my_test_api"
    assert "A test API" in tool.description
    assert "Configured endpoint: https://api.example.com/hello" in tool.description
    assert "Configured method: POST" in tool.description
    assert "- API_KEY" in tool.description
    assert "- API_KEY_BACKUP" in tool.description


def test_custom_api_tool_replace_secrets():
    # Use unencrypted secrets for simplicity since decrypt_value handles unencrypted fallback or we can mock it
    # We will mock decrypt_value to just return the value for testing replace
    with patch(
        "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
        side_effect=lambda x: x,
    ):
        tool = CustomApiTool(
            name="test",
            description="test",
            env={"API_KEY": "secret123", "API_KEY_BACKUP": "secret456"},
        )

        # Test word boundaries
        result = tool._replace_secrets("Bearer $API_KEY")
        assert result == "Bearer secret123"

        # Test word boundaries avoiding partial replacement
        result2 = tool._replace_secrets("Bearer $API_KEY_BACKUP")
        assert result2 == "Bearer secret456"

        # Test bracket notation
        result3 = tool._replace_secrets("Bearer ${API_KEY}")
        assert result3 == "Bearer secret123"

        # Test recursive
        dict_val = {
            "url": "http://example.com?key=$API_KEY",
            "headers": {"Authorization": "Bearer ${API_KEY_BACKUP}"},
            "list": ["$API_KEY", "normal"],
        }
        res_dict = tool._replace_secrets(dict_val)
        assert res_dict["url"] == "http://example.com?key=secret123"
        assert res_dict["headers"]["Authorization"] == "Bearer secret456"
        assert res_dict["list"] == ["secret123", "normal"]


@pytest.mark.asyncio
async def test_run_json_async():
    with (
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
            side_effect=lambda x: x,
        ),
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.call_api"
        ) as mock_call_api,
    ):
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "headers": {},
            "body": {"data": "test"},
            "error": None,
        }

        tool = CustomApiTool(name="test", description="test", env={"KEY": "val"})

        args = {"url": "http://test.com/$KEY", "method": "GET"}

        res = await tool.run_json_async(args)
        assert res["success"] is True
        assert res["status_code"] == 200
        assert res["body"] == {"data": "test"}

        mock_call_api.assert_called_once_with(
            url="http://test.com/val", method="GET", headers={}, params={}, body=None
        )


@pytest.mark.asyncio
async def test_run_json_async_uses_configured_endpoint_defaults():
    with (
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
            side_effect=lambda x: x,
        ),
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.call_api"
        ) as mock_call_api,
    ):
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "headers": {},
            "body": {"data": "test"},
            "error": None,
        }

        tool = CustomApiTool(
            name="HelloAPI",
            description="test",
            env={"TOKEN": "secret"},
            url="https://api.example.com/hello",
            method="POST",
            headers={"Authorization": "Bearer $TOKEN"},
        )

        res = await tool.run_json_async({"body": {"name": "Ada"}})
        assert res["success"] is True

        mock_call_api.assert_called_once_with(
            url="https://api.example.com/hello",
            method="POST",
            headers={"Authorization": "Bearer secret"},
            params={},
            body={"name": "Ada"},
        )


@pytest.mark.asyncio
async def test_run_json_async_passes_timeout_and_retry_count_when_requested():
    with (
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
            side_effect=lambda x: x,
        ),
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.call_api"
        ) as mock_call_api,
    ):
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "headers": {},
            "body": {"data": "test"},
            "error": None,
        }

        tool = CustomApiTool(
            name="LongRunningAPI",
            description="test",
            env={},
            url="https://api.example.com/long-running",
            method="POST",
        )

        res = await tool.run_json_async(
            {"body": {"name": "Ada"}, "timeout": 180, "retry_count": 0}
        )
        assert res["success"] is True

        mock_call_api.assert_called_once_with(
            url="https://api.example.com/long-running",
            method="POST",
            headers={},
            params={},
            body={"name": "Ada"},
            timeout=180,
            retry_count=0,
        )


@pytest.mark.asyncio
async def test_run_json_async_merges_configured_and_call_headers():
    with (
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
            side_effect=lambda x: x,
        ),
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.call_api"
        ) as mock_call_api,
    ):
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "headers": {},
            "body": {"data": "test"},
            "error": None,
        }

        tool = CustomApiTool(
            name="HelloAPI",
            description="test",
            env={"TOKEN": "secret"},
            url="https://api.example.com/hello",
            headers={
                "Authorization": "Bearer $TOKEN",
                "X-Default": "1",
                "X-Override": "default",
            },
        )

        res = await tool.run_json_async(
            {"headers": {"X-Custom": "2", "X-Override": "caller"}}
        )
        assert res["success"] is True

        mock_call_api.assert_called_once_with(
            url="https://api.example.com/hello",
            method="GET",
            headers={
                "Authorization": "Bearer secret",
                "X-Default": "1",
                "X-Custom": "2",
                "X-Override": "caller",
            },
            params={},
            body=None,
        )


@pytest.mark.asyncio
async def test_run_json_async_merges_configured_and_call_body():
    with (
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
            side_effect=lambda x: x,
        ),
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.call_api"
        ) as mock_call_api,
    ):
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "headers": {},
            "body": {"data": "test"},
            "error": None,
        }

        tool = CustomApiTool(
            name="AIHubWorkflow",
            description="Invoke a 53AIHub workflow agent",
            env={"AIHUB_TOKEN": "secret", "TRACE_ID": "trace-default"},
            url="https://aihub.example.com/v1/workflow/run",
            method="POST",
            headers={"Authorization": "Bearer $AIHUB_TOKEN"},
            body=(
                '{"model":"agent-13","stream":false,'
                '"parameters":{"trace_id":"$TRACE_ID"}}'
            ),
        )

        res = await tool.run_json_async(
            {
                "body": {
                    "conversation_id": 619,
                    "parameters": {
                        "resume_file_id": "file_id:175",
                        "trace_id": "trace-runtime",
                    },
                }
            }
        )
        assert res["success"] is True

        mock_call_api.assert_called_once_with(
            url="https://aihub.example.com/v1/workflow/run",
            method="POST",
            headers={"Authorization": "Bearer secret"},
            params={},
            body={
                "model": "agent-13",
                "stream": False,
                "conversation_id": 619,
                "parameters": {
                    "trace_id": "trace-runtime",
                    "resume_file_id": "file_id:175",
                },
            },
        )


@pytest.mark.asyncio
async def test_run_json_async_supports_configured_coze_stream_workflow_body():
    with (
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.decrypt_value",
            side_effect=lambda x: x,
        ),
        patch(
            "xagent.core.tools.adapters.vibe.api_tool_adapter.call_api"
        ) as mock_call_api,
    ):
        mock_call_api.return_value = {
            "success": True,
            "status_code": 200,
            "headers": {"content-type": "text/event-stream"},
            "body": "event:Done\ndata:{}",
            "error": None,
        }

        tool = CustomApiTool(
            name="Coze Stream Workflow",
            description="Invoke a Coze workflow with the configured request body",
            env={"COZE_TOKEN": "secret"},
            url="https://api.coze.cn/v1/workflow/stream_run",
            method="POST",
            headers={
                "Authorization": "Bearer $COZE_TOKEN",
                "Content-Type": "application/json",
            },
            body=(
                '{"workflow_id":"7648982443038703656",'
                '"app_id":"7648929438155210767",'
                '"parameters":{'
                '"chengshi_in":"上海",'
                '"guihua_fangxiang":"AI大模型",'
                '"input":"https://p9-bot-workflow-sign.byteimg.com/tos-cn-i-mdko3gqilj/35a502eb00fa411da13bbcc8ab472df2.pdf~tplv-mdko3gqilj-image.image?rk3s=81d4c505&x-expires=1812022967&x-signature=bjYJK1hLorUemG2xziNsezuJK9k%3D&x-wf-file_name=21%E5%B1%8A++%E5%BC%A0%E6%81%BA%E6%98%8E+%E4%B8%AA%E4%BA%BA%E7%AE%80%E5%8E%86.pdf",'
                '"mubiao_gangwei":"AI产品经理",'
                '"xinzi_in":"10k"'
                "}}"
            ),
        )

        res = await tool.run_json_async({})
        assert res["success"] is True

        mock_call_api.assert_called_once_with(
            url="https://api.coze.cn/v1/workflow/stream_run",
            method="POST",
            headers={
                "Authorization": "Bearer secret",
                "Content-Type": "application/json",
            },
            params={},
            body={
                "workflow_id": "7648982443038703656",
                "app_id": "7648929438155210767",
                "parameters": {
                    "chengshi_in": "上海",
                    "guihua_fangxiang": "AI大模型",
                    "input": "https://p9-bot-workflow-sign.byteimg.com/tos-cn-i-mdko3gqilj/35a502eb00fa411da13bbcc8ab472df2.pdf~tplv-mdko3gqilj-image.image?rk3s=81d4c505&x-expires=1812022967&x-signature=bjYJK1hLorUemG2xziNsezuJK9k%3D&x-wf-file_name=21%E5%B1%8A++%E5%BC%A0%E6%81%BA%E6%98%8E+%E4%B8%AA%E4%BA%BA%E7%AE%80%E5%8E%86.pdf",
                    "mubiao_gangwei": "AI产品经理",
                    "xinzi_in": "10k",
                },
            },
        )


@pytest.mark.asyncio
async def test_run_json_async_returns_error_without_any_url():
    tool = CustomApiTool(name="test", description="test", env={})

    res = await tool.run_json_async({})

    assert res["success"] is False
    assert "URL is required" in res["error"]


def test_run_json_sync_raises_runtime_error():
    tool = CustomApiTool(name="test", description="test", env={})

    # Since pytest-asyncio runs tests in an event loop if marked with @pytest.mark.asyncio
    # We can test that calling the sync version raises an error when a loop is running
    async def inner():
        with pytest.raises(RuntimeError, match="Event loop is already running"):
            tool.run_json_sync({"url": "http://test", "method": "GET"})

    import asyncio

    asyncio.run(inner())


def test_create_custom_api_tools():
    configs = [
        {
            "name": "api1",
            "description": "desc1",
            "env": {"k1": "v1"},
            "url": "https://api.example.com/api1",
            "method": "POST",
            "headers": {"X-Key": "$k1"},
        },
        {"name": "api2", "description": "desc2", "env": {"k2": "v2"}},
    ]
    tools = create_custom_api_tools(configs)
    assert len(tools) == 2
    assert tools[0].name == "api_api1_call"
    assert tools[1].name == "api_api2_call"
    assert "Configured endpoint: https://api.example.com/api1" in tools[0].description
