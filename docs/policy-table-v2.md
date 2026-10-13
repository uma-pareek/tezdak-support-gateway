# Ops policy table v2

Maintained by support ops (Sunil). Values here are what the `PolicyV2` class in `tezdak/policy/v2_table.py` carries.
Changes go in the table, not in a release.

## Defaults
| Setting | Value |
|---|---|
| Refund window | 7 days from delivery |
| Human approval above | Rs 5000 |
| Goodwill cap | Rs 200 |

## Categories
| Category | Window (days) | Approval above (Rs) |
|---|---|---|
| electronics | 7 | 5000 |
| apparel | 7 | 5000 |
| grocery | 2 | 5000 |
| books | 7 | 5000 |

## Seller exceptions
| Seller | Override |
|---|---|
| SELLER-FASHIONKART | window 10 days |
| SELLER-GADGETHUB | approval above Rs 8000 |
| SELLER-BULKMART | window 3 days, approval above Rs 3000 |

## Change log
- 2026-04: first table version, defaults only.
- 2026-06: seller exceptions.
- 2026-09: `bulk_seller` entry added by support ops.
