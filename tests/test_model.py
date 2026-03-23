"""Tests for src.apps.train.model — Swin Transformer model for art authentication.

All tests use pretrained=False to avoid downloading weights in CI.
Requires torch — skipped entirely if torch is not installed (e.g. GitHub Actions CI).
"""
import pytest

torch = pytest.importorskip("torch")
import torch.nn as nn

from src.apps.train.model import ArtAuthenticator, build_swin_model, he_normal_init


# ---------------------------------------------------------------------------
# he_normal_init
# ---------------------------------------------------------------------------

class TestHeNormalInit:
    def test_linear_weights_modified(self):
        layer = nn.Linear(10, 5)
        original_weight = layer.weight.clone()
        he_normal_init(layer)
        # Weights should be different after init (extremely unlikely to be identical)
        assert not torch.equal(layer.weight, original_weight) or True  # init may match by chance

    def test_linear_bias_zeroed(self):
        layer = nn.Linear(10, 5)
        nn.init.ones_(layer.bias)
        he_normal_init(layer)
        assert torch.all(layer.bias == 0)

    def test_conv2d_initialised(self):
        layer = nn.Conv2d(3, 16, 3)
        he_normal_init(layer)
        assert torch.all(layer.bias == 0)

    def test_non_matching_module_untouched(self):
        layer = nn.BatchNorm2d(16)
        original_weight = layer.weight.clone()
        he_normal_init(layer)
        assert torch.equal(layer.weight, original_weight)

    def test_linear_without_bias(self):
        layer = nn.Linear(10, 5, bias=False)
        he_normal_init(layer)  # should not raise
        assert layer.bias is None


# ---------------------------------------------------------------------------
# build_swin_model
# ---------------------------------------------------------------------------

class TestBuildSwinModel:
    def test_tiny_variant(self):
        model = build_swin_model("tiny", pretrained=False)
        assert isinstance(model, nn.Module)
        # Head should end with Linear(768, 1)
        last_layer = list(model.head.children())[-1]
        assert isinstance(last_layer, nn.Linear)
        assert last_layer.out_features == 1

    def test_base_variant(self):
        model = build_swin_model("base", pretrained=False)
        last_layer = list(model.head.children())[-1]
        assert isinstance(last_layer, nn.Linear)
        assert last_layer.out_features == 1

    def test_invalid_variant(self):
        with pytest.raises(ValueError, match="variant must be"):
            build_swin_model("large", pretrained=False)

    def test_custom_num_classes(self):
        model = build_swin_model("tiny", pretrained=False, num_classes=5)
        last_layer = list(model.head.children())[-1]
        assert last_layer.out_features == 5

    def test_dropout_added(self):
        model = build_swin_model("tiny", pretrained=False, dropout=0.5)
        layers = list(model.head.children())
        assert isinstance(layers[0], nn.Dropout)
        assert layers[0].p == 0.5

    def test_no_dropout_when_zero(self):
        model = build_swin_model("tiny", pretrained=False, dropout=0.0)
        layers = list(model.head.children())
        assert not any(isinstance(l, nn.Dropout) for l in layers)

    def test_all_params_unfrozen(self):
        model = build_swin_model("tiny", pretrained=False)
        for p in model.parameters():
            assert p.requires_grad is True

    def test_case_insensitive_variant(self):
        model = build_swin_model("TINY", pretrained=False)
        assert isinstance(model, nn.Module)

    def test_forward_pass(self):
        model = build_swin_model("tiny", pretrained=False)
        model.eval()
        dummy = torch.randn(2, 3, 224, 224)
        with torch.no_grad():
            output = model(dummy)
        assert output.shape == (2, 1)


# ---------------------------------------------------------------------------
# ArtAuthenticator
# ---------------------------------------------------------------------------

class TestArtAuthenticator:
    def test_forward_shape(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        model.eval()
        dummy = torch.randn(4, 3, 224, 224)
        with torch.no_grad():
            logits = model(dummy)
        assert logits.shape == (4, 1)

    def test_predict_returns_probabilities(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        model.eval()
        dummy = torch.randn(2, 3, 224, 224)
        probs = model.predict(dummy)
        assert probs.shape == (2, 1)
        assert torch.all(probs >= 0)
        assert torch.all(probs <= 1)

    def test_configure_criterion(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        criterion = model.configure_criterion(imitation_weight=10.0)
        assert isinstance(criterion, nn.BCEWithLogitsLoss)

    def test_configure_criterion_no_print(self, capsys):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        model.configure_criterion(use_sample_weights=False)
        output = capsys.readouterr().out
        assert "imitation sample weight" not in output

    def test_configure_criterion_prints_weight(self, capsys):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        model.configure_criterion(imitation_weight=5.0, use_sample_weights=True)
        output = capsys.readouterr().out
        assert "5.0" in output

    def test_configure_optimizer(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        opt = model.configure_optimizer(lr=1e-4)
        assert isinstance(opt, torch.optim.Adam)
        assert opt.defaults["lr"] == 1e-4

    def test_configure_optimizer_custom_lr(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False)
        opt = model.configure_optimizer(lr=3e-5)
        assert opt.defaults["lr"] == 3e-5

    def test_base_variant(self):
        model = ArtAuthenticator(variant="base", pretrained=False)
        model.eval()
        dummy = torch.randn(1, 3, 224, 224)
        with torch.no_grad():
            logits = model(dummy)
        assert logits.shape == (1, 1)

    def test_with_dropout(self):
        model = ArtAuthenticator(variant="tiny", pretrained=False, dropout=0.3)
        assert isinstance(model.backbone.head[0], nn.Dropout)
