import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import warnings

# 忽略 JWT 密钥长度警告
warnings.filterwarnings("ignore", category=UserWarning, message=".*HMAC key.*")


from deepcode.config.loader import get_current_config
from deepcode.core.agent import DeepCodeAgent

config = get_current_config()

agent = DeepCodeAgent(config)


async def main():

    print(await agent.ainvoke("你是谁", thread_id="1"))

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())