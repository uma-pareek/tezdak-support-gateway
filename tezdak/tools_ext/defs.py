"""Function-tool specs for the extra tools, same shape as the base tool specs."""

import copy


def _tool(name, description, properties, required):
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": {
            "type": "object", "properties": properties, "required": required,
            "additionalProperties": False,
        },
    }


_AWB = {"type": "string", "minLength": 3, "description": "Shipment AWB, for example TZ4829301"}
_PHONE = {"type": "string", "minLength": 10, "description": "Customer phone, digits with optional +91"}

TOOL_DEFS = {
    "get_order": _tool("get_order", "Order record for an AWB: seller, items, value, address.",
                       {"awb": _AWB}, ["awb"]),
    "update_address": _tool("update_address", "Replace the delivery address text on an order.",
                            {"awb": _AWB, "new_address": {"type": "string", "minLength": 10, "maxLength": 300},
                             "by": {"type": "string"}}, ["awb", "new_address"]),
    "cancel_order": _tool("cancel_order", "Cancel an order that has not left the hub.",
                          {"awb": _AWB, "by": {"type": "string"}}, ["awb"]),
    "create_ticket": _tool("create_ticket", "Open a support ticket for an AWB.",
                           {"awb": _AWB, "kind": {"type": "string", "minLength": 2},
                            "summary": {"type": "string", "minLength": 3, "maxLength": 500},
                            "priority": {"type": "string", "enum": ["low", "normal", "high"]}},
                           ["awb", "kind", "summary"]),
    "get_customer": _tool("get_customer", "Customer profile by phone number.", {"phone": _PHONE}, ["phone"]),
    "add_ticket_note": _tool("add_ticket_note", "Append a note to an existing ticket.",
                             {"ticket_id": {"type": "integer", "minimum": 1},
                              "text": {"type": "string", "minLength": 1, "maxLength": 1000},
                              "author": {"type": "string"}}, ["ticket_id", "text"]),
    "send_template_message": _tool("send_template_message",
                                   "Queue a pre-approved WhatsApp template message to the customer.",
                                   {"phone": _PHONE,
                                    "template": {"type": "string", "enum": [
                                        "delay_notice", "reschedule_confirm", "address_confirm", "feedback_ask"]},
                                    "params": {"type": "array", "items": {"type": "string"}}},
                                   ["phone", "template"]),
}


def tool_spec_list(names=None):
    """Deep copies of the specs, in definition order, optionally filtered by name."""
    wanted = set(names) if names is not None else None
    return [copy.deepcopy(s) for n, s in TOOL_DEFS.items() if wanted is None or n in wanted]


def schema_for(name):
    return TOOL_DEFS[name]["parameters"]
