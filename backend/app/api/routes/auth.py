from fastapi import APIRouter, Depends

from app.core.auth import AuthenticatedUser, require_authenticated_user

router = APIRouter(prefix="/auth")


@router.get("/me")
async def read_current_user(
    user: AuthenticatedUser = Depends(require_authenticated_user),
) -> dict[str, str | None]:
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
    }
