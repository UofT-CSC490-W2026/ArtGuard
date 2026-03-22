"""Swin Transformer model for art authentication.

Based on: "Art Authentication with Vision Transformers" (Schaerf et al., 2023)
arXiv: 2307.03039

Key paper details implemented here:

- Swin-Tiny (28M params, ImageNet-1K) or Swin-Base (88M params, ImageNet-22K)
- Full fine-tuning of all layers (variant iii -- best performing in paper)
- He normal initialisation on the new classification head
- Binary classification output (authentic vs. contrast)
- Adam optimiser, lr=1e-4, binary cross-entropy loss
"""

import torch
import torch.nn as nn
from torchvision.models import (
    swin_t, Swin_T_Weights,
    swin_b, Swin_B_Weights,
)


def he_normal_init(module: nn.Module) -> None:
    """Apply He normal initialisation to Linear and Conv2d layers.

    Initialises weights with Kaiming normal (fan_in, relu) and sets
    biases to zero. Non-matching module types are left unchanged.

    Args:
        module: A PyTorch module (applied recursively via ``nn.Module.apply``).
    """
    if isinstance(module, (nn.Linear, nn.Conv2d)):
        nn.init.kaiming_normal_(module.weight, mode="fan_in", nonlinearity="relu")
        if module.bias is not None:
            nn.init.zeros_(module.bias)


def build_swin_model(
    variant: str = "tiny",
    pretrained: bool = True,
    num_classes: int = 1,
    dropout: float = 0.0,
) -> nn.Module:
    """Build a Swin Transformer with a He-normal initialised classification head.

    Downloads pretrained ImageNet weights (if requested), replaces the
    original 1000-class head with a new ``num_classes``-output head using
    He normal initialisation, and unfreezes all parameters for full
    fine-tuning (variant iii from the paper).

    >>> model = build_swin_model("tiny", pretrained=False)
    >>> model.head[-1].out_features
    1

    Args:
        variant:     ``"tiny"`` (Swin-Tiny, 28M params) or ``"base"``
                     (Swin-Base, 88M params).
        pretrained:  Whether to load ImageNet pretrained weights.
        num_classes: Number of output units (1 for binary sigmoid output).
        dropout:     Dropout probability before the head (0 = disabled).

    Returns:
        An ``nn.Module`` with all layers unfrozen, ready for training.

    Raises:
        ValueError: If variant is not ``"tiny"`` or ``"base"``.
    """
    variant = variant.lower()

    if variant == "tiny":
        weights = Swin_T_Weights.IMAGENET1K_V1 if pretrained else None
        model = swin_t(weights=weights)
        in_features = model.head.in_features  # 768
    elif variant == "base":
        weights = Swin_B_Weights.IMAGENET1K_V1 if pretrained else None
        model = swin_b(weights=weights)
        in_features = model.head.in_features  # 1024
    else:
        raise ValueError(f"variant must be 'tiny' or 'base', got '{variant}'")

    head_layers: list[nn.Module] = []
    if dropout > 0.0:
        head_layers.append(nn.Dropout(p=dropout))
    head_layers.append(nn.Linear(in_features, num_classes))

    model.head = nn.Sequential(*head_layers)
    model.head.apply(he_normal_init)

    for param in model.parameters():
        param.requires_grad = True

    return model


class ArtAuthenticator(nn.Module):
    """Binary art authentication model wrapping a Swin Transformer backbone.

    Provides the recommended loss function and optimiser from the paper:

    - **Loss**: BCEWithLogitsLoss (binary cross-entropy; paper Section 3.3)
    - **Optimiser**: Adam, lr=1e-4 (paper Section 3.3)

    The ``forward`` method returns raw logits (no sigmoid). Use ``predict``
    for probabilities at inference time.

    Args:
        variant:    ``"tiny"`` or ``"base"`` Swin variant.
        pretrained: Whether to load ImageNet pretrained weights.
        dropout:    Dropout probability before the classification head.
    """

    def __init__(
        self,
        variant: str = "tiny",
        pretrained: bool = True,
        dropout: float = 0.0,
    ) -> None:
        """Initialize the ArtAuthenticator with the specified Swin backbone."""
        super().__init__()
        self.backbone = build_swin_model(
            variant=variant, pretrained=pretrained, num_classes=1, dropout=dropout,
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Compute raw logits for a batch of images.

        Args:
            x: Float tensor of shape ``(B, 3, H, W)`` with values in [0, 1].
               Paper uses 224x224 patches (bicubic-downsampled from 256x256).

        Returns:
            Logits tensor of shape ``(B, 1)``.
        """
        return self.backbone(x)

    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """Compute authenticity probabilities for a batch of images.

        Values > 0.5 indicate the model considers the image authentic.

        Args:
            x: Float tensor of shape ``(B, 3, H, W)``.

        Returns:
            Probability tensor of shape ``(B, 1)`` in the range [0, 1].
        """
        with torch.no_grad():
            return torch.sigmoid(self.forward(x))

    def configure_criterion(
        self,
        imitation_weight: float = 10.0,
        use_sample_weights: bool = True,
    ) -> nn.BCEWithLogitsLoss:
        """Create the binary cross-entropy loss function.

        Paper (Section 3.2): imitation patches are weighted wim=10 in the
        standard-contrast-set experiments. Per-sample weights should be
        supplied to the loss in the training loop.

        Args:
            imitation_weight: Weight for inauthentic samples (logged when
                              use_sample_weights is True).
            use_sample_weights: Whether to log the configured weight.

        Returns:
            A ``BCEWithLogitsLoss`` instance.
        """
        if use_sample_weights:
            print(f"[ArtAuthenticator] imitation sample weight = {imitation_weight}")
        return nn.BCEWithLogitsLoss()

    def configure_optimizer(self, lr: float = 1e-4) -> torch.optim.Optimizer:
        """Create an Adam optimiser with the paper's default learning rate.

        Args:
            lr: Learning rate (default 1e-4, per paper Section 3.3).

        Returns:
            An ``Adam`` optimiser over all model parameters.
        """
        return torch.optim.Adam(self.parameters(), lr=lr)


if __name__ == "__main__":
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}\n")

    for variant in ("tiny", "base"):
        print(f"--- Swin-{variant.capitalize()} ---")
        model = ArtAuthenticator(variant=variant, pretrained=True).to(device)

        dummy = torch.randn(4, 3, 224, 224, device=device)
        logits = model(dummy)
        probs = model.predict(dummy)

        print(f"  Output shape : {logits.shape}")
        print(f"  Sample probs : {probs.squeeze().tolist()}")
        print(f"  Trainable params: "
              f"{sum(p.numel() for p in model.parameters() if p.requires_grad):,}\n")

    model = ArtAuthenticator(variant="tiny").to(device)
    criterion = model.configure_criterion(imitation_weight=10.0, use_sample_weights=True)
    optimizer = model.configure_optimizer(lr=1e-4)
    print("Criterion:", criterion)
    print("Optimizer :", optimizer)
