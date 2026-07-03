from __future__ import annotations

from fastapi import APIRouter

from api.routers.webhooks import clerk

router = APIRouter()
router.include_router(clerk.router, prefix="/clerk", tags=["webhooks"])
