"""Tests for src.apps.data_pipeline.preprocess — image patching pipeline."""

from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from src.apps.data_pipeline.preprocess import (
    GRID_2X2_THRESHOLD,
    GRID_4X4_THRESHOLD,
    TARGET_PATCH_SIZE,
    PreprocessConfig,
    S3UploadContext,
    _encode_jpeg,
    _upload_patch,
    apply_gaussian_blur,
    center_crop_to_square,
    choose_grid_size,
    compute_grid_boxes,
    downsample_to_square,
    extract_grid_patches,
    generate_patch_variants,
    process_image_to_patches,
    rotate_patch,
)


class TestPreprocessConfig:
    """Tests for PreprocessConfig."""

    def test_defaults(self):
        cfg = PreprocessConfig()
        assert cfg.apply_gaussian_blur is False
        assert cfg.gaussian_blur_radius == 1.0
        assert cfg.rotation_angles == [0]

    def test_custom_rotation(self):
        cfg = PreprocessConfig(rotation_angles=[0, 90, 180])
        assert cfg.rotation_angles == [0, 90, 180]

    def test_blur_enabled(self):
        cfg = PreprocessConfig(apply_gaussian_blur=True, gaussian_blur_radius=2.5)
        assert cfg.apply_gaussian_blur is True
        assert cfg.gaussian_blur_radius == 2.5


class TestS3UploadContext:
    """Tests for S3UploadContext dataclass."""

    def test_creation(self):
        ctx = S3UploadContext(
            s3_client=MagicMock(),
            processed_bucket="bucket",
            processed_prefix="prefix",
            image_id="img-123",
        )
        assert ctx.processed_bucket == "bucket"
        assert ctx.image_id == "img-123"


class TestChooseGridSize:
    """Tests for choose_grid_size."""

    def test_large_image_4x4(self):
        assert choose_grid_size(2048, 1536) == 4

    def test_medium_image_2x2(self):
        assert choose_grid_size(800, 600) == 2

    def test_small_image_2x2(self):
        assert choose_grid_size(400, 300) == 2

    def test_exactly_at_threshold(self):
        # min side == 1024 is NOT > 1024, so should be 2x2
        assert choose_grid_size(1024, 1024) == 2

    def test_just_above_4x4_threshold(self):
        assert choose_grid_size(1025, 1025) == 4

    def test_portrait_orientation(self):
        assert choose_grid_size(600, 2000) == 2  # min side is 600

    def test_landscape_very_wide(self):
        assert choose_grid_size(5000, 1025) == 4


class TestComputeGridBoxes:
    """Tests for compute_grid_boxes."""

    def test_2x2_grid(self):
        boxes = compute_grid_boxes(100, 100, 2)
        assert len(boxes) == 4
        # First box: top-left
        assert boxes[0] == (0, 0, 50, 50)
        # Last box: bottom-right
        assert boxes[3] == (50, 50, 100, 100)

    def test_4x4_grid(self):
        boxes = compute_grid_boxes(400, 400, 4)
        assert len(boxes) == 16

    def test_1x1_grid(self):
        boxes = compute_grid_boxes(100, 100, 1)
        assert len(boxes) == 1
        assert boxes[0] == (0, 0, 100, 100)

    def test_non_square(self):
        boxes = compute_grid_boxes(200, 100, 2)
        assert len(boxes) == 4
        # Widths should be 100, heights 50
        assert boxes[0] == (0, 0, 100, 50)


class TestExtractGridPatches:
    """Tests for extract_grid_patches."""

    def test_returns_correct_count(self):
        img = Image.new("RGB", (100, 100))
        patches = extract_grid_patches(img, 2)
        assert len(patches) == 4

    def test_patch_contents(self):
        img = Image.new("RGB", (100, 100))
        patches = extract_grid_patches(img, 2)
        patch_img, x, y, w, h = patches[0]
        assert isinstance(patch_img, Image.Image)
        assert x == 0
        assert y == 0
        assert w == 50
        assert h == 50


class TestCenterCropToSquare:
    """Tests for center_crop_to_square."""

    def test_basic_crop(self):
        img = Image.new("RGB", (300, 300))
        cropped = center_crop_to_square(img, 224)
        assert cropped.size == (224, 224)

    def test_rectangular_input(self):
        img = Image.new("RGB", (400, 300))
        cropped = center_crop_to_square(img, 224)
        assert cropped.size == (224, 224)

    def test_too_small_raises(self):
        img = Image.new("RGB", (100, 100))
        with pytest.raises(ValueError, match="Cannot center crop"):
            center_crop_to_square(img, 224)

    def test_exact_size(self):
        img = Image.new("RGB", (224, 224))
        cropped = center_crop_to_square(img, 224)
        assert cropped.size == (224, 224)


class TestDownsampleToSquare:
    """Tests for downsample_to_square."""

    def test_downsamples(self):
        img = Image.new("RGB", (500, 500))
        result = downsample_to_square(img, 224)
        assert result.size == (224, 224)

    def test_upsamples(self):
        img = Image.new("RGB", (50, 50))
        result = downsample_to_square(img, 224)
        assert result.size == (224, 224)


class TestApplyGaussianBlur:
    """Tests for apply_gaussian_blur."""

    def test_returns_same_size(self):
        img = Image.new("RGB", (100, 100))
        blurred = apply_gaussian_blur(img, 2.0)
        assert blurred.size == (100, 100)


class TestRotatePatch:
    """Tests for rotate_patch."""

    def test_zero_rotation_returns_copy(self):
        img = Image.new("RGB", (100, 100), color="red")
        rotated = rotate_patch(img, 0)
        assert rotated.size == img.size
        assert rotated is not img  # Should be a copy

    def test_90_degree_rotation(self):
        img = Image.new("RGB", (100, 200))
        rotated = rotate_patch(img, 90)
        assert rotated.size[0] >= 100  # expand=True changes dimensions


class TestGeneratePatchVariants:
    """Tests for generate_patch_variants."""

    def test_default_config_one_variant(self):
        img = Image.new("RGB", (100, 100))
        config = PreprocessConfig()
        variants = generate_patch_variants(img, config)
        assert len(variants) == 1
        assert variants[0][1] == "orig"

    def test_multiple_rotations(self):
        img = Image.new("RGB", (100, 100))
        config = PreprocessConfig(rotation_angles=[0, 90])
        variants = generate_patch_variants(img, config)
        assert len(variants) == 2
        suffixes = [v[1] for v in variants]
        assert "orig" in suffixes
        assert "rot90" in suffixes

    def test_blur_suffix(self):
        img = Image.new("RGB", (100, 100))
        config = PreprocessConfig(apply_gaussian_blur=True, rotation_angles=[0])
        variants = generate_patch_variants(img, config)
        assert variants[0][1] == "orig_blur"


class TestEncodeJpeg:
    """Tests for _encode_jpeg."""

    def test_returns_bytes(self):
        img = Image.new("RGB", (10, 10))
        data = _encode_jpeg(img)
        assert isinstance(data, bytes)
        assert len(data) > 0

    def test_valid_jpeg(self):
        img = Image.new("RGB", (10, 10))
        data = _encode_jpeg(img)
        # JPEG magic bytes
        assert data[:2] == b"\xff\xd8"


class TestProcessImageToPatches:
    """Tests for process_image_to_patches (integration)."""

    def test_with_mocked_s3(self):
        mock_s3 = MagicMock()
        img = Image.new("RGB", (600, 600))

        patches = process_image_to_patches(
            img=img,
            image_id="test-img-1",
            processed_bucket="test-bucket",
            processed_prefix="test",
            s3_client=mock_s3,
        )

        assert len(patches) > 0
        for p in patches:
            assert "patch_id" in p
            assert "patch_type" in p
            assert "patch_path" in p
            assert p["patch_path"].startswith("s3://test-bucket/")

    def test_converts_rgba_to_rgb(self):
        mock_s3 = MagicMock()
        img = Image.new("RGBA", (600, 600))  # RGBA mode

        patches = process_image_to_patches(
            img=img,
            image_id="rgba-test",
            processed_bucket="bucket",
            processed_prefix="prefix",
            s3_client=mock_s3,
        )
        assert len(patches) > 0

    def test_large_image_produces_more_patches(self):
        mock_s3 = MagicMock()
        small_img = Image.new("RGB", (600, 600))
        large_img = Image.new("RGB", (2048, 2048))

        small_patches = process_image_to_patches(
            small_img, "s", "b", "p", mock_s3,
        )
        large_patches = process_image_to_patches(
            large_img, "l", "b", "p", mock_s3,
        )
        # 4x4 grid has more cells than 2x2
        assert len(large_patches) > len(small_patches)

    def test_with_real_s3(self, s3):
        """Integration test with moto S3."""
        img = Image.new("RGB", (600, 600))
        patches = process_image_to_patches(
            img=img,
            image_id="integration-test",
            processed_bucket="test-processed-bucket",
            processed_prefix="test",
            s3_client=s3,
        )
        assert len(patches) > 0

        # Verify patches were actually uploaded to S3
        for p in patches:
            uri = p["patch_path"]
            assert uri.startswith("s3://test-processed-bucket/")


class TestUploadPatchErrorHandling:
    """Tests for _upload_patch error handling."""

    def test_raises_ioerror_on_s3_failure(self):
        mock_s3 = MagicMock()
        mock_s3.put_object.side_effect = Exception("AccessDenied")
        img = Image.new("RGB", (224, 224), color="red")
        with pytest.raises(IOError, match="Failed to upload patch"):
            _upload_patch(mock_s3, "bucket", "key.jpg", img)
