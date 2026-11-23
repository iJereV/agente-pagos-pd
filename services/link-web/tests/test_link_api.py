from datetime import timedelta

from link_fakes import EMAIL, JTI, NOW, OTHER_UID, UID, WA_ID, FakePublisher
from link_web.domain import token_hash


def post(client, link_token: str, id_token: str = "google-id"):
    return client.post("/api/link", json={"link_token": link_token, "id_token": id_token})


def test_first_link_binds_number_and_publishes_event(client, store, publisher):
    store.add_token(JTI, "link")

    response = post(client, "link-token")

    assert response.status_code == 200
    assert response.json() == {"status": "linked"}
    assert store.wa_links[WA_ID] == {"customer_id": UID, "linked_at": NOW}
    assert store.customers[UID] == {
        "email": EMAIL,
        "wa_id": WA_ID,
        "linked_at": NOW,
        "last_sign_in_at": NOW,
    }
    assert store.link_tokens[token_hash(JTI)]["used_at"] == NOW
    assert publisher.published == [
        {
            "type": "system_event",
            "event": "sign_in_completed",
            "event_id": "evt-1",
            "wa_id": WA_ID,
            "timestamp": "2026-11-23T15:20:00Z",
            "data": {"customer_id": UID},
        }
    ]


def test_reauth_refreshes_sign_in_time_for_bound_account(client, store, publisher):
    earlier = NOW - timedelta(days=3)
    store.wa_links[WA_ID] = {"customer_id": UID, "linked_at": earlier}
    store.customers[UID] = {
        "email": EMAIL,
        "wa_id": WA_ID,
        "linked_at": earlier,
        "last_sign_in_at": earlier,
    }
    store.add_token(JTI, "reauth")

    response = post(client, "reauth-token")

    assert response.json() == {"status": "reauthenticated"}
    assert store.customers[UID]["last_sign_in_at"] == NOW
    assert store.customers[UID]["linked_at"] == earlier
    assert len(publisher.published) == 1


def test_reused_token_is_rejected(client, store, publisher):
    store.add_token(JTI, "link")
    post(client, "link-token")

    response = post(client, "link-token")

    assert response.status_code == 410
    assert response.json() == {"status": "token_used"}
    assert len(publisher.published) == 1


def test_expired_token_is_rejected(client, store, publisher):
    store.add_token(JTI, "link", expires_in=timedelta(seconds=-1))

    response = post(client, "link-token")

    assert response.status_code == 410
    assert response.json() == {"status": "token_expired"}
    assert store.wa_links == {}
    assert publisher.published == []


def test_link_token_past_its_jwt_expiry_is_gone(client, store, publisher):
    response = post(client, "expired-link-token")

    assert response.status_code == 410
    assert response.json() == {"status": "token_expired"}
    assert publisher.published == []


def test_reauth_with_a_different_account_is_rejected_and_keeps_token(client, store, publisher):
    store.wa_links[WA_ID] = {"customer_id": UID, "linked_at": NOW}
    store.add_token(JTI, "reauth")

    response = post(client, "reauth-token", "other-google-id")

    assert response.status_code == 409
    assert response.json() == {"status": "account_mismatch"}
    assert store.link_tokens[token_hash(JTI)]["used_at"] is None
    assert OTHER_UID not in store.customers
    assert publisher.published == []


def test_number_already_linked_to_another_account_is_rejected(client, store, publisher):
    store.wa_links[WA_ID] = {"customer_id": OTHER_UID, "linked_at": NOW}
    store.add_token(JTI, "link")

    response = post(client, "link-token")

    assert response.status_code == 409
    assert response.json() == {"status": "number_linked_to_other_account"}
    assert store.wa_links[WA_ID]["customer_id"] == OTHER_UID
    assert publisher.published == []


def test_account_already_linked_to_another_number_is_rejected(client, store):
    store.customers[UID] = {"email": EMAIL, "wa_id": "5490000000999"}
    store.add_token(JTI, "link")

    response = post(client, "link-token")

    assert response.json() == {"status": "account_linked_to_other_number"}
    assert store.wa_links == {}


def test_unknown_token_record_is_rejected(client):
    assert post(client, "link-token").json() == {"status": "token_not_found"}


def test_invalid_link_token_signature_is_rejected(client):
    response = post(client, "forged-token")

    assert response.status_code == 400
    assert response.json() == {"status": "invalid_link"}


def test_invalid_identity_does_not_burn_the_token(client, store):
    store.add_token(JTI, "link")

    response = post(client, "link-token", "forged-id-token")

    assert response.status_code == 401
    assert store.link_tokens[token_hash(JTI)]["used_at"] is None


def test_non_google_sign_in_is_rejected(client, store):
    store.add_token(JTI, "link")

    response = post(client, "link-token", "password-id")

    assert response.status_code == 403
    assert response.json() == {"status": "google_account_required"}


def test_publish_failure_still_reports_success(make_client, store):
    store.add_token(JTI, "link")

    response = post(make_client(FakePublisher(fail=True)), "link-token")

    assert response.status_code == 200
    assert store.wa_links[WA_ID]["customer_id"] == UID
