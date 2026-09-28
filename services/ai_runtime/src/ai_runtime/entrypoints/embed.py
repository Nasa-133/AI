"""POST /internal/v1/embed — Core → AI yagona sinxron chaqiruv (TZ 13.3): qidiruv so‘rovi vektori.

Servis tokeni bilan himoyalangan; brauzerga ochilmaydi.
"""

import secrets
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ..ports.embeddings import EmbeddingProvider, EmbeddingUnavailable

router = APIRouter(prefix="/internal/v1", tags=["internal"])


class EmbedIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    texts: list[Annotated[str, Field(min_length=1, max_length=4000)]] = Field(
        min_length=1, max_length=16)
    model_profile: Literal["embedding_default"]


def _authorize(request: Request, authorization: str | None) -> None:
    expected: str = request.app.state.service_token
    scheme, _, token = (authorization or "").partition(" ")
    if not expected or scheme.lower() != "bearer" or not secrets.compare_digest(
            token.encode(), expected.encode()):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Servis tokeni noto‘g‘ri")


@router.post("/embed")
async def embed(body: EmbedIn, request: Request,
                authorization: Annotated[str | None, Header()] = None) -> dict[str, Any]:
    _authorize(request, authorization)
    embedder: EmbeddingProvider = request.app.state.embedder
    try:
        vectors = await embedder.embed(body.texts)
    except EmbeddingUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"model": embedder.model, "dimensions": len(vectors[0]), "embeddings": vectors}
