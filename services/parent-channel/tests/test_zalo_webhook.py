import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mentor_parent_channel import SECRET_HEADER, ParentLinkService, create_webhook_router
from zalo_fakes import FakeZalo, InMemoryStore, text_update

SECRET = "webhook-secret-123"


@pytest.fixture
def http(service: ParentLinkService) -> TestClient:
    app = FastAPI()
    app.include_router(create_webhook_router(service, SECRET))
    return TestClient(app)


def test_webhook_rejects_missing_or_wrong_secret(http: TestClient, zalo: FakeZalo) -> None:
    assert http.post("/webhooks/zalo", json=text_update("hi")).status_code == 403
    r = http.post("/webhooks/zalo", json=text_update("hi"), headers={SECRET_HEADER: "wrong-secret"})
    assert r.status_code == 403 and r.json() == {"message": "Unauthorized"}
    assert zalo.calls == []


def test_webhook_links_parent_and_ignores_duplicate(
    http: TestClient, service: ParentLinkService, store: InMemoryStore, zalo: FakeZalo
) -> None:
    code = service.start_link("stu-1").link_code
    update = text_update(code, message_id="zalo-msg-1")
    for _ in range(2):
        r = http.post("/webhooks/zalo", json=update, headers={SECRET_HEADER.lower(): SECRET})
        assert r.status_code == 200 and r.json() == {"ok": True}
    assert store.get_by_student("stu-1").status == "awaiting_consent"
    assert len(zalo.sent()) == 1


def test_webhook_bad_body(http: TestClient) -> None:
    headers = {SECRET_HEADER: SECRET, "content-type": "application/json"}
    assert http.post("/webhooks/zalo", content=b"not json", headers=headers).status_code == 400
    assert http.post("/webhooks/zalo", json=[1, 2], headers={SECRET_HEADER: SECRET}).status_code == 400


def test_router_requires_valid_secret(service: ParentLinkService) -> None:
    with pytest.raises(ValueError):
        create_webhook_router(service, "short")
