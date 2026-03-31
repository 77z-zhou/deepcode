from pathlib import Path
import json

from deepcode.config.settings import Settings

DEFAULT_SETTINGS = {
    "env": {
        "MODEL_NAME": "",
        "MODEL_BASE_URL":"",
        "MODEL_API_KEY":""
    }
}

class ConfigLoader:
    def __init__(self, workspace: str):
        self.workspace = workspace
        self.root_dir = Path.home() / ".deepcode"  # 全局根目录
        self.project_dir = Path(workspace) / ".deepcode"

        self._init_root_dir()

    def _init_root_dir(self):
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.root_settings = self.root_dir / "settings.json"
        if not self.root_settings.exists():
            self.root_settings.write_text(json.dumps(DEFAULT_SETTINGS))
        if not self.project_dir.exists():
            self.project_dir.mkdir(parents=True, exist_ok=True)

    def load_config(self):
        root_json = json.loads(self.root_settings.read_text())
        env = root_json.get("env")

        setting_dict = {"workspace": self.workspace, 
                        "root_dir": str(self.root_dir), 
                        "project_dir": str(self.project_dir)}
        
        model_settings = self.model_convert(env)
        setting_dict["model"] = model_settings

        return Settings(**setting_dict)

    def model_convert(self, env: dict):
        model_name = env.get("MODEL_NAME")
        base_url = env.get("MODEL_BASE_URL")
        api_key = env.get("MODEL_API_KEY")
        return {"model_name": model_name, "base_url": base_url, "api_key": api_key}

def get_current_config():
    cwd = str(Path.cwd())
    loader = ConfigLoader(workspace=cwd)
    return loader.load_config()