import re
import yaml
from pathlib import Path
from typing import Annotated

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.tools import tool

from ._utils import append_to_system_message

SKILL_SYSTEM_PROMPT_TEMPLATE = """
## Skills System

You have access to a skills library that provides specialized capabilities and domain knowledge.

**Available Skills:**

{skills}

**How to Use Skills (Progressive Disclosure):**

Skills follow a **progressive disclosure** pattern - you see their name and description above, but only read full instructions when needed:

1. **Recognize when a skill applies**: Check if the user's task matches a skill's description
2. **Read the skill's full instructions**: Use the path shown in the skill list above
3. **Follow the skill's instructions**: SKILL.md contains step-by-step workflows, best practices, and examples
4. **Access supporting files**: Skills may include helper scripts, configs, or reference docs - use absolute paths

**When to Use Skills:**
- User's request matches a skill's domain (e.g., "research X" -> web-research skill)
- You need specialized knowledge or structured workflows
- A skill provides proven patterns for complex tasks

**Executing Skill Scripts:**
Skills may contain Python scripts or other executable files. Always use absolute paths from the skill list.

**Example Workflow:**

User: "Can you research the latest developments in quantum computing?"

1. Check available skills -> See "web-research" skill with its path
2. Read the skill using the path shown
3. Follow the skill's research workflow (search -> organize -> synthesize)
4. Use any helper scripts with absolute paths

Remember: Skills make you more capable and consistent. When in doubt, check if a skill exists for the task!
"""

LOAD_SKILL_TOOL_DESCRIPTION = """Load specialized knowledge by Skill name. 
Remember: You may only invoke `load_skill` when you actually need to use a specific skill."""

class SkillsMiddelware(AgentMiddleware):

    def __init__(self, skills_dir: Path):
        self.skills_dir = skills_dir
        self.skills = {}
        self._load_all()
        
        @tool(description=LOAD_SKILL_TOOL_DESCRIPTION)
        def load_skill(name: Annotated[str, "Skill name to load"]):
            skill = self.skills.get(name)
            if not skill:
                return f"Error: Unkown skill '{name}'. Available: {', '.join(self.skills.keys())}"
            return f"<skill name=\"{name}\">\n{skill['body']}\n</skill>"
        
        self.tools = [load_skill]
  
    def wrap_model_call(self, request: ModelRequest, handler):
        modified_request = self._modify_request(request)
        return handler(modified_request)
    
    async def awrap_model_call(self, request: ModelRequest, handler):
        modified_request = self._modify_request(request)
        return await handler(modified_request)

    def _modify_request(self, request: ModelRequest):
        if not self.skills:
            return request
        
        lines = []
        for name, skill in self.skills.items():
            meta = skill['meta']
            annotations = self._format_skill_annotations(meta)
            desc = meta.get("description", "No description")
            desc_line = f"- **{name}**: {desc}"
            if annotations:
                desc_line += f" ({annotations})"
            lines.append(desc_line)
            if meta["allowed_tools"]:
                lines.append(f"  -> Allowed tools: {', '.join(meta['allowed_tools'])}")
        skill_list = "\n".join(lines)
        skill_prompt = SKILL_SYSTEM_PROMPT_TEMPLATE.format(skills=skill_list)
        new_system_message = append_to_system_message(request.system_message, skill_prompt)
        return request.override(system_message=new_system_message)


    def _format_skill_annotations(self,meta) -> str:
        parts: list[str] = []
        if meta.get("license"):
            parts.append(f"License: {meta['license']}")
        if meta.get("compatibility"):
            parts.append(f"Compatibility: {meta['compatibility']}")
        return ", ".join(parts)


    def _load_all(self):
        if not self.skills_dir.exists():
            return 
        for f in sorted(self.skills_dir.rglob("SKILL.md")):
            text = f.read_text()
            meta, body = self._parse_frontmatter_metadata(text)
            name = meta.get("name", f.parent.name)
            self.skills[name] = {"meta": meta, "body": body, "path": str(f)}


    def _parse_frontmatter_metadata(self, text: str) -> tuple[dict, str]:
        frontmatter_pattern = r"^---\n(.*?)\n---\n(.*)"
        match = re.match(frontmatter_pattern, text, re.DOTALL)

        metadata = {}
        frontmatter_str = match.group(1)
        frontmatter_data = yaml.safe_load(frontmatter_str)
        metadata['name'] = str(frontmatter_data.get("name", "")).strip()
        metadata['description'] = str(frontmatter_data.get("description", "")).strip()

        raw_tools = frontmatter_data.get("allowed-tools")
        if isinstance(raw_tools, str):
            allowed_tools = [
                t.strip(",")
                for t in raw_tools.split()
                if t.strip(",")
            ]
        else:
            allowed_tools = []
        metadata['allowed_tools'] = allowed_tools
        metadata['license'] = str(frontmatter_data.get("license")).strip()
        metadata['compatibility'] = str(frontmatter_data.get("compatibility")).strip() or None
    
        body = match.group(2).strip()
        return metadata, body