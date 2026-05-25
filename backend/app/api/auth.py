"""Authenticated actor route handlers."""

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.schemas import CurrentActorView
from app.auth import CurrentActor, get_current_actor

ActorDep = Annotated[CurrentActor, Depends(get_current_actor)]

router = APIRouter(prefix="/auth", dependencies=[Depends(get_current_actor)])


@router.get("/me", response_model=CurrentActorView)
async def get_authenticated_actor(actor: ActorDep) -> CurrentActorView:
    """Return the server-verified actor projection used for scoped API access."""
    return CurrentActorView(
        actor_id=actor.actor_id,
        subject=actor.subject,
        auth_mode=actor.auth_mode,
        email=actor.email,
        workspace_id=actor.workspace_id,
        kb_scope_id=actor.kb_scope_id,
    )
