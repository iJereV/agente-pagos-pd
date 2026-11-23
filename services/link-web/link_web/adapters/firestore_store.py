"""ChannelStore on the Firestore `channel` database; one transaction per sign-in."""

from google.cloud import firestore

from ..domain import (
    Accepted,
    ChannelSnapshot,
    LinkTokenRecord,
    Rejection,
    SignInRequest,
    customer_fields,
    decide,
    new_link_fields,
)


class FirestoreChannelStore:
    def __init__(self, client: firestore.Client) -> None:
        self._client = client

    def apply_sign_in(self, request: SignInRequest) -> Accepted | Rejection:
        return _apply_sign_in(self._client.transaction(), self._client, request)


@firestore.transactional
def _apply_sign_in(
    transaction: firestore.Transaction, client: firestore.Client, request: SignInRequest
) -> Accepted | Rejection:
    token_ref = client.collection("link_tokens").document(request.token_hash)
    link_ref = client.collection("wa_links").document(request.wa_id)
    customer_ref = client.collection("customers").document(request.uid)

    token_doc = token_ref.get(transaction=transaction)
    link_doc = link_ref.get(transaction=transaction)
    customer_doc = customer_ref.get(transaction=transaction)

    snapshot = ChannelSnapshot(
        token=_token_record(token_doc),
        linked_customer_id=link_doc.get("customer_id") if link_doc.exists else None,
        customer_wa_id=customer_doc.get("wa_id") if customer_doc.exists else None,
    )
    decision = decide(snapshot, request)
    if isinstance(decision, Rejection):
        return decision

    transaction.update(token_ref, {"used_at": request.now})
    if decision.create_link:
        transaction.create(link_ref, new_link_fields(request))
    transaction.set(customer_ref, customer_fields(request, decision), merge=True)
    return decision


def _token_record(doc: firestore.DocumentSnapshot) -> LinkTokenRecord | None:
    if not doc.exists:
        return None
    data = doc.to_dict() or {}
    return LinkTokenRecord(
        wa_id=data["wa_id"],
        purpose=data["purpose"],
        expires_at=data["expires_at"],
        used_at=data.get("used_at"),
    )
