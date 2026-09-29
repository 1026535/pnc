from __future__ import annotations

import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

import cv2
import numpy as np
from PIL import Image, ImageDraw

from pnc_automation.core.vision.image.models import Bounds, TemplateMatch
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

    def test_opencv_inner_pool_stays_bounded_during_concurrent_matching(self) -> None:
        self.assertEqual(cv2.getNumThreads(), 1)
        image = _textured_image((80, 60))
        patch = image.crop((23, 17, 39, 31))
        path = self._save(patch)

        with ThreadPoolExecutor(max_workers=4) as pool:
            results = tuple(
                pool.map(
                    lambda _: self.matcher.find_best_match(
                        image, path, threshold=0.98
                    ),
                    range(4),
                )
            )

        self.assertEqual(
            [result.bounds for result in results if result is not None],
            [Bounds(x=23, y=17, width=16, height=14)] * 4,
        )
        self.assertEqual(cv2.getNumThreads(), 1)

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

    def test_scaled_variants_are_shared_between_default_matchers(self) -> None:
        image = _textured_image((80, 60))
        template = image.crop((23, 17, 39, 31))
        path = self._save(template)
        prepared = self.matcher.prepare_frame(image)
        second_matcher = OpenCvTemplateMatcher()
        assert prepared is not None

        with (
            mock.patch.object(
                matcher_module,
                "_decode_template",
                wraps=matcher_module._decode_template,
            ) as decode,
            mock.patch.object(
                matcher_module,
                "_scale_decoded_template",
                wraps=matcher_module._scale_decoded_template,
            ) as scale,
        ):
            first = self.matcher.find_best_match(
                prepared, path, threshold=0.0, template_scale=1.25
            )
            second = second_matcher.find_best_match(
                prepared, path, threshold=0.0, template_scale=1.25
            )

        self.assertEqual(first, second)
        self.assertIsNotNone(first)
        self.assertEqual(1, decode.call_count)
        self.assertEqual(1, scale.call_count)

    def test_scaled_template_cache_invalidates_changed_file(self) -> None:
        cache = DecodedTemplateCache(max_size=4)
        path = self._save(Image.new("RGB", (16, 14), (10, 20, 30)))

        first = cache._get_scaled(path, 1.25)
        self.assertIsNotNone(first)
        Image.new("RGB", (24, 18), (30, 40, 50)).save(path)
        second = cache._get_scaled(path, 1.25)

        self.assertIsNotNone(second)
        assert second is not None
        self.assertEqual((22, 30, 3), second.rgb.shape)
        self.assertEqual(2, len(cache._entries))  # type: ignore[attr-defined]

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

        for scaled in (False, True):
            with self.subTest(scaled=scaled):
                cache.clear()
                for path in paths:
                    if scaled:
                        cache._get_scaled(path, 1.1)
                    else:
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

    def test_find_matches_returns_each_separated_glyph_once(self) -> None:
        image = _textured_image((120, 40))
        patch = image.crop((23, 13, 35, 25))
        image.paste(patch, (75, 9))
        path = self._save(patch)

        matches = self.matcher.find_matches(image, path, threshold=0.98)

        self.assertEqual(
            {match.bounds for match in matches},
            {Bounds(23, 13, 12, 12), Bounds(75, 9, 12, 12)},
        )
        self.assertTrue(all(match.confidence >= 0.98 for match in matches))

    def test_find_matches_suppresses_overlapping_duplicate_candidates(self) -> None:
        image = _textured_image((60, 40))
        patch = image.crop((23, 13, 35, 25))
        path = self._save(patch)

        matches = self.matcher.find_matches(image, path, threshold=0.98)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].bounds, Bounds(23, 13, 12, 12))

    def test_find_matches_respects_max_matches_and_threshold(self) -> None:
        image = _textured_image((160, 40))
        patch = image.crop((11, 13, 23, 25))
        image.paste(patch, (60, 9))
        image.paste(patch, (110, 17))
        path = self._save(patch)

        absent = self._save(Image.new("RGB", (12, 12), (255, 0, 255)))

        capped = self.matcher.find_matches(image, path, threshold=0.98, max_matches=2)
        rejected = self.matcher.find_matches(image, absent, threshold=0.98)

        self.assertEqual(len(capped), 2)
        self.assertEqual(rejected, ())
        with self.assertRaises(ValueError):
            self.matcher.find_matches(image, path, threshold=0.9, max_matches=0)

    def test_find_matches_prefers_confidence_over_correlation_when_candidates_compete(self) -> None:
        """A brightened copy out-correlates a faithful one but must not win suppression."""
        template_values = np.random.default_rng(7).integers(
            0, 190, size=(12, 12, 3), dtype=np.uint8
        )
        template = Image.fromarray(template_values, mode="RGB")
        brightened = Image.fromarray(
            (template_values.astype(np.int16) + 60).astype(np.uint8), mode="RGB"
        )
        faithful_values = template_values.copy()
        for y, x in ((2, 3), (7, 9), (10, 1), (4, 11)):
            faithful_values[y, x] = np.clip(
                faithful_values[y, x].astype(np.int16) + 25, 0, 255
            ).astype(np.uint8)
        image = Image.new("RGB", (80, 50), (32, 32, 32))
        image.paste(brightened, (20, 15))
        image.paste(Image.fromarray(faithful_values, mode="RGB"), (22, 16))
        path = self._save(template)

        matches = self.matcher.find_matches(image, path, threshold=0.5)
        best = self.matcher.find_best_match(image, path, threshold=0.5)

        self.assertEqual([Bounds(22, 16, 12, 12)], [match.bounds for match in matches])
        self.assertGreater(matches[0].confidence, 0.9)
        assert best is not None
        self.assertEqual(Bounds(22, 16, 12, 12), best.bounds)

    def test_find_matches_stays_inside_search_region(self) -> None:
        image = _textured_image((120, 60))
        patch = image.crop((23, 13, 35, 25))
        image.paste(patch, (90, 40))
        path = self._save(patch)

        matches = self.matcher.find_matches(
            image,
            path,
            threshold=0.98,
            search_region=Bounds(x=0, y=0, width=60, height=40),
        )

        self.assertEqual(
            [match.bounds for match in matches],
            [Bounds(23, 13, 12, 12)],
        )

    def test_find_matches_projects_bounds_to_original_pixels(self) -> None:
        reference = _textured_image((80, 40))
        template = reference.crop((21, 11, 31, 19))
        image = reference.resize((160, 80), Image.Resampling.NEAREST)
        image.paste(template.resize((20, 16), Image.Resampling.NEAREST), (120, 40))
        path = self._save(template)
        prepared = self.matcher.prepare_frame(image, reference_size=(80, 40))
        assert prepared is not None

        matches = self.matcher.find_matches(prepared, path, threshold=0.85)

        self.assertEqual(len(matches), 2)
        self.assertIn(Bounds(42, 22, 20, 16), {match.bounds for match in matches})
        self.assertIn(Bounds(120, 40, 20, 16), {match.bounds for match in matches})

    def test_coarse_to_fine_refinement_recovers_full_search_result(self) -> None:
        image = _smooth_textured_image((120, 80))
        patch = image.crop((47, 33, 63, 47))
        path = self._save(patch)
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert proposal is not None
        expected = self.matcher.find_best_match(prepared, path, threshold=0.9)

        with mock.patch.object(
            self.matcher,
            "find_best_match",
            wraps=self.matcher.find_best_match,
        ) as native:
            result = self.matcher.find_best_match_coarse_to_fine(
                prepared, proposal, path, threshold=0.9
            )

        self.assertEqual(result, expected)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=47, y=33, width=16, height=14))
        refined = [
            call
            for call in native.call_args_list
            if call.kwargs.get("search_region") is not None
        ]
        self.assertGreaterEqual(len(refined), 1)
        self.assertLessEqual(len(refined), 8)
        self.assertTrue(
            all(call.args[0] is prepared for call in refined)
        )

    def test_coarse_to_fine_projects_bounds_at_nonnative_resolution(self) -> None:
        reference = _smooth_textured_image((80, 40))
        template = reference.crop((21, 11, 31, 19))
        image = reference.resize((160, 80), Image.Resampling.NEAREST)
        path = self._save(template)
        prepared = self.matcher.prepare_frame(image, reference_size=(80, 40))
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert proposal is not None
        self.assertEqual(proposal.original_size, (160, 80))
        expected = self.matcher.find_best_match(prepared, path, threshold=0.85)

        result = self.matcher.find_best_match_coarse_to_fine(
            prepared, proposal, path, threshold=0.85
        )

        self.assertEqual(result, expected)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=42, y=22, width=20, height=16))

    def test_coarse_to_fine_supports_off_grid_template_scale(self) -> None:
        donor = _smooth_textured_image((120, 90))
        patch = donor.crop((8, 8, 32, 32))
        scaled_values = cv2.resize(
            np.array(patch), (20, 20), interpolation=cv2.INTER_AREA
        )
        image = Image.new("RGB", (120, 90), (24, 28, 32))
        image.paste(Image.fromarray(scaled_values, mode="RGB"), (61, 44))
        path = self._save(patch)
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert proposal is not None
        expected = self.matcher.find_best_match(
            prepared, path, threshold=0.8, template_scale=0.83
        )

        result = self.matcher.find_best_match_coarse_to_fine(
            prepared, proposal, path, threshold=0.8, template_scale=0.83
        )

        assert expected is not None and result is not None
        self.assertEqual(result.bounds, Bounds(x=61, y=44, width=20, height=20))
        self.assertEqual(result.bounds, expected.bounds)
        self.assertAlmostEqual(result.confidence, expected.confidence, delta=1e-5)

    def test_coarse_to_fine_overflow_falls_back_to_exact_search(self) -> None:
        donor = _smooth_textured_image((160, 100))
        patch = donor.crop((4, 4, 16, 16))
        path = self._save(patch)
        image = Image.new("RGB", (160, 100), (24, 28, 32))
        image.paste(patch, (24, 8))
        noise = np.random.default_rng(11).integers(-3, 4, (12, 12, 3))
        perturbed = np.clip(np.array(patch).astype(np.int16) + noise, 0, 255)
        rival = Image.fromarray(perturbed.astype(np.uint8), mode="RGB")
        for index in range(1, 9):
            image.paste(rival, (24 + 14 * index, 8))
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert proposal is not None
        expected = self.matcher.find_best_match(prepared, path, threshold=0.9)

        with mock.patch.object(
            self.matcher,
            "find_best_match",
            wraps=self.matcher.find_best_match,
        ) as native:
            result = self.matcher.find_best_match_coarse_to_fine(
                prepared, proposal, path, threshold=0.9
            )

        # Nine distinct neighborhoods exceed the refinement budget, so the
        # exact full-resolution search runs once and no rival is truncated.
        self.assertEqual(native.call_count, 1)
        self.assertIsNone(native.call_args.kwargs.get("search_region"))
        self.assertEqual(result, expected)
        assert result is not None
        self.assertEqual(result.bounds, Bounds(x=24, y=8, width=12, height=12))

    def test_proposal_frame_quarters_the_reference_resolution(self) -> None:
        """The proposal frame is a quarter-scale immutable view of the scene."""
        image = _smooth_textured_image((200, 160))
        prepared = self.matcher.prepare_frame(image)

        proposal = self.matcher.prepare_proposal_frame(prepared)

        self.assertIsInstance(proposal, PreparedFrame)
        self.assertEqual(proposal.reference_size, (50, 40))
        self.assertEqual(proposal.original_size, (200, 160))
        self.assertEqual(proposal.pixels.shape, (40, 50, 3))
        self.assertFalse(proposal.pixels.flags.writeable)

        # Reference-normalized frames keep the original capture size, so
        # coarse hits still project through the standard mapping.
        resized = Image.new("RGB", (240, 184), (30, 40, 50))
        normalized = self.matcher.prepare_frame(resized, reference_size=(120, 92))
        assert normalized is not None
        small = self.matcher.prepare_proposal_frame(normalized)
        self.assertEqual(small.reference_size, (30, 23))
        self.assertEqual(small.original_size, (240, 184))
        self.assertTrue(np.all(small.pixels == (30, 40, 50)))

    def test_proposal_frame_falls_back_to_half_for_incompatible_quarter_aspect(self) -> None:
        prepared = self.matcher.prepare_frame(_smooth_textured_image((120, 90)))

        proposal = self.matcher.prepare_proposal_frame(prepared)

        self.assertEqual((60, 45), proposal.reference_size)
        self.assertEqual((120, 90), proposal.original_size)
        self.assertEqual((45, 60, 3), proposal.pixels.shape)
        self.assertFalse(proposal.pixels.flags.writeable)

    def test_proposal_frame_uses_owned_native_copy_when_downscales_mismatch(self) -> None:
        values = np.random.default_rng(9).integers(0, 256, (5, 7, 3), dtype=np.uint8)
        image = Image.fromarray(values, mode="RGB")
        prepared = self.matcher.prepare_frame(image)

        proposal = self.matcher.prepare_proposal_frame(prepared)

        self.assertEqual((7, 5), proposal.reference_size)
        self.assertEqual((7, 5), proposal.original_size)
        np.testing.assert_array_equal(prepared.pixels, proposal.pixels)
        self.assertFalse(np.shares_memory(prepared.pixels, proposal.pixels))
        with self.assertRaises(ValueError):
            proposal.pixels.setflags(write=True)
        path = self._save(image.crop((2, 1, 5, 4)))
        match = self.matcher.find_best_match_coarse_to_fine(
            prepared, proposal, path, threshold=0.9
        )
        self.assertIsNotNone(match)
        assert match is not None
        self.assertEqual(Bounds(2, 1, 3, 3), match.bounds)

    def test_proposal_frame_requires_a_prepared_frame(self) -> None:
        with self.assertRaises(TypeError):
            self.matcher.prepare_proposal_frame(Image.new("RGB", (16, 16)))  # type: ignore[arg-type]

    def test_coarse_to_fine_rejects_a_mismatched_proposal_frame(self) -> None:
        prepared = self.matcher.prepare_frame(_smooth_textured_image((120, 90)))
        assert prepared is not None
        # The malformed former quarter proposal still fails; the producer
        # now chooses 60x45 rather than relaxing consumer rejection.
        proposal = PreparedFrame(
            pixels=np.zeros((22, 30, 3), dtype=np.uint8),
            original_size=(120, 90),
            reference_size=(30, 22),
        )

        with self.assertRaisesRegex(ValueError, "same-aspect downscale"):
            self.matcher.find_best_match_coarse_to_fine(
                prepared, proposal, Path(self.temp_dir.name) / "any.png", threshold=0.9
            )

    def test_coarse_to_fine_dedup_is_measured_in_native_pixels(self) -> None:
        """Proposal peaks merge at 6 native px, so 2 quarter px stay distinct."""
        image = _smooth_textured_image((120, 92))
        path = self._save(image.crop((8, 8, 24, 24)))
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert prepared is not None and proposal is not None
        # The quarter-resolution proposal maps one coarse pixel to 4 native.

        for peaks, expected_calls in (
            (((10, 5), (11, 5)), 1),  # 4 native px apart -> one neighborhood
            (((10, 5), (12, 5)), 2),  # 8 native px apart -> two neighborhoods
            (((10, 5), (10, 7)), 2),  # 8 native px on the other axis -> two
        ):
            with self.subTest(peaks=peaks):
                refined: list[Bounds] = []

                def fake_native(_frame, _path, *, threshold, search_region=None, **_kw):
                    assert search_region is not None
                    refined.append(search_region)
                    return None

                with (
                    mock.patch.object(
                        matcher_module,
                        "_qualified_candidates",
                        return_value=[(x, y, 0.95, 0.95) for x, y in peaks],
                    ) as coarse,
                    mock.patch.object(
                        self.matcher, "find_best_match", side_effect=fake_native
                    ) as native,
                ):
                    result = self.matcher.find_best_match_coarse_to_fine(
                        prepared, proposal, path, threshold=0.9
                    )

                self.assertIsNone(result)
                self.assertEqual(expected_calls, native.call_count)
                # Coarse candidates are proposed at the lowered floor.
                self.assertAlmostEqual(0.7, coarse.call_args.kwargs["threshold"])
                # Quarter coordinate (10, 5) maps to native (40, 20) and the
                # 16x16 template keeps the 6px refinement margin on each side.
                self.assertEqual(Bounds(34, 14, 28, 28), refined[0])

    def test_coarse_to_fine_returns_the_best_confidence_refinement(self) -> None:
        """Distinct neighborhoods each refine natively; confidence picks the winner."""
        image = _smooth_textured_image((120, 92))
        path = self._save(image.crop((8, 8, 24, 24)))
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert prepared is not None and proposal is not None
        strong = TemplateMatch(bounds=Bounds(60, 24, 16, 16), confidence=0.93)
        weak = TemplateMatch(bounds=Bounds(40, 20, 16, 16), confidence=0.85)
        hits = iter((weak, strong))

        with (
            mock.patch.object(
                matcher_module,
                "_qualified_candidates",
                return_value=[(10, 5, 0.96, 0.96), (15, 6, 0.97, 0.97)],
            ),
            mock.patch.object(
                self.matcher,
                "find_best_match",
                side_effect=lambda *_a, **_kw: next(hits),
            ) as native,
        ):
            result = self.matcher.find_best_match_coarse_to_fine(
                prepared, proposal, path, threshold=0.9
            )

        self.assertEqual(2, native.call_count)
        self.assertEqual(strong, result)

    def test_coarse_to_fine_undersized_proposal_template_runs_exact_search(self) -> None:
        """A template too small at quarter scale keeps the exact-native path."""
        image = _smooth_textured_image((120, 92))
        patch = image.crop((47, 33, 59, 45))
        path = self._save(patch)
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert prepared is not None and proposal is not None
        expected = self.matcher.find_best_match(prepared, path, threshold=0.9)

        with mock.patch.object(
            self.matcher,
            "find_best_match",
            wraps=self.matcher.find_best_match,
        ) as native:
            result = self.matcher.find_best_match_coarse_to_fine(
                prepared, proposal, path, threshold=0.9
            )

        # The 12px template is 3px on the proposal frame, below the supported
        # minimum, so the exact full-resolution search runs once.
        self.assertEqual(1, native.call_count)
        self.assertIsNone(native.call_args.kwargs.get("search_region"))
        self.assertEqual(result, expected)

    def test_coarse_to_fine_leaves_generic_matcher_behavior_unchanged(self) -> None:
        image = _smooth_textured_image((80, 60))
        patch = image.crop((23, 17, 39, 31))
        path = self._save(patch)
        prepared = self.matcher.prepare_frame(image)
        proposal = self.matcher.prepare_proposal_frame(prepared)
        assert proposal is not None
        self.assertIsNotNone(
            self.matcher.find_best_match_coarse_to_fine(
                prepared, proposal, path, threshold=0.9
            )
        )

        direct = self.matcher.find_best_match(prepared, path, threshold=0.98)
        matches = self.matcher.find_matches(prepared, path, threshold=0.98)

        assert direct is not None
        self.assertEqual(direct.bounds, Bounds(x=23, y=17, width=16, height=14))
        self.assertEqual(
            [match.bounds for match in matches],
            [Bounds(x=23, y=17, width=16, height=14)],
        )

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


def _smooth_textured_image(size: tuple[int, int]) -> Image.Image:
    """Structured content that survives 2x area downsampling at any phase.

    Independent pixel noise loses its coarse-scale correlation when a patch
    sits at odd coordinates, so coarse-to-fine tests need content with
    realistic multi-pixel structure instead.
    """

    width, height = size
    small = np.random.default_rng(7).integers(
        0,
        256,
        size=(max(1, height // 4), max(1, width // 4), 3),
        dtype=np.uint8,
    )
    values = cv2.resize(small, (width, height), interpolation=cv2.INTER_LINEAR)
    return Image.fromarray(values, mode="RGB")


if __name__ == "__main__":
    unittest.main()
