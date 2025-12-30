import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import json
import sys
import os

# Ensure src is in path
sys.path.append(os.getcwd())

# Mocking external dependencies
mock_db = MagicMock()
# Ensure get_all_speakers_memory returns an empty dict for now, but is awaitable
mock_db.get_all_speakers_memory = AsyncMock(return_value={})
mock_db.is_llm_enabled = AsyncMock(return_value=True)

mock_llm_response = MagicMock()
mock_choice = MagicMock()
mock_message = MagicMock()
mock_message.content = "你好呀！我是琪露诺~"
mock_message.tool_calls = None
mock_choice.message = mock_message
mock_llm_response.choices = [mock_choice]

async def test_bot_response_flow():
    print("Testing Bot Response Flow...")
    # Use AsyncMock for the return of completions.create
    with patch("openai.resources.chat.completions.AsyncCompletions.create", new_callable=AsyncMock) as mock_create:
        mock_create.return_value = mock_llm_response
        
        from src.ai.llm_service import LLMService
        from src.config import config
        
        # Setup config for testing
        config.llm.api_key = "test_key"
        
        service = LLMService()
        await service.set_db(mock_db)
        
        chat_history = [
            {"role": "user", "content": "你好", "sender_name": "测试用户", "sender_id": 123456}
        ]
        
        responses = await service.generate_chat_response(chat_history)
        
        print(f"Bot responses: {responses}")
        assert len(responses) > 0
        print("Bot response flow test passed!")

async def test_command_system():
    print("Testing Command System...")
    from src.bot.command_system import command_system
    
    # Test a simple command like $$ping
    # FIXED: removed double curly braces
    result = await command_system.parse_and_execute("$$ping", 123, 456, {})
    
    assert result is not None
    assert result.success is True
    print(f"Command response: {result.response}")
    print("Command system test passed!")

async def main():
    try:
        await test_bot_response_flow()
        await test_command_system()
        print("\nAll tests completed successfully!")
    except Exception as e:
        print(f"\nTest failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())