from functools import lru_cache
from importlib.resources import files

import yaml
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import commit, get_db
from app.deps import current_user
from app.models import Skill, User
from app.schemas import Page
from app.skill_schemas import SkillStatus, SkillView, SkillWrite

router = APIRouter(prefix="/api/skills", tags=["Skill 管理"])


@lru_cache
def builtin_skills() -> dict[str, dict]:
    result = {}
    for directory in files("app").joinpath("builtin_skills").iterdir():
        path = directory.joinpath("SKILL.md")
        if not path.is_file():
            continue
        _, metadata, instructions = path.read_text(encoding="utf-8").split("---", 2)
        spec = yaml.safe_load(metadata)
        result[spec["name"]] = {**spec, "instructions": instructions.strip(), "enabled": True}
    return result


def skill_view(skill: Skill) -> dict:
    return {
        key: getattr(skill, key)
        for key in (
            "id",
            "name",
            "description",
            "instructions",
            "tools",
            "builtin",
            "enabled",
            "created_at",
            "updated_at",
        )
    }


async def ensure_skills(db: AsyncSession, user: User) -> None:
    existing = set(await db.scalars(select(Skill.name).where(Skill.user_id == user.id)))
    for name, spec in builtin_skills().items():
        if name not in existing:
            try:
                async with db.begin_nested():
                    db.add(Skill(user_id=user.id, builtin=True, **spec))
                    await db.flush()
            except IntegrityError:
                # Another request seeded the same user's builtins concurrently.
                pass
    if set(builtin_skills()) - existing:
        await commit(db)


async def owned_skill(skill_id: str, user: User, db: AsyncSession, lock: bool = False) -> Skill:
    query = select(Skill).where(Skill.id == skill_id, Skill.user_id == user.id)
    if lock:
        query = query.with_for_update()
    skill = await db.scalar(query.execution_options(populate_existing=True))
    if skill is None:
        raise HTTPException(404, "Skill 不存在")
    return skill


@router.get("", response_model=Page[SkillView])
async def list_skills(
    q: str = Query("", max_length=100),
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    await ensure_skills(db, user)
    conditions = [Skill.user_id == user.id]
    if q:
        conditions.append(Skill.name.contains(q, autoescape=True))
    rows = await db.scalars(
        select(Skill).where(*conditions).order_by(Skill.builtin.desc(), Skill.name)
    )
    items = [skill_view(row) for row in rows]
    return {"items": items, "total": len(items)}


@router.get("/tools")
async def tool_catalog(user: User = Depends(current_user)):
    from app.agent_tools import TOOLS

    return {
        "items": [
            {
                "name": name,
                "description": tool.description,
                "mutation": tool.mutation,
                "parameters": tool.schema.model_json_schema(),
                "secret_fields": tool.secret_fields,
            }
            for name, tool in TOOLS.items()
        ]
    }


@router.post("", response_model=SkillView, status_code=201)
async def create_skill(
    body: SkillWrite, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    if body.name in builtin_skills():
        raise HTTPException(409, "该名称属于内置 Skill")
    count = await db.scalar(select(func.count()).select_from(Skill).where(Skill.user_id == user.id))
    if count >= 100:
        raise HTTPException(409, "每个用户最多 100 个 Skill")
    if await db.scalar(select(Skill.id).where(Skill.user_id == user.id, Skill.name == body.name)):
        raise HTTPException(409, "Skill 名称已存在")
    skill = Skill(user_id=user.id, builtin=False, **body.model_dump())
    try:
        async with db.begin_nested():
            db.add(skill)
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Skill 名称已存在") from None
    await commit(db)
    return skill_view(skill)


@router.get("/{skill_id}", response_model=SkillView)
async def get_skill(
    skill_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    return skill_view(await owned_skill(skill_id, user, db))


@router.put("/{skill_id}", response_model=SkillView)
async def update_skill(
    skill_id: str,
    body: SkillWrite,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    skill = await owned_skill(skill_id, user, db)
    if (skill.builtin and body.name != skill.name) or (
        not skill.builtin and body.name in builtin_skills()
    ):
        raise HTTPException(409, "内置 Skill 不能改名，自定义 Skill 不能占用内置名称")
    try:
        async with db.begin_nested():
            for key, value in body.model_dump().items():
                setattr(skill, key, value)
            await db.flush()
    except IntegrityError:
        raise HTTPException(409, "Skill 名称已存在") from None
    await commit(db)
    return skill_view(skill)


@router.patch("/{skill_id}", response_model=SkillView)
async def set_skill_status(
    skill_id: str,
    body: SkillStatus,
    user: User = Depends(current_user),
    db: AsyncSession = Depends(get_db),
):
    skill = await owned_skill(skill_id, user, db)
    skill.enabled = body.enabled
    await commit(db)
    return skill_view(skill)


@router.delete("/{skill_id}", status_code=204)
async def delete_skill(
    skill_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    skill = await owned_skill(skill_id, user, db)
    if skill.builtin:
        raise HTTPException(409, "内置 Skill 可停用或恢复默认，不能删除")
    await db.delete(skill)
    await commit(db)


@router.post("/{skill_id}/reset", response_model=SkillView)
async def reset_skill(
    skill_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    skill = await owned_skill(skill_id, user, db)
    if not skill.builtin:
        raise HTTPException(409, "仅内置 Skill 支持恢复默认")
    for key, value in builtin_skills()[skill.name].items():
        setattr(skill, key, value)
    await commit(db)
    return skill_view(skill)


@router.get("/{skill_id}/export")
async def export_skill(
    skill_id: str, user: User = Depends(current_user), db: AsyncSession = Depends(get_db)
):
    skill = await owned_skill(skill_id, user, db)
    meta = yaml.safe_dump(
        {"name": skill.name, "description": skill.description, "tools": skill.tools},
        allow_unicode=True,
        sort_keys=False,
    )
    return Response(
        f"---\n{meta}---\n\n{skill.instructions}\n",
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{skill.name}-SKILL.md"'},
    )
