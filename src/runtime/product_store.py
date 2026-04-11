from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.models.product import Product, PromptVariant, compute_product_revision, ensure_variant_ids


def list_products(data_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(data_dir)
    if not root.exists():
        return []

    products: list[dict[str, Any]] = []
    for product_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        product_file = product_dir / 'product.json'
        if not product_file.exists():
            continue
        product = Product.model_validate(_read_product_file(product_file))
        payload = product.model_dump(mode='json')
        payload['revision'] = compute_product_revision(product)
        products.append(payload)
    return products


def get_product(data_dir: str | Path, name: str) -> dict[str, Any]:
    product_file = Path(data_dir) / name / 'product.json'
    if not product_file.exists():
        raise FileNotFoundError(f'Product not found: {name}')
    product = Product.model_validate(_read_product_file(product_file))
    payload = product.model_dump(mode='json')
    payload['revision'] = compute_product_revision(product)
    return payload


def create_product(
    data_dir: str | Path,
    name: str,
    variants: Sequence[PromptVariant | Mapping[str, Any]],
    images: Sequence[str],
) -> dict[str, Any]:
    product_dir = Path(data_dir) / name
    if product_dir.exists():
        raise FileExistsError(f'Product already exists: {name}')

    product = Product(
        name=name,
        images=list(images),
        prompt_variants=ensure_variant_ids(variants),
    )
    product_dir.mkdir(parents=True, exist_ok=False)
    _write_product_file(product_dir / 'product.json', product)
    return get_product(data_dir, name)


def update_product(
    data_dir: str | Path,
    name: str,
    variants: Sequence[PromptVariant | Mapping[str, Any]],
) -> dict[str, Any]:
    existing = Product.model_validate(get_product(data_dir, name))
    updated = Product(
        name=existing.name,
        images=existing.images,
        prompt_variants=ensure_variant_ids(variants),
    )
    _write_product_file(Path(data_dir) / name / 'product.json', updated)
    payload = updated.model_dump(mode='json')
    payload['revision'] = compute_product_revision(updated)
    return payload


def _read_product_file(product_file: Path) -> dict[str, Any]:
    return json.loads(product_file.read_text(encoding='utf-8'))


def _write_product_file(product_file: Path, product: Product) -> None:
    product_file.write_text(
        json.dumps(product.model_dump(mode='json'), ensure_ascii=False, indent=2),
        encoding='utf-8',
    )
