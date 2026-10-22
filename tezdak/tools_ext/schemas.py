"""Tiny JSON-schema subset validator.

Supported keywords: type (string, integer, number, boolean, object, array), required, properties,
enum, minLength, maxLength, minimum, maximum, items, additionalProperties (bool only).
"""

_TYPES = {
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
}


class SchemaError(ValueError):
    def __init__(self, errors):
        self.errors = list(errors)
        super().__init__("; ".join(self.errors))


def _check(value, schema, path, errors):
    t = schema.get("type")
    if t is not None:
        check = _TYPES.get(t)
        if check is None:
            errors.append(f"{path}: unsupported schema type {t!r}")
            return
        if not check(value):
            errors.append(f"{path}: expected {t}, got {type(value).__name__}")
            return
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "maxLength" in schema and len(value) > schema["maxLength"]:
            errors.append(f"{path}: longer than {schema['maxLength']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum {schema['maximum']}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _check(item, schema["items"], f"{path}[{i}]", errors)
    if isinstance(value, dict):
        props = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{path}.{name}: missing required field")
        for name, item in value.items():
            if name in props:
                _check(item, props[name], f"{path}.{name}", errors)
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}.{name}: unexpected field")


def collect_errors(args, schema):
    errors = []
    _check(args, schema, "args", errors)
    return errors


def validate_args(args, schema):
    """Raise SchemaError listing every problem; return args unchanged when valid."""
    errors = collect_errors(args, schema)
    if errors:
        raise SchemaError(errors)
    return args


def is_valid(args, schema):
    return not collect_errors(args, schema)
