from langchain.chat_models import init_chat_model
from langchain_openai import ChatOpenAI
from deepcode.config.settings import ModelSettings


def _create_openai_model(model_name: str, api_key: str, base_url: str):
    return ChatOpenAI(
        model=model_name,
        api_key=api_key,
        base_url=base_url
    )

def create_model(config: ModelSettings):

    model_name = config.model_name
    api_key = config.api_key
    base_url = config.base_url

    return _create_openai_model(model_name, api_key, base_url)
