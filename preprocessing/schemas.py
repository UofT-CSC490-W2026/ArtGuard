from dataclasses import dataclass, field
from typing import Optional
import uuid

# We will store a user's id, username, password and email.
@dataclass
class User:
    user_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    username: str = ""
    password: str = ""  
    email: str = "" 

# We will store each inference's id, the user associated with the inference request,
# the path to the uploaded image (for debugging), the image's name, the model's
# predicted score, and supporting explanation.
@dataclass
class InferenceRecord:
    inference_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str = "" 
    image_name: Optional[str] = None   
    image_path: str = ""          
    score: float = 0.0   
    explanation: Optional[str] = None

# We will store each image's id, name, path and dimensions. We will also store it's label 
# (authentic) vs. inauthentic), sublabel (forgery vs. imitation), split (training, 
# validation, test for reproducibility), attributed creator and actual creator.
@dataclass
class ImageRecord:
    image_id: str
    image_name: str
    image_path: str
    image_width: int
    image_height: int
    label: str 
    sublabel: Optional[str] = None    
    split: str  
    attributed_creator: Optional[str] = None  
    actual_creator: Optional[str] = None      

# We will store each patch's id, path and associated image. We will also store
# it's type (is it a grid patch, or center patch), dimensions and location.
@dataclass
class PatchRecord:
    patch_id: str
    patch_path: str
    image_id: str
    patch_type: str 
    patch_x: int
    patch_y: int
    patch_width: int
    patch_height: int


