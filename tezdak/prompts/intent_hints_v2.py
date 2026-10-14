"""intent_hints_v2 (Sept). More intents, slightly longer. Used together with the nlu v2 taxonomy."""

INTENT_HINTS_V2 = {
    "wismo": "Check the shipment first. Give status and, if the carrier has one, the expected date. Keep it to three lines.",
    "reschedule_request": "Confirm the slot, book it, and repeat the date back. If attempts are used up, say so and offer a human.",
    "ndr_complaint": "The customer says a delivery attempt did not really happen. Check the shipment and the scans, then follow the case rules. Be calm, no blame on the rider.",
    "not_received_after_delivered": "Parcel shows delivered but the customer does not have it. Ask them to check with neighbours and family once, then escalate.",
    "address_change": "Address changes are only possible before the parcel is out for delivery. Check the status first.",
    "cancel_order": "Cancellation depends on the seller. Check the status; if it is out for delivery, do not promise.",
    "refund_status": "Look up the refund. Do not give a date you cannot see in the tools.",
    "feedback": "Thank the customer, note the feedback, do not argue.",
    "other": "Answer briefly. Ask for the AWB (it starts with TZ) if you need it.",
}
