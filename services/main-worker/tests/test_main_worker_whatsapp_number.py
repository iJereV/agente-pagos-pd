import pytest
from main_worker.adapters.whatsapp import outbound_number


@pytest.mark.parametrize(
    ("wa_id", "expected"),
    [
        ("5490000000001", "540000000001"),  # Argentina mobile: drop the 9
        ("5210000000001", "520000000001"),  # Mexico mobile: drop the 1
        ("540000000001", "540000000001"),  # already in outbound form
        ("15550000001", "15550000001"),  # other countries unchanged
    ],
)
def test_outbound_number(wa_id: str, expected: str) -> None:
    assert outbound_number(wa_id) == expected
