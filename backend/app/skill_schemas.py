from datetime import datetime

from pydantic import Field, field_validator

from app.schemas import StrictModel


class SkillWrite(StrictModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9-]{2,63}$")
    description: str = Field(min_length=1, max_length=500)
    instructions: str = Field(min_length=1, max_length=8000)
    tools: list[str] = Field(default_factory=list, max_length=30)
    enabled: bool = True

    @field_validator("tools")
    @classmethod
    def known_tools(cls, value):
        from app.agent_tools import TOOLS

        if set(value) - TOOLS.keys():
            raise ValueError("Skill 只能绑定工具目录中的系统工具")
        return list(dict.fromkeys(value))


class SkillView(SkillWrite):
    id: str
    builtin: bool
    created_at: datetime
    updated_at: datetime


class SkillStatus(StrictModel):
    enabled: bool
