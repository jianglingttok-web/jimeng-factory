"""Tests for product_store — pure filesystem operations."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.models.product import PromptVariant
from src.runtime.product_store import (
    create_product,
    get_product,
    list_products,
    update_product,
)


# ── list_products ─────────────────────────────────────────────────────────────

class TestListProducts:
    def test_empty_dir_returns_empty_list(self, tmp_path):
        result = list_products(tmp_path)
        assert result == []

    def test_nonexistent_dir_returns_empty_list(self, tmp_path):
        result = list_products(tmp_path / "does-not-exist")
        assert result == []

    def test_dir_without_product_json_is_skipped(self, tmp_path):
        (tmp_path / "empty-dir").mkdir()
        result = list_products(tmp_path)
        assert result == []

    def test_returns_products_with_product_json(self, tmp_path):
        create_product(tmp_path, "product-a", [
            PromptVariant(id="", title="Title A", prompt="prompt a")
        ], images=[])
        result = list_products(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "product-a"

    def test_returns_multiple_products(self, tmp_path):
        create_product(tmp_path, "alpha", [
            PromptVariant(id="", title="T", prompt="p1")
        ], images=[])
        create_product(tmp_path, "beta", [
            PromptVariant(id="", title="T", prompt="p2")
        ], images=[])
        result = list_products(tmp_path)
        names = {p["name"] for p in result}
        assert names == {"alpha", "beta"}

    def test_mixed_dirs_only_lists_products_with_json(self, tmp_path):
        (tmp_path / "no-json-dir").mkdir()
        create_product(tmp_path, "valid-product", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=[])
        result = list_products(tmp_path)
        assert len(result) == 1
        assert result[0]["name"] == "valid-product"

    def test_each_product_has_revision_field(self, tmp_path):
        create_product(tmp_path, "rev-test", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=[])
        result = list_products(tmp_path)
        assert "revision" in result[0]
        assert isinstance(result[0]["revision"], str)
        assert len(result[0]["revision"]) > 0

    def test_products_returned_in_sorted_order(self, tmp_path):
        create_product(tmp_path, "zzz-last", [PromptVariant(id="", title="T", prompt="p")], images=[])
        create_product(tmp_path, "aaa-first", [PromptVariant(id="", title="T", prompt="p")], images=[])
        result = list_products(tmp_path)
        assert result[0]["name"] == "aaa-first"
        assert result[1]["name"] == "zzz-last"


# ── get_product ───────────────────────────────────────────────────────────────

class TestGetProduct:
    def test_returns_product_when_found(self, tmp_path):
        create_product(tmp_path, "my-product", [
            PromptVariant(id="", title="T1", prompt="prompt text")
        ], images=[])
        result = get_product(tmp_path, "my-product")
        assert result["name"] == "my-product"

    def test_raises_for_missing_product(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            get_product(tmp_path, "nonexistent")

    def test_includes_revision(self, tmp_path):
        create_product(tmp_path, "p", [PromptVariant(id="", title="T", prompt="p")], images=[])
        result = get_product(tmp_path, "p")
        assert "revision" in result

    def test_includes_prompt_variants(self, tmp_path):
        create_product(tmp_path, "p", [
            PromptVariant(id="", title="My Title", prompt="my prompt")
        ], images=[])
        result = get_product(tmp_path, "p")
        variants = result["prompt_variants"]
        assert len(variants) == 1
        assert variants[0]["prompt"] == "my prompt"
        assert variants[0]["title"] == "My Title"

    def test_includes_images_list(self, tmp_path):
        create_product(tmp_path, "p", [PromptVariant(id="", title="T", prompt="p")], images=["img1.jpg"])
        result = get_product(tmp_path, "p")
        assert "img1.jpg" in result["images"]


# ── create_product ────────────────────────────────────────────────────────────

class TestCreateProduct:
    def test_creates_product_directory(self, tmp_path):
        create_product(tmp_path, "new-prod", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=[])
        assert (tmp_path / "new-prod").is_dir()

    def test_creates_product_json(self, tmp_path):
        create_product(tmp_path, "json-prod", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=[])
        assert (tmp_path / "json-prod" / "product.json").exists()

    def test_returns_product_dict_with_name(self, tmp_path):
        result = create_product(tmp_path, "returned-prod", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=[])
        assert result["name"] == "returned-prod"

    def test_assigns_variant_ids_when_empty(self, tmp_path):
        result = create_product(tmp_path, "id-prod", [
            PromptVariant(id="", title="T", prompt="my prompt")
        ], images=[])
        variants = result["prompt_variants"]
        assert len(variants) == 1
        assert variants[0]["id"] != ""

    def test_raises_on_duplicate_name(self, tmp_path):
        create_product(tmp_path, "dup-prod", [PromptVariant(id="", title="T", prompt="p")], images=[])
        with pytest.raises(FileExistsError):
            create_product(tmp_path, "dup-prod", [PromptVariant(id="", title="T", prompt="p")], images=[])

    def test_creates_with_multiple_variants(self, tmp_path):
        result = create_product(tmp_path, "multi-variant", [
            PromptVariant(id="", title="V1", prompt="prompt 1"),
            PromptVariant(id="", title="V2", prompt="prompt 2"),
        ], images=[])
        assert len(result["prompt_variants"]) == 2

    def test_stores_images(self, tmp_path):
        result = create_product(tmp_path, "with-images", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=["photo1.jpg", "photo2.jpg"])
        assert "photo1.jpg" in result["images"]
        assert "photo2.jpg" in result["images"]


# ── update_product ────────────────────────────────────────────────────────────

class TestUpdateProduct:
    def test_updates_variants(self, tmp_path):
        create_product(tmp_path, "upd-prod", [
            PromptVariant(id="", title="Old Title", prompt="old prompt")
        ], images=[])
        result = update_product(tmp_path, "upd-prod", [
            PromptVariant(id="", title="New Title", prompt="new prompt")
        ])
        assert result["prompt_variants"][0]["prompt"] == "new prompt"
        assert result["prompt_variants"][0]["title"] == "New Title"

    def test_preserves_product_name(self, tmp_path):
        create_product(tmp_path, "name-check", [PromptVariant(id="", title="T", prompt="p")], images=[])
        result = update_product(tmp_path, "name-check", [PromptVariant(id="", title="T2", prompt="p2")])
        assert result["name"] == "name-check"

    def test_preserves_existing_images(self, tmp_path):
        create_product(tmp_path, "img-preserve", [
            PromptVariant(id="", title="T", prompt="p")
        ], images=["kept.jpg"])
        result = update_product(tmp_path, "img-preserve", [
            PromptVariant(id="", title="T2", prompt="p2")
        ])
        assert "kept.jpg" in result["images"]

    def test_raises_for_missing_product(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            update_product(tmp_path, "ghost-product", [
                PromptVariant(id="", title="T", prompt="p")
            ])

    def test_persists_update_to_disk(self, tmp_path):
        create_product(tmp_path, "persist-test", [
            PromptVariant(id="", title="Old", prompt="old")
        ], images=[])
        update_product(tmp_path, "persist-test", [
            PromptVariant(id="", title="New", prompt="new text")
        ])
        # Read back via get_product to verify file was written
        reloaded = get_product(tmp_path, "persist-test")
        assert reloaded["prompt_variants"][0]["prompt"] == "new text"

    def test_assigns_ids_to_new_variants(self, tmp_path):
        create_product(tmp_path, "id-assign", [PromptVariant(id="", title="T", prompt="p")], images=[])
        result = update_product(tmp_path, "id-assign", [
            PromptVariant(id="", title="No ID", prompt="fresh variant")
        ])
        assert result["prompt_variants"][0]["id"] != ""

    def test_revision_changes_after_update(self, tmp_path):
        create_product(tmp_path, "rev-chg", [PromptVariant(id="", title="T", prompt="original")], images=[])
        before = get_product(tmp_path, "rev-chg")["revision"]
        update_product(tmp_path, "rev-chg", [PromptVariant(id="", title="T", prompt="changed")])
        after = get_product(tmp_path, "rev-chg")["revision"]
        assert before != after
