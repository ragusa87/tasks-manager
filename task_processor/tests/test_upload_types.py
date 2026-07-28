"""Unit tests for the allow-list -> UI string derivations (pure functions)."""

from django.conf import settings

from core.upload_types import (
    accept_attribute,
    describe_types,
    recording_enabled,
    type_categories,
)

FULL_LIST = [
    "application/pdf",
    "image/png",
    "image/jpeg",
    "audio/mpeg",
    "audio/mp4",
    "video/mp4",  # m4a container alias
]


class TestTypeCategories:
    def test_full_list(self):
        assert type_categories(FULL_LIST) == ["PDF", "image", "audio"]

    def test_pdf_only(self):
        assert type_categories(["application/pdf"]) == ["PDF"]

    def test_video_counts_when_no_audio(self):
        # Without audio in the list, video/mp4 and video/webm are genuinely video.
        assert type_categories(["video/mp4"]) == ["video"]
        assert type_categories(["video/webm"]) == ["video"]

    def test_webm_container_alias_is_not_video(self):
        assert type_categories(["audio/ogg", "video/webm"]) == ["audio"]

    def test_unknown_type_is_generic_file(self):
        assert type_categories(["application/zip"]) == ["file"]

    def test_empty(self):
        assert type_categories([]) == []


class TestDescribeTypes:
    def test_three_categories(self):
        assert describe_types(FULL_LIST) == "PDF, image or audio"

    def test_two_categories(self):
        assert describe_types(["application/pdf", "image/png"]) == "PDF or image"

    def test_single_category(self):
        assert describe_types(["application/pdf"]) == "PDF"

    def test_empty_falls_back(self):
        assert describe_types([]) == "file"


class TestAcceptAttribute:
    def test_full_list(self):
        assert (
            accept_attribute(FULL_LIST) == ".pdf,application/pdf,image/*,audio/*,.m4a"
        )

    def test_pdf_only(self):
        assert accept_attribute(["application/pdf"]) == ".pdf,application/pdf"

    def test_m4a_hint_only_with_mp4_audio(self):
        assert accept_attribute(["audio/ogg"]) == "audio/*"
        assert accept_attribute(["audio/mp4"]) == "audio/*,.m4a"

    def test_unknown_type_passes_through(self):
        assert accept_attribute(["application/zip"]) == "application/zip"

    def test_webm_hint_only_with_audio(self):
        assert accept_attribute(["audio/ogg", "video/webm"]) == "audio/*,.webm"
        assert accept_attribute(["video/webm"]) == "video/webm"


class TestRecordingEnabled:
    """The recorder always uploads WAV, which magic detects as audio/x-wav;
    that exact entry gates the feature."""

    def test_requires_the_detected_type(self):
        assert recording_enabled(["audio/x-wav"]) is True
        # audio/wav alone is not enough: magic reports audio/x-wav.
        assert recording_enabled(["audio/wav"]) is False

    def test_disabled_without_wav(self):
        assert recording_enabled(["application/pdf", "audio/webm"]) is False
        assert recording_enabled([]) is False


class TestAgainstRealSettings:
    """The derivations must stay coherent with the deployed allow-list."""

    def test_settings_label(self):
        assert describe_types(settings.ALLOWED_TYPES) == "PDF, image or audio"

    def test_settings_accept(self):
        accept = accept_attribute(settings.ALLOWED_TYPES)
        assert "image/*" in accept
        assert "audio/*" in accept
        assert ".pdf" in accept
        assert ".m4a" in accept
        # the container quirks must not leak a video/* picker entry
        assert "video" not in accept

    def test_settings_enable_the_recorder(self):
        assert recording_enabled(settings.ALLOWED_TYPES) is True
