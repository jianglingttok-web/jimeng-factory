"""Tests for pure helper functions in src/providers/jimeng.py.

These functions have no external dependencies (no browser, no network).
We test them by calling the instance methods on a minimal JimengProvider
constructed with a stub config — no Playwright sessions are opened.
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.providers.jimeng import JimengProvider, RemoteResult


# ── Fixture: minimal provider ─────────────────────────────────────────────────

@pytest.fixture
def provider():
    """Create a JimengProvider with a stub config — no real browser needed."""
    from src.config import (
        AppConfig,
        JimengProviderConfig,
        PathsConfig,
        ProvidersConfig,
        VideoConfig,
    )
    config = AppConfig(
        paths=PathsConfig(),
        providers=ProvidersConfig(
            jimeng=JimengProviderConfig(
                base_url="http://jimeng.test",
                enabled=False,
            )
        ),
        video=VideoConfig(),
    )
    return JimengProvider(config, config_path="config.yaml")


# ── _pick_transcoded_video_url ────────────────────────────────────────────────

class TestPickTranscodedVideoUrl:
    def test_returns_none_for_non_dict(self, provider):
        assert provider._pick_transcoded_video_url(None) is None
        assert provider._pick_transcoded_video_url("string") is None
        assert provider._pick_transcoded_video_url(42) is None
        assert provider._pick_transcoded_video_url([]) is None

    def test_returns_none_for_empty_dict(self, provider):
        assert provider._pick_transcoded_video_url({}) is None

    def test_picks_720p_first(self, provider):
        transcoded = {
            "720p": {"video_url": "http://cdn.test/720p.mp4"},
            "480p": {"video_url": "http://cdn.test/480p.mp4"},
            "360p": {"video_url": "http://cdn.test/360p.mp4"},
            "origin": {"video_url": "http://cdn.test/origin.mp4"},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url == "http://cdn.test/720p.mp4"

    def test_falls_back_to_480p_when_720p_missing(self, provider):
        transcoded = {
            "480p": {"video_url": "http://cdn.test/480p.mp4"},
            "360p": {"video_url": "http://cdn.test/360p.mp4"},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url == "http://cdn.test/480p.mp4"

    def test_falls_back_to_360p(self, provider):
        transcoded = {
            "360p": {"video_url": "http://cdn.test/360p.mp4"},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url == "http://cdn.test/360p.mp4"

    def test_falls_back_to_origin(self, provider):
        transcoded = {
            "origin": {"video_url": "http://cdn.test/origin.mp4"},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url == "http://cdn.test/origin.mp4"

    def test_returns_none_when_all_empty(self, provider):
        transcoded = {
            "720p": {"video_url": ""},
            "480p": {"video_url": "   "},
            "360p": {},
            "origin": None,
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url is None

    def test_skips_non_dict_quality_entry(self, provider):
        transcoded = {
            "720p": "not-a-dict",
            "480p": {"video_url": "http://cdn.test/480p.mp4"},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url == "http://cdn.test/480p.mp4"

    def test_strips_whitespace_from_url(self, provider):
        transcoded = {
            "720p": {"video_url": "  http://cdn.test/720p.mp4  "},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url == "http://cdn.test/720p.mp4"

    def test_returns_none_when_video_url_key_missing(self, provider):
        transcoded = {
            "720p": {"other_key": "value"},
        }
        url = provider._pick_transcoded_video_url(transcoded)
        assert url is None


# ── _extract_remote_results_from_asset_payload ────────────────────────────────

def _make_asset(
    asset_id: str = "asset-1",
    created_time: float = 1_700_000_000.0,
    video_url: str = "http://cdn.test/video.mp4",
    asset_type: int = 2,
    millis: bool = False,
) -> dict:
    """Build a minimal asset dict matching the expected payload structure."""
    ts = int(created_time * 1000) if millis else int(created_time)
    return {
        "id": asset_id,
        "type": asset_type,
        "video": {
            "created_time": ts,
            "item_list": [
                {
                    "video": {
                        "transcoded_video": {
                            "720p": {"video_url": video_url},
                        }
                    }
                }
            ],
        },
    }


def _make_payload(assets: list[dict]) -> dict:
    return {"data": {"asset_list": assets}}


class TestExtractRemoteResultsFromAssetPayload:
    def test_returns_empty_for_none_payload(self, provider):
        result = provider._extract_remote_results_from_asset_payload(None, since_ts=0.0)
        assert result == []

    def test_returns_empty_for_empty_dict(self, provider):
        result = provider._extract_remote_results_from_asset_payload({}, since_ts=0.0)
        assert result == []

    def test_returns_empty_for_missing_data_key(self, provider):
        result = provider._extract_remote_results_from_asset_payload({"other": {}}, since_ts=0.0)
        assert result == []

    def test_returns_empty_for_missing_asset_list(self, provider):
        result = provider._extract_remote_results_from_asset_payload({"data": {}}, since_ts=0.0)
        assert result == []

    def test_returns_empty_for_non_list_asset_list(self, provider):
        result = provider._extract_remote_results_from_asset_payload(
            {"data": {"asset_list": "oops"}}, since_ts=0.0
        )
        assert result == []

    def test_parses_valid_asset(self, provider):
        asset = _make_asset(created_time=1_700_000_100.0)
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert len(results) == 1
        assert isinstance(results[0], RemoteResult)
        assert results[0].url == "http://cdn.test/video.mp4"

    def test_filters_assets_before_since_ts(self, provider):
        old_asset = _make_asset(asset_id="old", created_time=1_000_000.0)
        new_asset = _make_asset(asset_id="new", created_time=1_700_000_000.0)
        payload = _make_payload([old_asset, new_asset])
        results = provider._extract_remote_results_from_asset_payload(
            payload, since_ts=1_699_999_999.0
        )
        assert len(results) == 1
        assert results[0].title == "new"

    def test_skips_non_type_2_assets(self, provider):
        asset = _make_asset(asset_type=1)  # type=1 should be skipped
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert results == []

    def test_skips_asset_with_missing_video(self, provider):
        asset = {
            "id": "no-video",
            "type": 2,
            # no "video" key
        }
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert results == []

    def test_skips_asset_with_empty_item_list(self, provider):
        asset = {
            "id": "empty-items",
            "type": 2,
            "video": {
                "created_time": 1_700_000_000,
                "item_list": [],
            },
        }
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert results == []

    def test_converts_millisecond_timestamps(self, provider):
        # When created_time > 1e12 it should be divided by 1000
        asset = _make_asset(created_time=1_700_000_000.0, millis=True)
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert len(results) == 1
        assert results[0].created_at == pytest.approx(1_700_000_000.0, abs=1.0)

    def test_asset_title_set_from_id(self, provider):
        asset = _make_asset(asset_id="my-asset-id")
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert results[0].title == "my-asset-id"

    def test_skips_asset_with_no_transcoded_url(self, provider):
        asset = {
            "id": "no-url",
            "type": 2,
            "video": {
                "created_time": 1_700_000_000,
                "item_list": [
                    {
                        "video": {
                            "transcoded_video": {
                                "720p": {"video_url": ""},  # empty URL
                            }
                        }
                    }
                ],
            },
        }
        payload = _make_payload([asset])
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert results == []

    def test_returns_multiple_valid_assets(self, provider):
        assets = [
            _make_asset(asset_id=f"asset-{i}", created_time=1_700_000_000.0 + i,
                        video_url=f"http://cdn.test/v{i}.mp4")
            for i in range(3)
        ]
        payload = _make_payload(assets)
        results = provider._extract_remote_results_from_asset_payload(payload, since_ts=0.0)
        assert len(results) == 3
        urls = {r.url for r in results}
        assert "http://cdn.test/v0.mp4" in urls
        assert "http://cdn.test/v2.mp4" in urls
