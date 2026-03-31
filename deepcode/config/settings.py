from pydantic_settings import BaseSettings
from functools import cached_property

from pathlib import Path


class ModelSettings(BaseSettings):
    model_name: str
    base_url: str
    api_key: str

class AgentSettings(BaseSettings):
    ...

class Settings(BaseSettings):
    root_dir: str
    project_dir: str
    workspace: str
    model: ModelSettings
    recursion_limit: int = 1000

    @cached_property
    def cli_history_file(self) -> Path:  # 会话历史文件
        return Path(self.root_dir) / "cli_history.txt"
        

    
