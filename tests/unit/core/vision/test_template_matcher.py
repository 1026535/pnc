from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np
from PIL import Image, ImageDraw

from pnc_automation.core.vision.image.models import Bounds
from pnc_automation.core.vision.template import template_matcher as matcher_module
from pnc_automation.core.vision.template.template_matcher import (
    DecodedTemplateCache,
    OpenCvTemplateMatcher,
    PreparedFrame,
)


class OpenCvTemplateMatcherTests(unittest.TestCase):
    def setUp(self) -> None:
        self.matcher = OpenCvTemplateMatcher()
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

    def test_finds_translated_textured_patch(self) -> None:
        image = _textured_image((80, 60))
        patch = image.crop((23, 17, 39, 31))
        path = self._save(patch)

        result = self.matcher.find_best_match(image, path, threshold=0.98)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=23, y=17, width=16, height=14))
        self.assertGreaterEqual(result.confidence, 0.98)

    def test_returns_none_when_template_is_absent(self) -> None:
        image = Image.new("RGB", (80, 60), (20, 30, 40))
        template = Image.new("RGB", (12, 10), (220, 150, 40))

        result = self.matcher.find_best_match(image, self._save(template), threshold=0.95)

        self.assertIsNone(result)

    def test_search_region_is_restricted(self) -> None:
        image = _textured_image((100, 80))
        patch = image.crop((70, 50, 86, 64))
        path = self._save(patch)

        result = self.matcher.find_best_match(
            image,
            path,
            threshold=0.98,
            search_region=Bounds(x=0, y=0, width=60, height=45),
        )

        self.assertIsNone(result)

    def test_alpha_mask_ignores_transparent_border(self) -> None:
        template = Image.new("RGBA", (12, 12), (0, 0, 0, 0))
        template_draw = ImageDraw.Draw(template)
        for y in range(3, 9):
            for x in range(3, 9):
                template_draw.point((x, y), fill=((x * 31) % 255, (y * 37) % 255, 180, 255))

        image = Image.new("RGB", (50, 40), (9, 11, 13))
        image.paste(template.convert("RGB"), (19, 13))
        image.paste((240, 20, 20), (19, 13, 12, 25))
        image.paste(template.crop((0, 0, 12, 12)).convert("RGB"), (19, 13), template)
        path = self._save(template)

        result = self.matcher.find_best_match(image, path, threshold=0.98)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=19, y=13, width=12, height=12))

    def test_reference_size_projects_match_to_original_pixels(self) -> None:
        reference = _textured_image((80, 40))
        template = reference.crop((21, 11, 31, 19))
        image = reference.resize((160, 80), Image.Resampling.NEAREST)

        result = self.matcher.find_best_match(
            image,
            self._save(template),
            threshold=0.85,
            reference_size=(80, 40),
        )

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=42, y=22, width=20, height=16))

    def test_prepared_frame_matches_wrapper_with_resize_and_roi(self) -> None:
        reference = _textured_image((80, 40))
        template = reference.crop((21, 11, 31, 19))
        image = reference.resize((160, 80), Image.Resampling.NEAREST)
        path = self._save(template)
        roi = Bounds(x=10, y=5, width=60, height=30)
        prepared = self.matcher.prepare_frame(image, reference_size=(80, 40))

        self.assertIsInstance(prepared, PreparedFrame)
        assert prepared is not None
        wrapper_result = self.matcher.find_best_match(
            image,
            path,
            threshold=0.85,
            search_region=roi,
            reference_size=(80, 40),
        )
        prepared_result = self.matcher.find_best_match(
            prepared,
            path,
            threshold=0.85,
            search_region=roi,
        )

        self.assertEqual(prepared_result, wrapper_result)

    def test_prepared_frame_owns_read_only_pixels(self) -> None:
        image = _textured_image((30, 20))
        prepared = self.matcher.prepare_frame(image)
        assert prepared is not None
        before = prepared.pixels.copy()

        image.paste((0, 0, 0), (0, 0, 30, 20))

        np.testing.assert_array_equal(prepared.pixels, before)
        self.assertFalse(prepared.pixels.flags.writeable)
        with self.assertRaises(ValueError):
            prepared.pixels[0, 0, 0] = 0
        with self.assertRaises(ValueError):
            prepared.pixels.setflags(write=True)

    def test_unsupported_aspect_skips_template_io(self) -> None:
        image = Image.new("RGB", (100, 100), (10, 20, 30))
        missing = Path(self.temp_dir.name) / "does-not-exist.png"

        self.assertIsNone(
            self.matcher.find_best_match(
                image,
                missing,
                threshold=0.9,
                reference_size=(100, 98),
            )
        )

    def test_template_cache_reuses_decoding_for_prepared_frame_calls(self) -> None:
        image = _textured_image((80, 60))
        template = image.crop((23, 17, 39, 31))
        path = self._save(template)
        prepared = self.matcher.prepare_frame(image)
        assert prepared is not None

        with mock.patch.object(
            matcher_module,
            "_decode_template",
            wraps=matcher_module._decode_template,
        ) as decode:
            self.assertIsNotNone(
                self.matcher.find_best_match(prepared, path, threshold=0.98)
            )
            self.assertIsNotNone(
                self.matcher.find_best_match(prepared, path, threshold=0.98)
            )

        self.assertEqual(decode.call_count, 1)

    def test_template_cache_invalidates_changed_file(self) -> None:
        image = _textured_image((80, 60))
        first = image.crop((23, 17, 39, 31))
        path = self._save(first)
        prepared = self.matcher.prepare_frame(image)
        assert prepared is not None
        self.assertIsNotNone(self.matcher.find_best_match(prepared, path, threshold=0.98))

        replacement = Image.new("RGB", (17, 15), (220, 12, 44))
        replacement.save(path)

        self.assertIsNone(self.matcher.find_best_match(prepared, path, threshold=0.98))

    def test_template_cache_is_bounded_lru(self) -> None:
        cache = DecodedTemplateCache(max_size=2)
        paths = [
            self._save(Image.new("RGB", (3, 3), color))
            for color in ((10, 20, 30), (40, 50, 60), (70, 80, 90))
        ]

        for path in paths:
            cache.get(path)

        self.assertLessEqual(len(cache._entries), 2)  # type: ignore[attr-defined]
        self.assertNotIn(paths[0].resolve(), {key[0] for key in cache._entries})  # type: ignore[attr-defined]

    def test_cached_file_deletion_is_validated(self) -> None:
        path = self._save(Image.new("RGB", (3, 3), (10, 20, 30)))
        cache = DecodedTemplateCache()
        cache.get(path)
        path.unlink()

        with self.assertRaises(FileNotFoundError):
            cache.get(path)

    def test_decode_failure_is_retryable_after_file_repair(self) -> None:
        path = Path(self.temp_dir.name) / "repairable.png"
        path.write_bytes(b"not an image")
        cache = DecodedTemplateCache()
        with self.assertRaises(ValueError):
            cache.get(path)

        Image.new("RGB", (3, 3), (10, 20, 30)).save(path)

        self.assertEqual(cache.get(path).rgb.shape, (3, 3, 3))

    def test_cache_rejects_invalid_size_and_does_not_cache_decode_errors(self) -> None:
        with self.assertRaises(ValueError):
            DecodedTemplateCache(max_size=0)

        path = Path(self.temp_dir.name) / "invalid.png"
        path.write_bytes(b"not an image")
        cache = DecodedTemplateCache()
        with self.assertRaises(ValueError):
            cache.get(path)
        path.unlink()
        with self.assertRaises(FileNotFoundError):
            cache.get(path)

    def test_rejects_reference_with_different_aspect_ratio(self) -> None:
        image = Image.new("RGB", (100, 100), (10, 20, 30))
        template = Image.new("RGB", (10, 10), (10, 20, 30))

        result = self.matcher.find_best_match(
            image,
            self._save(template),
            threshold=0.9,
            reference_size=(100, 98),
        )

        self.assertIsNone(result)

    def test_rejects_dimmed_copy_with_color_guard(self) -> None:
        image = _textured_image((80, 60))
        patch = image.crop((23, 17, 39, 31))
        dimmed = patch.point(lambda channel: channel // 2)
        image.paste(dimmed, (23, 17))

        result = self.matcher.find_best_match(
            image,
            self._save(patch),
            threshold=0.95,
        )

        self.assertIsNone(result)

    def test_matches_solid_template_without_zero_variance_failure(self) -> None:
        image = Image.new("RGB", (80, 60), (10, 15, 20))
        ImageDraw.Draw(image).rectangle((31, 22, 44, 32), fill=(180, 90, 40))
        template = Image.new("RGB", (14, 11), (180, 90, 40))

        result = self.matcher.find_best_match(image, self._save(template), threshold=0.99)

        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=31, y=22, width=14, height=11))

    def test_validates_threshold_and_image(self) -> None:
        template = Image.new("RGB", (2, 2), (10, 20, 30))
        path = self._save(template)

        with self.assertRaises(ValueError):
            self.matcher.find_best_match(template, path, threshold=1.1)
        with self.assertRaises(TypeError):
            self.matcher.find_best_match(object(), path, threshold=0.9)  # type: ignore[arg-type]
        with self.assertRaises(FileNotFoundError):
            self.matcher.find_best_match(template, Path(self.temp_dir.name) / "missing.png", threshold=0.9)

    def _save(self, image: Image.Image) -> Path:
        path = Path(self.temp_dir.name) / f"template-{len(list(Path(self.temp_dir.name).iterdir()))}.png"
        image.save(path)
        return path


def _textured_image(size: tuple[int, int]) -> Image.Image:
    width, height = size
    values = np.random.default_rng(90210).integers(
        0,
        256,
        size=(height, width, 3),
        dtype=np.uint8,
    )
    return Image.fromarray(values, mode="RGB")


if __name__ == "__main__":
    unittest.main()
