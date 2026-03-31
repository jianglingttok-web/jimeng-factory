from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Mapping, Sequence

from pydantic import BaseModel, Field


class PromptVariant(BaseModel):
    id: str
    title: str
    prompt: str


class Product(BaseModel):
    name: str
    images: list[str] = Field(default_factory=list)
    prompt_variants: list[PromptVariant] = Field(default_factory=list)


def ensure_variant_ids(
    variants: Sequence[PromptVariant | Mapping[str, Any]],
) -> list[PromptVariant]:
    normalized: list[PromptVariant] = []
    for raw_variant in variants:
        data = (
            raw_variant.model_dump()
            if isinstance(raw_variant, PromptVariant)
            else dict(raw_variant)
        )
        if not data.get("id"):
            data["id"] = uuid.uuid4().hex[:8]
        normalized.append(PromptVariant.model_validate(data))
    return normalized


def compute_product_revision(data: Product | Mapping[str, Any]) -> str:
    product = data if isinstance(data, Product) else Product.model_validate(data)
    payload = {
        "images": sorted(product.images),
        "prompt_variants": sorted(
            [
                {
                    "id": variant.id,
                    "title": variant.title,
                    "prompt": variant.prompt,
                }
                for variant in product.prompt_variants
            ],
            key=lambda item: item["id"],
        ),
    }
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
