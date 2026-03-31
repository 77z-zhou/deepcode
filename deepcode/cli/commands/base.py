from abc import ABC, abstractmethod
from typing import List, Dict, Any


class Command(ABC):
    name: str = ""
    description: str = ""
    aliases: List[str] = []

    @abstractmethod
    def execute(self, args: List[str], context: Dict[str, Any]) -> str:
        pass

    def get_help(self) -> str:
        return f"/{self.name} - {self.description}"
