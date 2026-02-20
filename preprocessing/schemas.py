from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import time, uuid

# We will store a user's id, username, password and email.
@dataclass
class User:
    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    username: str = ""
    password: str = ""  
    email: str = "" 

# We will store each inference's id, the user associated with the inference request,
# the path to the uploaded image (for debugging), the image's name, the model's
# predicted score, and supporting explanation.
@dataclass
class InferenceRecord:
    inference_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    user_id: str = "" 
    image_name: Optional[str] = None   
    image_path: str = ""          
    score: float = 0.0   
    explanation: Optional[str] = None

# We will store each image's id, name, path and dimensions. We will also store it's label 
# (authentic) vs. inauthentic), sublabel (original vs. forgery vs. imitation), run, fold and 
# dataset information for split reproducibility, attributed creator and actual creator.
@dataclass
class ImageRecord:
    image_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    image_name: str = ""
    image_path: str = ""
    image_width: int = 0
    image_height: int = 0
    label: Optional[str] = None         
    sublabel: Optional[str] = None       
    run_id: Optional[str] = None
    dataset_version: Optional[str] = None
    fold_id: Optional[int] = None 
    attributed_creator: Optional[str] = None  
    actual_creator: Optional[str] = None      

# We will store each patch's id, path and associated image. We will also store
# it's type (is it a grid patch, or center patch), dimensions and location.
@dataclass
class PatchRecord:
    patch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    patch_path: str = ""
    image_id: str = ""
    patch_type: str = ""
    patch_x: int = 0
    patch_y: int = 0
    patch_width: int = 0
    patch_height: int = 0

# We will store each run's model artifacts (i.e., best weights and hyperparameter config.), 
# information to reproduce the data splits and averaged metrics across folds.
@dataclass
class RunRecord:
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    status: str = "running"     
    dataset_version: str = ""  
    modal_volume_path: Optional[str] = None
    best_config_id: Optional[str] = None
    k_folds: int = 5
    stratify_on: str = "sublabel"
    outer_split_seed: int = 17
    inner_split_seed: int = 99
    mean_accuracy: Optional[float] = None
    mean_auc: Optional[float] = None
    mean_f1: Optional[float] = None
    mean_precision: Optional[float] = None
    mean_recall: Optional[float] = None
    std_accuracy: Optional[float] = None
    std_auc: Optional[float] = None
    std_f1: Optional[float] = None
    std_precision: Optional[float] = None
    std_recall: Optional[float] = None
    
# We will store each hyperparameter combination in a fold, including dataset information
# for reproducibility, and whether this hyperparameter combination is the best in the
# fold (If it is, provide the corresponding model weights stored in a modal volume). 
@dataclass
class ConfigRecord:
    config_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: int = field(default_factory=lambda: int(time.time() * 1000))
    run_id: str = ""
    dataset_version: str = ""
    fold_id: int = 0
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    best_epoch: Optional[int] = None
    best_val: Optional[float] = None
    early_stopped: bool = False
    is_best_in_fold: bool = False
    modal_volume_path: Optional[str] = None 

