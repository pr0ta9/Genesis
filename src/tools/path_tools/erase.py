#!/usr/bin/env python3
"""
Text removal using LaMa inpainting model - ImageText format compatible

This version works directly with ImageText objects from ocr_optimized.py
instead of the old bbox dictionary format.
"""

import json
import os
import sys
import cv2
import numpy as np
import torch
from urllib.parse import urlparse
from torch.hub import download_url_to_file, get_dir
import time
from ...path import pathtool, StructuredData, ImageFile

# Default model URL
LAMA_MODEL_URL = os.environ.get(
    "LAMA_MODEL_URL",
    "https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt",
)

def download_model(url):
    """Download model from URL and cache it"""
    parts = urlparse(url)
    hub_dir = get_dir()
    model_dir = os.path.join(hub_dir, "checkpoints")
    if not os.path.isdir(model_dir):
        os.makedirs(os.path.join(model_dir, "hub", "checkpoints"))
    filename = os.path.basename(parts.path)
    cached_file = os.path.join(model_dir, filename)
    if not os.path.exists(cached_file):
        sys.stderr.write('Downloading: "{}" to {}\n'.format(url, cached_file))
        hash_prefix = None
        download_url_to_file(url, cached_file, hash_prefix, progress=True)
    return cached_file

def ceil_modulo(x, mod):
    """Calculate ceiling modulo"""
    if x % mod == 0:
        return x
    return (x // mod + 1) * mod

def pad_img_to_modulo(img, mod):
    """Pad image to be divisible by mod"""
    h, w = img.shape[:2]
    target_h = ceil_modulo(h, mod)
    target_w = ceil_modulo(w, mod)
    
    if target_h == h and target_w == w:
        return img
    
    # Pad using reflection
    pad_h = target_h - h
    pad_w = target_w - w
    
    # Create padded image
    padded = np.pad(img, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')
    return padded

def tensor_to_image(tensor):
    """Convert PyTorch tensor to numpy image"""
    if isinstance(tensor, torch.Tensor):
        tensor = tensor.detach().cpu().numpy()
    
    # Handle different tensor shapes
    if len(tensor.shape) == 4:  # Batch dimension
        tensor = tensor[0]
    
    if len(tensor.shape) == 3 and tensor.shape[0] in [1, 3]:  # CHW format
        tensor = np.transpose(tensor, (1, 2, 0))
    
    # Convert to 0-255 range
    if tensor.max() <= 1.0:
        tensor = tensor * 255.0
    
    return tensor.astype(np.uint8)

def run_lama_model(model, image, mask, device='cuda'):
    """Run LaMa inpainting model"""
    h, w = image.shape[:2]
    
    # Pad image and mask to be divisible by 8
    image_padded = pad_img_to_modulo(image, 8)
    mask_padded = pad_img_to_modulo(mask[..., np.newaxis], 8)[..., 0]
    
    # Convert to tensors
    image_tensor = torch.from_numpy(image_padded).permute(2, 0, 1).unsqueeze(0).float() / 255.0
    mask_tensor = torch.from_numpy(mask_padded).unsqueeze(0).unsqueeze(0).float() / 255.0
    
    # Move to device
    image_tensor = image_tensor.to(device)
    mask_tensor = mask_tensor.to(device)
    
    # Run model
    with torch.no_grad():
        start_time = time.time()
        result = model(image_tensor, mask_tensor)
        elapsed = (time.time() - start_time) * 1000
        print(f"LaMa processing time: {elapsed:.1f}ms")
    
    # Convert back to image
    result_image = tensor_to_image(result)
    
    # Crop back to original size
    result_image = result_image[:h, :w]
    
    return result_image

def create_mask_from_imagetext_list(image_shape, text_regions, padding=5):
    """
    Create a binary mask from ImageText objects (compatible with old format)
    
    Args:
        image_shape: (height, width) of the image
        text_regions: List of ImageText objects
        padding: Additional padding around bounding boxes
        
    Returns:
        Binary mask as numpy array
    """
    height, width = image_shape[:2]
    mask = np.zeros((height, width), dtype=np.uint8)
    
    for text_region in text_regions:
        # Get points from ImageText object
        if hasattr(text_region, 'points') and text_region.points is not None:
            points = text_region.points
            
            # Ensure points is a numpy array
            if not isinstance(points, np.ndarray):
                points = np.array(points)
            
            # Handle different point formats
            if len(points.shape) == 1:
                points = points.reshape(-1, 2)
            
            # Create polygon mask - USE SAME METHOD AS OLD VERSION
            if len(points) >= 3:  # Need at least 3 points for a polygon
                # Convert to bounding rectangle (like old version)
                x_coords = points[:, 0]
                y_coords = points[:, 1]
                
                x_min = max(0, int(np.min(x_coords)) - padding)
                y_min = max(0, int(np.min(y_coords)) - padding)
                x_max = min(width, int(np.max(x_coords)) + padding)
                y_max = min(height, int(np.max(y_coords)) + padding)
                
                # Fill rectangle (like old version did)
                mask[y_min:y_max, x_min:x_max] = 255
    
    return mask

@pathtool(input="bbox_data", output="return")
def erase(bbox_data: StructuredData, input_path: ImageFile, output_path: ImageFile, device: str = 'cuda', padding: int = 10) -> ImageFile:
    """
    Remove text from image using LaMa inpainting model - ImageText compatible version
    
    Args:
        bbox_data: bbox data containing bboxes/text regions
        input_path: Path to original input image (from path metadata system)
        output_path: Path for output image
        device: Device to run model on ('cuda' or 'cpu')
        padding: Additional padding around text regions
        
    Returns:
        Path to output image
    """
    
    # Check if image exists
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Image file not found: {input_path}")
    
    # Load image
    image = cv2.imread(input_path)
    if image is None:
        raise ValueError(f"Could not load image from {input_path}")
    
    original_shape = image.shape
    
    # OCR result is always a list of bbox dictionaries from ocr.py
    # Convert bboxes to ImageText-like objects for mask creation
    text_regions = []
    
    for bbox in bbox_data:
        if 'boxes' in bbox and bbox['boxes']:
            # Create ImageText-like objects from bbox data
            for box_points in bbox['boxes']:
                class TextRegionForErase:
                    def __init__(self, points):
                        self.points = np.array(points)
                
                text_regions.append(TextRegionForErase(box_points))
    
    if not text_regions:
        print("No text regions found, copying original image")
        cv2.imwrite(output_path, image)
        return output_path
    
    # Create mask from ImageText objects
    mask = create_mask_from_imagetext_list(original_shape, text_regions, padding)
    
    print(f"Created mask with {np.sum(mask > 0)} pixels to inpaint")
    print(f"Image shape: {original_shape}")
    print(f"Found {len(text_regions)} text regions to remove")
    
    # Debug info available if needed (can be enabled for troubleshooting)
    
    # Initialize LaMa model
    print(f"Initializing LaMa model on {device}...")
    if device == 'cuda' and not torch.cuda.is_available():
        print("CUDA not available, falling back to CPU")
        device = 'cpu'
    
    # Download and load model
    model_path = download_model(LAMA_MODEL_URL)
    model = torch.jit.load(model_path, map_location=device)
    model.eval()
    
    # Run inpainting
    print("Processing image with LaMa model...")
    result_image = run_lama_model(model, image, mask, device)
    
    # Ensure output directory exists
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    # Save result
    cv2.imwrite(output_path, result_image)
    print(f"Text removal completed. Result saved to: {output_path}")
    
    return output_path
