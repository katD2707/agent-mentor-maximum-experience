import httpx
import pytest
from mentor_parent_channel import ParentLinkService, ZaloBotClient
from zalo_fakes import BASE, TOKEN, Clock, FakeZalo, InMemoryStore


@pytest.fixture
def zalo() -> FakeZalo:
    return FakeZalo()


@pytest.fixture
def client(zalo: FakeZalo) -> ZaloBotClient:
    return ZaloBotClient(TOKEN, base_url=BASE, transport=httpx.MockTransport(zalo))


@pytest.fixture
def store() -> InMemoryStore:
    return InMemoryStore()


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def service(store: InMemoryStore, client: ZaloBotClient, clock: Clock) -> ParentLinkService:
    return ParentLinkService(store, client, "Mentor Bot", now=clock)
