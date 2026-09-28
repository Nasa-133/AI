"""Composition root: provider tanlovi aniq; OpenAI xatosida fake’ga o‘tish yo‘q."""

import socket
from dataclasses import dataclass
from datetime import timedelta
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from ..adapters.fake_provider import FakeProvider
from ..adapters.hash_embedder import HashEmbedder
from ..adapters.http_tools import HttpBusinessTools
from ..adapters.openai_embedder import OpenAIEmbedder
from ..adapters.openai_provider import OpenAIResponsesProvider
from ..adapters.s3_store import S3ObjectStore
from ..adapters.sql_store import SqlRunStore
from ..adapters.tool_catalog import load_tool_specs
from ..application.runner import AgentRunner
from ..domain.pricing import Pricing
from ..ports.clock import SystemClock
from ..ports.embeddings import EmbeddingProvider
from ..ports.model import ModelProvider
from ..ports.tools import BusinessTools
from .settings import Settings


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    tools: HttpBusinessTools
    provider: ModelProvider
    embedder: EmbeddingProvider
    objects: S3ObjectStore


def make_provider(settings: Settings) -> ModelProvider:
    if settings.model_provider == "openai":
        return OpenAIResponsesProvider(api_key=settings.openai_api_key,
                                       model=settings.openai_model_main)
    return FakeProvider()


def make_embedder(settings: Settings) -> EmbeddingProvider:
    if settings.embedding_provider == "openai":
        return OpenAIEmbedder(api_key=settings.openai_api_key,
                              model=settings.openai_model_embedding,
                              dimensions=settings.embedding_dimensions)
    return HashEmbedder(settings.embedding_dimensions or 256)


def build_container(settings: Settings) -> Container:
    return Container(
        settings=settings,
        engine=create_async_engine(settings.database_url, pool_pre_ping=True),
        tools=HttpBusinessTools(base_url=settings.business_tools_url,
                                service_token=settings.business_tools_token),
        provider=make_provider(settings),
        embedder=make_embedder(settings),
        objects=S3ObjectStore(endpoint_url=settings.s3_endpoint_url,
                              access_key=settings.s3_access_key,
                              secret_key=settings.s3_secret_key, region=settings.s3_region),
    )


def make_runner(container: Container, *, tools: BusinessTools | None = None,
                owner: str | None = None) -> AgentRunner:
    return AgentRunner(
        store=SqlRunStore(container.engine),
        provider=container.provider,
        tools=tools or container.tools,
        tool_specs=load_tool_specs(),
        clock=SystemClock(),
        owner=owner or f"{socket.gethostname()}:{uuid4().hex[:8]}",
        lease=timedelta(seconds=container.settings.lease_seconds),
        pricing=Pricing(container.settings.price_input_per_1m,
                        container.settings.price_output_per_1m, container.settings.price_currency),
    )
