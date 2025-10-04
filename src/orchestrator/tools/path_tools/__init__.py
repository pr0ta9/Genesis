"""
Path tools package exposing decorated tools for auto-discovery.
"""

# Controlled import order to prevent CUDA conflicts:
# Import PaddleOCR-based tools first, then PyTorch-based tools

# # 1. OCR tools first (PaddleOCR claims CUDA)
# from .ocr import image_ocr, pdf_ocr

# # 2. Translation (uses LLM, no direct GPU)
# from .translate import translate

# # 3. PyTorch-based tools last (after PaddleOCR is initialized)
# from .erase import erase
# from .inpaint_text import inpaint_text

# # 4. Other tools
# from .denoise import denoise

# __all__ = [
#     'image_ocr', 'pdf_ocr', 'translate', 'erase', 
#     'inpaint_text', 'denoise'
# ]


