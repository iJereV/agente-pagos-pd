"""What every receipt-extraction model is asked for, and the shape it must answer in."""

from pydantic import BaseModel

PROMPT = """\
You read one image that a customer sent as proof of a bank transfer in Argentina.
Set is_receipt to false if the image is not a transfer receipt.
Copy every other field exactly as printed. Do not compute, convert or reformat anything.
Leave a field null when it is not printed or not legible. Never guess.
- coelsa_id: the COELSA / transfer id (may be labelled "ID COELSA", "Código de transacción").
- amount_text: the transferred amount with its symbol and separators, e.g. "$ 2.166,35".
- datetime_local_text: the date and time of the transfer as printed.
- origin_cuit: the CUIT/CUIL of the person or company that sent the money.
- destination_cvu: the CVU or CBU that received the money.
- bank_name: the bank or wallet that issued the receipt.
"""


class ReceiptFields(BaseModel):
    is_receipt: bool
    coelsa_id: str | None = None
    amount_text: str | None = None
    datetime_local_text: str | None = None
    origin_cuit: str | None = None
    destination_cvu: str | None = None
    bank_name: str | None = None
