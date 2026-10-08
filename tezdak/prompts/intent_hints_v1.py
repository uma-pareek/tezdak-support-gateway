"""intent_hints_v1, the hint block the agent has used since launch."""

INTENT_HINTS_V1 = {
    "wismo": "Check the shipment (and scans if needed) and tell the customer where the parcel is.",
    "reschedule_request": "Book another attempt for the slot the customer asked for, unless the parcel is out of attempts.",
    "ndr_complaint": "Complaints about a missed or failed attempt go to a human: check the shipment, then escalate.",
    "not_received_after_delivered": "Delivered-but-not-received cases go to a human: check the shipment, then escalate.",
    "other": "Answer briefly and ask for the tracking number if you need it.",
}
