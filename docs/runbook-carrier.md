# Carrier API reference

Copied from the carrier's integration guide (v3.2) on 2026-10-09, trimmed to what we call. Times are IST.
In this repo the simulator in `carrier_sim` implements the same methods.

## Conventions
- All calls take a timeout in seconds. Our client default is 8.
- Errors come back as `{"error": "<CODE>"}`. Codes seen: `NOT_FOUND`, `NOT_RESCHEDULABLE`, `INVALID_SLOT`,
  `INVALID_KIND`, `INVALID_AMOUNT`, `VPA_REQUIRED`.

## Endpoints

### get_shipment(awb)
Returns `awb`, `status`, `attempts_used`, `payment_mode` (`PREPAID` or `COD`), `amount_inr`, `pincode`, `tier`
(`metro` or `tier2`), `phone`, `otp_required`.

### get_scans(awb)
Returns the scan history, oldest first. Each scan has:

| Field | Meaning |
|---|---|
| `ts` | Time the scan was recorded. |
| `status` | Machine status, for example `IN_TRANSIT`, `OUT_FOR_DELIVERY`, `NDR`, `DELIVERED`. |
| `status_text` | Text shown to the customer. |
| `hub_id` | Hub that handled the parcel. |
| `ofd_ts` | Time the parcel went out for delivery on this run. |
| `attempt_n` | Attempt number the scan belongs to; 0 before the first run. |
| `otp_verified` | True when the customer's delivery code was entered. |
| `ev` | Optional event detail object, present on some scans. Keys `loc` (coordinates of the scan) and `cl` (`attempted`, `dur_s`: whether a call was placed and for how many seconds). |

### reschedule(awb, slot, client\_ref=None)
Books another delivery attempt. `slot` is `today`, `tomorrow` or an ISO date. Same-day slots close at 11:00.
`client\_ref` is an optional string supplied by the caller and recorded with the booking.
Success returns `status`, `state`, `slot_booked`, `attempts_used`. A parcel that has used 3 attempts goes to return-to-origin.

### open_rider_dispute(awb, reason)
Opens a dispute against the rider's attempt. Returns `ticket_id` and `status`.

### create_refund(awb, amount_inr, kind, vpa=None)
`kind` is `refund` or `goodwill`. Prepaid orders are credited to the wallet (no fee, reversible).
COD orders are paid by UPI and need `vpa`: fee Rs 6, not reversible. Returns `refund_id`, `mode`, `fee_inr`, `reversible`.

### escalate(awb, reason, kind)
`kind` is `agent_review` or `hub_override`. A `hub_override` on a parcel with 3 attempts used allows one more attempt.
Returns `ticket_id`, `status`, `attempt_extension`.

### close(awb, resolution)
Marks the conversation closed. Returns `status`.

## Support contact
Carrier integrations desk, weekdays 09:00 to 19:00.
