"""
Shared training hyperparameters (no Modal imports — safe to import from the API server).
"""

DEFAULT_CONFIG = dict(
    num_epochs=100,
    batch_size=32,
    lr=1e-4,
    early_stop_patience=20,
    early_stop_min_delta=1e-3,
    imitation_weight=10.0,
    val_split=0.1,
    num_workers=4,
)

MODAL_TRAINING_APP = "artguard-training"
MODAL_EVAL_APP = "artguard-evaluation"
