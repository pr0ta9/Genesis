#!/usr/bin/env python3
"""
Demo script showing how to use the updated inpaint_text functionality
with the new OCR JSON format.
"""

import cv2
import numpy as np
import json
from pathlib import Path

# Import the simplified inpaint text function
from src.tools.path_tools.inpaint_text import inpaint_text

def demo_with_sample_data():
    """Demonstrate inpainting with sample OCR data"""
    print("=== Demo: Using sample OCR data ===")
    
    # Load the test image
    img_path = "test.png" 
    if not Path(img_path).exists():
        print(f"Warning: {img_path} not found. Creating a blank image for demo.")
        img = np.full((400, 600, 3), 255, dtype=np.uint8)  # White background
    else:
        img = cv2.imread(img_path)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    
    # Create sample OCR data in your new format
    sample_ocr_data = [
        {
            "id": 1,
            "direction": "h",  # horizontal text
            "is_cjk_original": True,
            "is_cjk_translation": False,
            "translation": "Hello, this is a test!",
            "text": "これはテストです",
            "texts": ["これはテストです"],
            "boxes": [[[100.0, 50.0], [350.0, 50.0], [350.0, 90.0], [100.0, 90.0]]],
            "center": [225.0, 70.0]
        },
        {
            "id": 2,
            "direction": "v",  # vertical text
            "is_cjk_original": True,
            "is_cjk_translation": False,
            "translation": "World",
            "text": "世界",
            "texts": ["世界"],
            "boxes": [[[450.0, 100.0], [500.0, 100.0], [500.0, 200.0], [450.0, 200.0]]],
            "center": [475.0, 150.0]
        }
    ]
    
    # Save sample JSON for testing file loading
    with open('sample_ocr.json', 'w', encoding='utf-8') as f:
        json.dump(sample_ocr_data, f, ensure_ascii=False, indent=2)
    
    # Test 1: Direct JSON data processing
    print("Processing OCR data directly...")
    result1 = inpaint_text(
        img.copy(), 
        sample_ocr_data,
        font_size_offset=5,  # Make text slightly larger
        use_dilation_stroke=True,  # Use fast stroke rendering
        disable_font_border=False  # Keep text borders for readability
    )
    
    # Save result
    result1_bgr = cv2.cvtColor(result1, cv2.COLOR_RGB2BGR)
    cv2.imwrite('demo_result_direct.png', result1_bgr)
    print("✅ Saved result as 'demo_result_direct.png'")
    
    # Test 2: Loading from JSON file
    print("Processing OCR data from JSON file...")
    with open('sample_ocr.json', 'r', encoding='utf-8') as f:
        loaded_ocr_data = json.load(f)
    
    result2 = inpaint_text(
        img.copy(),
        loaded_ocr_data,
        font_size_offset=8,
        use_dilation_stroke=True
    )
    
    # Save result 
    result2_bgr = cv2.cvtColor(result2, cv2.COLOR_RGB2BGR)
    cv2.imwrite('demo_result_from_file.png', result2_bgr)
    print("✅ Saved result as 'demo_result_from_file.png'")

def demo_multiple_regions():
    """Demonstrate processing multiple text regions"""
    print("\n=== Demo: Multiple text regions ===")
    
    # Create a test image
    img = np.full((300, 500, 3), 240, dtype=np.uint8)  # Light gray background
    
    # Multiple text regions
    multi_region_data = [
        {
            "id": 1,
            "text": "日本語テスト",
            "translation": "Japanese Test",
            "boxes": [[[50.0, 50.0], [200.0, 50.0], [200.0, 90.0], [50.0, 90.0]]],
            "direction": "h",
            "is_cjk_original": True,
            "is_cjk_translation": False
        },
        {
            "id": 2,
            "text": "縦書き",
            "translation": "Vertical",
            "boxes": [[[400.0, 100.0], [450.0, 100.0], [450.0, 200.0], [400.0, 200.0]]],
            "direction": "v",
            "is_cjk_original": True,
            "is_cjk_translation": False
        },
        {
            "id": 3,
            "text": "English",
            "translation": "英語",
            "boxes": [[[100.0, 180.0], [300.0, 180.0], [300.0, 220.0], [100.0, 220.0]]],
            "direction": "h",
            "is_cjk_original": False,
            "is_cjk_translation": True
        }
    ]
    
    # Process multiple regions
    result = inpaint_text(
        img,
        multi_region_data,
        font_size_offset=5,
        use_dilation_stroke=True
    )
    
    # Save result
    result_bgr = cv2.cvtColor(result, cv2.COLOR_RGB2BGR) 
    cv2.imwrite('demo_result_multiple_regions.png', result_bgr)
    print("✅ Saved result as 'demo_result_multiple_regions.png'")

def print_usage_info():
    """Print usage information"""
    print("\n=== Usage Information ===")
    print("""
The updated inpaint_text.py now supports your new OCR JSON format!

Main functions:
• inpaint_text_from_json(img, ocr_data, **options) - Process JSON list directly
• inpaint_text_from_file(img, json_path, **options) - Load and process JSON file
• inpaint_text(img, text_regions, **options) - Original function with ImageText objects

Expected JSON format (list of dictionaries):
[
  {
    "id": 1,
    "direction": "v",  // "h" for horizontal, "v" for vertical
    "is_cjk_original": true,
    "is_cjk_translation": false,
    "translation": "Translated text",
    "text": "Original text",
    "texts": ["text", "segments"],
    "boxes": [[[x1, y1], [x2, y2], [x3, y3], [x4, y4]]],
    "center": [center_x, center_y]
  }
]

Key features:
• Automatic conversion from new JSON format to ImageText objects
• Preserves all original optimizations (5-10x faster rendering)
• Supports both horizontal and vertical text
• Auto-detects CJK languages and text direction
• Smart font size estimation from bounding boxes

Options:
• font_path: Path to custom font file (uses fallbacks if empty)
• font_size_offset: Add/subtract from estimated font sizes
• use_dilation_stroke: Use fast dilation-based text stroke
• disable_font_border: Remove text borders/stroke
• hyphenate: Enable text hyphenation for better layout
• show_progress: Show progress bar during processing
    """)

if __name__ == '__main__':
    print("🚀 Inpaint Text Demo - Simplified for New OCR JSON Format")
    print("=" * 60)
    
    try:
        demo_with_sample_data()
        demo_multiple_regions()
        print_usage_info()
        
        print("\n🎉 Demo completed successfully!")
        print("Check the generated PNG files to see the results.")
        
    except Exception as e:
        print(f"❌ Demo failed with error: {e}")
        import traceback
        traceback.print_exc()
