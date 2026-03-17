"""
model.py — Art Authentication with Swin Transformers
Based on: "Art Authentication with Vision Transformers" (Schaerf et al., 2023)
arXiv: 2307.03039

Key paper details implemented here:
- Swin-Tiny (28M params, ImageNet-1K) or Swin-Base (88M params, ImageNet-22K)
- Full fine-tuning of all layers (variant iii — best performing in paper)
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
    """Initialise linear/conv weights with He normal, biases to zero."""
    if isinstance(module, (nn.Linear, nn.Conv2d)):
        nn.init.kaiming_normal_(module.weight, mode="fan_in", nonlinearity="relu")
        if module.bias is not None:
            nn.init.zeros_(module.bias)

def build_swin_model(variant: str = "tiny", pretrained: bool = True, num_classes: int = 1, dropout: float = 0.0) -> nn.Module:
    """
    Download a pretrained Swin Transformer and replace its classification head
    with a binary (or N-class) dense layer, He-normal initialised.

    Args:
        variant    : "tiny"  → Swin-Tiny  (ImageNet-1K,  28M params)
                     "base"  → Swin-Base  (ImageNet-22K, 88M params)
        pretrained : Use ImageNet pretrained weights (recommended).
        num_classes: 1  → sigmoid binary output  (paper task)
                     N  → softmax N-class output
        dropout    : Optional dropout before the head (0 = disabled).

    Returns:
        nn.Module ready for training (all layers unfrozen).
    """
    variant = variant.lower()

    # ---- 1. Load backbone ------------------------------------------------
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

    # ---- 2. Replace classification head ----------------------------------
    # Paper: "the top was defined as a randomly-initialised dense layer"
    # with He-normal initialisation.
    head_layers: list[nn.Module] = []

    if dropout > 0.0:
        head_layers.append(nn.Dropout(p=dropout))

    head_layers.append(nn.Linear(in_features, num_classes))

    model.head = nn.Sequential(*head_layers)

    # Apply He-normal init to the new head only
    model.head.apply(he_normal_init)

    # ---- 3. Unfreeze all layers (variant iii from the paper) -------------
    for param in model.parameters():
        param.requires_grad = True

    return model


class ArtAuthenticator(nn.Module):
    """
    Thin wrapper around the Swin backbone that also exposes the
    recommended loss function and optimiser from the paper.

    Loss : BCEWithLogitsLoss  (binary cross-entropy; paper Section 3.3)
    Optim: Adam, lr=1e-4      (paper Section 3.3)

    Forward output is a raw logit (no sigmoid) — use predict() for
    probabilities at inference time.
    """

    def __init__(self, variant: str = "tiny", pretrained: bool = True, dropout: float = 0.0,) -> None:
        super().__init__()
        self.backbone = build_swin_model(variant=variant, pretrained=pretrained, num_classes=1, dropout=dropout)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """
        Args:
            x: (B, 3, H, W) float tensor, values in [0, 1].
               Paper uses 224×224 (bicubic-downsampled from 256×256 patches).
        Returns:
            logits: (B, 1)
        """
        return self.backbone(x)

    def predict(self, x: torch.Tensor) -> torch.Tensor:
        """Return probabilities in [0, 1]. Values > 0.5 → authentic."""
        with torch.no_grad():
            return torch.sigmoid(self.forward(x))

    def configure_criterion(self, imitation_weight: float = 10.0, use_sample_weights: bool = True) -> nn.BCEWithLogitsLoss:
        """
        Binary cross-entropy loss.

        Paper (Section 3.2): imitation patches are weighted wim=10 in the
        standard-contrast-set experiments. Set use_sample_weights=False
        (wim=1) for the refined-contrast-set experiments.

        Pass the returned criterion to your training loop and supply
        per-sample weights via the `weight` argument if needed.
        """
        if use_sample_weights:
            print(f"[ArtAuthenticator] imitation sample weight = {imitation_weight}")
        return nn.BCEWithLogitsLoss()

    def configure_optimizer(self, lr: float = 1e-4) -> torch.optim.Optimizer:
        """Adam optimiser, lr=1e-4 (paper Section 3.3)."""
        return torch.optim.Adam(self.parameters(), lr=lr)


if __name__ == "__main__":
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Using device: {device}\n")

    for variant in ("tiny", "base"):
        print(f"--- Swin-{variant.capitalize()} ---")
        model = ArtAuthenticator(variant=variant, pretrained=True).to(device)

        dummy = torch.randn(4, 3, 224, 224, device=device)
        logits = model(dummy)
        probs  = model.predict(dummy)

        print(f"  Output shape : {logits.shape}")
        print(f"  Sample probs : {probs.squeeze().tolist()}")
        print(f"  Trainable params: "
              f"{sum(p.numel() for p in model.parameters() if p.requires_grad):,}\n")

    model = ArtAuthenticator(variant="tiny").to(device)
    criterion = model.configure_criterion(imitation_weight=10.0, use_sample_weights=True)
    optimizer = model.configure_optimizer(lr=1e-4)
    print("Criterion:", criterion)
    print("Optimizer :", optimizer)