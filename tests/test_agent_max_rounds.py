"""Tests for agent max tool rounds handling."""

import pytest
from unittest.mock import Mock, patch, MagicMock
import json

from llmproxy.cli_agent import Agent, SYSTEM_PROMPT


class TestMaxToolRounds:
    """Test the max tool rounds retry behavior."""
    
    @patch('llmproxy.cli_agent.OpenAI')
    @patch('llmproxy.cli_agent.console')
    def test_max_rounds_triggers_final_answer(self, mock_console, mock_openai):
        """When max rounds reached, should request final answer without tools."""
        # Setup mock client
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        # Create responses that always want to use tools (never gives final answer)
        tool_call_response = MagicMock()
        tool_call_response.choices = [MagicMock()]
        tool_call_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(name="read_file", arguments='{"path": "test.txt"}')
            )
        ]
        tool_call_response.choices[0].message.content = None
        tool_call_response.choices[0].finish_reason = "tool_calls"
        tool_call_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        
        # Final answer response (after max rounds)
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.tool_calls = None
        final_response.choices[0].message.content = "Final answer after max rounds"
        final_response.choices[0].finish_reason = "stop"
        final_response.usage = MagicMock(prompt_tokens=200, completion_tokens=100)
        
        # Client returns tool responses for first N calls, then final
        mock_client.chat.completions.create.side_effect = [
            tool_call_response,  # round 1
            tool_call_response,  # round 2
            tool_call_response,  # round 3
            final_response,      # final retry (after max rounds=3)
        ]
        
        # Create agent with small max rounds
        agent = Agent(
            base_url="http://localhost:8080/v1",
            api_key="test",
            model="test-model",
            max_tool_rounds=3,
        )
        
        # Mock execute_tool to return results
        with patch('llmproxy.cli_agent.execute_tool', return_value="file content"):
            result = agent.chat("Please read test.txt")
        
        # Should get final answer, not the error message
        assert result == "Final answer after max rounds"
        assert "(reached max tool rounds" not in result
        assert "(agent completed" not in result
    
    @patch('llmproxy.cli_agent.OpenAI')
    @patch('llmproxy.cli_agent.console')
    def test_max_rounds_adds_system_message(self, mock_console, mock_openai):
        """Should add system message when max rounds reached."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        # Always returns tool calls
        tool_response = MagicMock()
        tool_response.choices = [MagicMock()]
        tool_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(name="read_file", arguments='{"path": "test.txt"}')
            )
        ]
        tool_response.choices[0].message.content = None
        tool_response.choices[0].finish_reason = "tool_calls"
        tool_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.tool_calls = None
        final_response.choices[0].message.content = "Done"
        final_response.choices[0].finish_reason = "stop"
        final_response.usage = MagicMock(prompt_tokens=200, completion_tokens=100)
        
        mock_client.chat.completions.create.side_effect = [
            tool_response,
            final_response,
        ]
        
        agent = Agent(
            base_url="http://localhost:8080/v1",
            api_key="test",
            model="test-model",
            max_tool_rounds=1,  # Only 1 round
        )
        
        with patch('llmproxy.cli_agent.execute_tool', return_value="content"):
            agent.chat("Test")
        
        # Check that the final call was made without tools
        final_call = mock_client.chat.completions.create.call_args_list[-1]
        assert 'tools' not in final_call.kwargs or final_call.kwargs.get('tools') is None
        
        # Check that a system message was added
        messages = agent.messages
        system_messages = [m for m in messages if m.get("role") == "system"]
        assert len(system_messages) >= 2  # Original + max rounds message
        
        # Find the max rounds message
        max_rounds_msg = None
        for msg in system_messages:
            if "maximum number of tool calls" in msg.get("content", ""):
                max_rounds_msg = msg
                break
        
        assert max_rounds_msg is not None
        assert "provide a final answer" in max_rounds_msg["content"]
    
    @patch('llmproxy.cli_agent.OpenAI')
    @patch('llmproxy.cli_agent.console')
    def test_max_rounds_shows_warning(self, mock_console, mock_openai):
        """Should show warning message when max rounds reached."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        tool_response = MagicMock()
        tool_response.choices = [MagicMock()]
        tool_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(name="read_file", arguments='{}')
            )
        ]
        tool_response.choices[0].message.content = None
        tool_response.choices[0].finish_reason = "tool_calls"
        tool_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.tool_calls = None
        final_response.choices[0].message.content = "Done"
        final_response.usage = MagicMock(prompt_tokens=200, completion_tokens=100)
        
        mock_client.chat.completions.create.side_effect = [
            tool_response,
            final_response,
        ]
        
        agent = Agent(
            base_url="http://localhost:8080/v1",
            api_key="test",
            model="test-model",
            max_tool_rounds=1,
        )
        
        with patch('llmproxy.cli_agent.execute_tool', return_value="content"):
            agent.chat("Test")
        
        # Check that warning was printed
        mock_console.print.assert_any_call(
            "[yellow]Reached max tool rounds. Requesting final answer...[/yellow]"
        )
    
    @patch('llmproxy.cli_agent.OpenAI')
    @patch('llmproxy.cli_agent.console')
    def test_max_rounds_tracks_usage(self, mock_console, mock_openai):
        """Should track token usage for final answer call."""
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        
        tool_response = MagicMock()
        tool_response.choices = [MagicMock()]
        tool_response.choices[0].message.tool_calls = [
            MagicMock(
                id="call_1",
                function=MagicMock(name="read_file", arguments='{}')
            )
        ]
        tool_response.choices[0].message.content = None
        tool_response.choices[0].finish_reason = "tool_calls"
        tool_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)
        
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.tool_calls = None
        final_response.choices[0].message.content = "Done"
        final_response.usage = MagicMock(prompt_tokens=200, completion_tokens=100)
        
        mock_client.chat.completions.create.side_effect = [
            tool_response,
            final_response,
        ]
        
        agent = Agent(
            base_url="http://localhost:8080/v1",
            api_key="test",
            model="test-model",
            max_tool_rounds=1,
        )
        
        with patch('llmproxy.cli_agent.execute_tool', return_value="content"):
            agent.chat("Test")
        
        # Usage should include both calls
        assert agent.usage["input_tokens"] == 300  # 100 + 200
        assert agent.usage["output_tokens"] == 150  # 50 + 100
