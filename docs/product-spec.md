# Product spec: Tezdak chat support assistant

Owner: Ritika (CX Operations). Engineering: Meera. Last edited 2026-10-14.

## Goal
Answer parcel questions on WhatsApp and in the app, and take the simple actions a support agent would, so that
human agents spend their time on cases that need a person.

## Channels
- WhatsApp (24 hour customer-service window). Replies are plain text, split when longer than 900 characters.
- In-app chat. Same agent, no splitting.
- Languages: English and Hinglish. Voice notes are accepted on WhatsApp; if the note cannot be read the customer is asked for text.

## Intents
| Intent | Example | What the assistant does |
|---|---|---|
| `wismo` | "Where is my parcel?" | Looks up the shipment and says where it is. |
| `reschedule_request` | "Deliver it tomorrow please" | Books another attempt if attempts are left. |
| `ndr_complaint` | "Rider aaya hi nahi" | Checks the shipment and hands the chat to a human. |
| `not_received_after_delivered` | "Shows delivered, I did not get it" | Checks the shipment and hands the chat to a human. |
| `other` | "Hi" | Short answer, asks for the tracking number. |

## Tools
`get_shipment`, `get_scans`, `reschedule`, `open_rider_dispute`, `create_refund` (refund or goodwill), `escalate`
(`agent_review` or `hub_override`), `close`.

## Rules of the world
- A parcel gets at most 3 delivery attempts. After that it goes back to the sender unless a hub manager approves another.
- Same-day slots close at 11:00 IST.
- Refunds and goodwill above the approval limit need a human. The limit is in the policy table (Rs 5000 in table v2).
- Refund window: 7 days from delivery (table v2).
- COD customers have no wallet. A COD payout goes by UPI, needs a UPI id, and costs Rs 6 in fees.
- The assistant never invents a delivery date. Every reply ends with an ETA line used for structured commitments.

## Service levels
See [slo.md](slo.md). Handing over to a human should include a short summary so the customer does not repeat themselves.

## Out of scope for 0.9
Multiple parcels in one chat, proactive delay messages, storing chat state outside the process.

## Open questions
- Should the assistant ever close a chat the customer has not confirmed? (Ritika: yes after 10 minutes of silence. Meera: unsure.)
- Do we show the carrier ticket id to customers? Not decided.
