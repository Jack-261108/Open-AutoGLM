#!/usr/bin/env python3
"""
Thinking Output Demo / 演示 thinking 输出的示例

This script demonstrates how the Agent outputs both thinking process and actions in verbose mode.
这个脚本展示了在 verbose 模式下，Agent 会同时输出思考过程和执行动作。

The configured model must support image input. For Anthropic or Ollama, use the
provider configurations shown in basic_usage.py; those alternatives are not run here.
"""

from phone_agent import PhoneAgent
from phone_agent.agent import AgentConfig
from phone_agent.config import get_messages
from phone_agent.model import ModelConfig


def main(lang: str = "cn"):
    msgs = get_messages(lang)

    print("=" * 60)
    print("Phone Agent - Thinking Demo")
    print("=" * 60)

    # Configure an OpenAI-compatible model (the default provider is openai)
    model_config = ModelConfig(
        provider="openai",
        base_url="http://localhost:8000/v1",
        model_name="autoglm-phone-9b",
        temperature=0.1,
    )

    # Configure Agent (verbose=True enables detailed output)
    agent_config = AgentConfig(
        max_steps=10,
        verbose=True,
        lang=lang,
    )

    # Create Agent
    agent = PhoneAgent(
        model_config=model_config,
        agent_config=agent_config,
    )

    try:
        # Execute task
        print(f"\n📱 {msgs['starting_task']}...\n")
        result = agent.run("打开小红书搜索美食攻略")

        print("\n" + "=" * 60)
        print(f"📊 {msgs['final_result']}: {result}")
        print("=" * 60)
    finally:
        agent.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phone Agent Thinking Demo")
    parser.add_argument(
        "--lang",
        type=str,
        default="cn",
        choices=["cn", "en"],
        help="Language for UI messages (cn=Chinese, en=English)",
    )
    args = parser.parse_args()

    main(lang=args.lang)
