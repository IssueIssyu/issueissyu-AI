from __future__ import annotations

from typing import Any

from pydantic import BaseModel


def register_pydantic_models(openapi_schema: dict[str, Any], *models: type[BaseModel]) -> None:
    components = openapi_schema.setdefault("components", {}).setdefault("schemas", {})
    for model in models:
        raw = model.model_json_schema(by_alias=True, ref_template="#/components/schemas/{model}")
        defs = raw.pop("$defs", {})
        for name, schema in defs.items():
            components.setdefault(name, schema)
        components[model.__name__] = raw


def patch_multipart_json_request_field(
    openapi_schema: dict[str, Any],
    *,
    body_schema_key: str,
    request_model: type[BaseModel],
    description: str,
    example: dict[str, Any] | None = None,
) -> None:
    components = openapi_schema.get("components", {}).get("schemas", {})
    body = components.get(body_schema_key)
    if body is None:
        return

    request_schema: dict[str, Any] = {
        "allOf": [{"$ref": f"#/components/schemas/{request_model.__name__}"}],
        "description": description,
    }
    if example is not None:
        request_schema["example"] = example

    body.setdefault("properties", {})["request"] = request_schema
