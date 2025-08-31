import numpy as np
from typing import List, Dict, Optional
from dataclasses import dataclass
from collections import Counter
import cv2
import os

from .object_types.image_text import ImageText
from ...path import pathtool, ImageFile, DocumentFile, StructuredData
from paddleocr import PaddleOCR

# Configuration with sensible defaults
DEFAULT_CONFIG = {
    "merge": {
        "aspect_ratio_tolerance": 1.3,
        "font_size_tolerance": 2.0,
        "char_gap_tolerance": 1.0,
        "char_gap_tolerance2": 1.0,
        "connection_gap_discard": 2.0,
        "ratio": 1.9,
        "split_gamma": 0.5,
        "split_sigma": 2.0,
        "min_confidence": 0.5
    }
}

@dataclass
class TextRegion:
    """Represents a merged text region containing multiple ImageText objects"""
    texts: List[ImageText]
    
    @property
    def text(self) -> str:
        return ' '.join(img_text.text for img_text in self.texts if img_text.text)
    
    @property
    def text_list(self) -> List[str]:
        return [img_text.text for img_text in self.texts]
    
    @property
    def center(self) -> np.ndarray:
        all_points = np.vstack([img_text.points for img_text in self.texts])
        return np.mean(all_points, axis=0)
    
    @property
    def direction(self) -> str:
        dirs = [img_text.auto_direction for img_text in self.texts]
        return Counter(dirs).most_common(1)[0][0] if dirs else 'h'
    
    def get_merged_box(self) -> np.ndarray:
        """Get minimum area rectangle containing all text boxes"""
        all_points = np.vstack([img_text.points for img_text in self.texts])
        rect = cv2.minAreaRect(all_points)
        return cv2.boxPoints(rect)
    
    def to_imagetext(self) -> ImageText:
        """Convert merged region to a single ImageText object"""
        merged_box = self.get_merged_box()
        
        # Calculate merged properties
        avg_font_size = int(np.mean([t.font_size for t in self.texts]))
        avg_color = tuple(int(np.mean([t.color[i] for t in self.texts])) for i in range(3))
        
        return ImageText(
            text=self.text,
            translation='',  # Will be filled by translation
            score=np.mean([t.score for t in self.texts]),
            points=merged_box,
            font_size=avg_font_size,
            color=avg_color,
            direction=self.direction
        )

class TextMerger:
    """Optimized text merging using ImageText objects"""
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = (config or {}).get('merge', DEFAULT_CONFIG['merge'])
    
    def can_merge(self, text_a: ImageText, text_b: ImageText) -> bool:
        """Determine if two ImageText objects should be merged - EXACT MATCH to TextBox logic"""
        cfg = self.config
        char_size = min(text_a.ocr_font_size, text_b.ocr_font_size)
        distance = text_a.distance_to(text_b)
        
        # Basic distance check
        if distance > cfg['connection_gap_discard'] * char_size:
            return False
        
        # Font size compatibility
        font_ratio = max(text_a.ocr_font_size, text_b.ocr_font_size) / char_size
        if font_ratio > cfg['font_size_tolerance']:
            return False
        
        # Aspect ratio compatibility
        if (text_a.aspect_ratio > cfg['aspect_ratio_tolerance'] and 
            text_b.aspect_ratio < 1 / cfg['aspect_ratio_tolerance']):
            return False
        if (text_b.aspect_ratio > cfg['aspect_ratio_tolerance'] and 
            text_a.aspect_ratio < 1 / cfg['aspect_ratio_tolerance']):
            return False
        
        # Special handling for axis-aligned boxes
        if text_a.is_axis_aligned and text_b.is_axis_aligned:
            return self._check_aligned_merge(text_a, text_b, char_size)
        
        # Default: merge if close enough
        return distance < char_size * cfg['char_gap_tolerance']
    

    
    def _check_aligned_merge(self, text_a: ImageText, text_b: ImageText, char_size: float) -> bool:
        """Check merge conditions for axis-aligned text"""
        cfg = self.config
        bbox_a, bbox_b = text_a.bbox, text_b.bbox
        distance = text_a.distance_to(text_b)
        
        if distance >= char_size * cfg['char_gap_tolerance']:
            return False
        
        # Check center alignment
        center_a_x = bbox_a['x'] + bbox_a['w'] / 2
        center_b_x = bbox_b['x'] + bbox_b['w'] / 2
        if abs(center_a_x - center_b_x) < cfg['char_gap_tolerance2']:
            return True
        
        # Check incompatible orientations
        ratio = cfg['ratio']
        if (bbox_a['w'] > bbox_a['h'] * ratio and bbox_b['h'] > bbox_b['w'] * ratio):
            return False
        if (bbox_b['w'] > bbox_b['h'] * ratio and bbox_a['h'] > bbox_a['w'] * ratio):
            return False
        
        # Horizontal text alignment
        if bbox_a['w'] > bbox_a['h'] * ratio or bbox_b['w'] > bbox_b['h'] * ratio:
            tolerance = char_size * cfg['char_gap_tolerance2']
            return (abs(bbox_a['x'] - bbox_b['x']) < tolerance or
                   abs((bbox_a['x'] + bbox_a['w']) - (bbox_b['x'] + bbox_b['w'])) < tolerance)
        
        # Vertical text alignment
        if bbox_a['h'] > bbox_a['w'] * ratio or bbox_b['h'] > bbox_b['w'] * ratio:
            tolerance = char_size * cfg['char_gap_tolerance2']
            return (abs(bbox_a['y'] - bbox_b['y']) < tolerance or
                   abs((bbox_a['y'] + bbox_a['h']) - (bbox_b['y'] + bbox_b['h'])) < tolerance)
        
        return False
    
    def merge_texts(self, texts: List[ImageText]) -> List[TextRegion]:
        """Merge ImageText objects into regions using connected components"""
        if not texts:
            return []
        
        # Build adjacency matrix
        n = len(texts)
        adjacency = np.zeros((n, n), dtype=bool)
        
        for i in range(n):
            for j in range(i + 1, n):
                if self.can_merge(texts[i], texts[j]):
                    adjacency[i, j] = adjacency[j, i] = True
        
        # Find connected components
        visited = np.zeros(n, dtype=bool)
        regions = []
        
        for i in range(n):
            if not visited[i]:
                # BFS to find connected component
                component = []
                queue = [i]
                visited[i] = True
                
                while queue:
                    curr = queue.pop(0)
                    component.append(curr)
                    
                    for j in range(n):
                        if adjacency[curr, j] and not visited[j]:
                            visited[j] = True
                            queue.append(j)
                
                # Split component if necessary
                split_groups = self._split_if_needed(texts, component)
                
                for group in split_groups:
                    group_texts = [texts[idx] for idx in group]
                    # Sort texts within region
                    group_texts = self._sort_texts_in_region(group_texts)
                    regions.append(TextRegion(group_texts))
        
        return regions
    
    def _split_if_needed(self, texts: List[ImageText], indices: List[int]) -> List[List[int]]:
        """Split a component if gaps are too large"""
        if len(indices) <= 1:
            return [indices]
        
        if len(indices) == 2:
            idx0, idx1 = indices
            distance = texts[idx0].distance_to(texts[idx1])
            font_size = max(texts[idx0].ocr_font_size, texts[idx1].ocr_font_size)
            
            gamma = self.config['split_gamma']
            if distance < (1 + gamma) * font_size:
                return [indices]
            return [[idx0], [idx1]]
        
        # For larger groups, use distance-based clustering
        return self._cluster_by_distance(texts, indices)
    
    def _cluster_by_distance(self, texts: List[ImageText], indices: List[int]) -> List[List[int]]:
        """Cluster texts based on pairwise distances"""
        if len(indices) <= 2:
            return [indices]
        
        # Calculate pairwise distances
        n = len(indices)
        distances = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                dist = texts[indices[i]].distance_to(texts[indices[j]])
                distances[i, j] = distances[j, i] = dist
        
        # Find distance statistics
        upper_triangle = distances[np.triu_indices(n, k=1)]
        if len(upper_triangle) == 0:
            return [indices]
        
        mean_dist = np.mean(upper_triangle)
        std_dist = np.std(upper_triangle) if len(upper_triangle) > 1 else 0
        max_dist = np.max(upper_triangle)
        
        avg_font = np.mean([texts[idx].ocr_font_size for idx in indices])
        gamma = self.config['split_gamma']
        sigma = self.config['split_sigma']
        
        # Check if should keep together
        threshold = max(mean_dist + sigma * std_dist, avg_font * (1 + gamma))
        if max_dist <= threshold or std_dist < 0.3 * avg_font + 5:
            return [indices]
        
        # Split at largest gap
        max_i, max_j = np.unravel_index(np.argmax(distances), distances.shape)
        
        # Create two groups based on closer distances
        group1, group2 = [indices[max_i]], [indices[max_j]]
        for k, idx in enumerate(indices):
            if k not in [max_i, max_j]:
                dist1 = distances[k, max_i]
                dist2 = distances[k, max_j]
                if dist1 <= dist2:
                    group1.append(idx)
                else:
                    group2.append(idx)
        
        # Recursively split if needed
        result = []
        for group in [group1, group2]:
            if len(group) > 1:
                result.extend(self._split_if_needed(texts, group))
            elif group:
                result.append(group)
        
        return result
    
    def _sort_texts_in_region(self, texts: List[ImageText]) -> List[ImageText]:
        """Sort texts within a region based on reading order"""
        if not texts:
            return texts
        
        # Determine primary direction
        directions = [text.auto_direction for text in texts]
        primary_dir = Counter(directions).most_common(1)[0][0] if directions else 'h'
        
        if primary_dir == 'h':
            # Horizontal: sort top to bottom, then left to right
            return sorted(texts, key=lambda t: (t.center[1], t.center[0]))
        else:
            # Vertical: sort right to left, then top to bottom
            return sorted(texts, key=lambda t: (-t.center[0], t.center[1]))

def _is_cjk_text(text: str) -> bool:
    """Check if text contains CJK (Chinese, Japanese, Korean) characters"""
    if not text:
        return False
    for char in text:
        # Unicode ranges for CJK characters
        if ('\u4e00' <= char <= '\u9fff' or  # CJK Unified Ideographs
            '\u3040' <= char <= '\u309f' or  # Hiragana
            '\u30a0' <= char <= '\u30ff' or  # Katakana
            '\uac00' <= char <= '\ud7af'):   # Hangul
            return True
    return False

def _ocr_internal(input_path: str, config: Optional[Dict] = None) -> StructuredData:
    """Internal OCR function shared by pdf_ocr and image_ocr"""
    config = config or DEFAULT_CONFIG
    
    # Validate input
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Input file not found: {input_path}")
    
    print(f"Processing: {input_path}")
    
    # Step 1: Run PaddleOCR
    print("Initializing PaddleOCR...")
    ocr_engine = PaddleOCR(
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        ocr_version="PP-OCRv5",
    )
    
    result = ocr_engine.predict(input=input_path)
    
    # Extract OCR results directly from PaddleOCR result objects
    paddle_data = {
        'dt_polys': [],
        'rec_texts': [],
        'rec_scores': []
    }
    
    # Process each result page
    for res in result:
        if hasattr(res, 'dt_polys') and hasattr(res, 'rec_texts') and hasattr(res, 'rec_scores'):
            paddle_data['dt_polys'].extend(res.dt_polys if res.dt_polys else [])
            paddle_data['rec_texts'].extend(res.rec_texts if res.rec_texts else [])
            paddle_data['rec_scores'].extend(res.rec_scores if res.rec_scores else [])
    
    # Create ImageText objects (unified class!)
    min_conf = config.get('merge', {}).get('min_confidence', 0.5)
    texts = []
    
    dt_polys = paddle_data.get('dt_polys', [])
    rec_texts = paddle_data.get('rec_texts', [])
    rec_scores = paddle_data.get('rec_scores', [])
    
    for poly, text, score in zip(dt_polys, rec_texts, rec_scores):
        if score > min_conf:
            # Create ImageText - font_size will be calculated dynamically via ocr_font_size property
            texts.append(ImageText(
                text=text,
                score=score,
                points=poly
                # Note: No static font_size - using dynamic ocr_font_size property instead
            ))
    
    print(f"Created {len(texts)} ImageText objects from {len(dt_polys)} detections")
    
    # Step 2: Merge text using optimized merger
    print("\nMerging text boxes...")
    
    merger = TextMerger(config)
    regions = merger.merge_texts(texts)
    
    # Step 3: Process results (metadata only)
    
    # Create bboxes array in the expected format
    bboxes = []
    for i, region in enumerate(regions):
        bboxes.append({
            'id': i + 1,
            'direction': region.direction,
            'is_cjk_original': _is_cjk_text(region.text),
            'is_cjk_translation': False,
            'translation': '',
            'text': region.text,
            'texts': region.text_list,
            'boxes': [text.points.tolist() for text in region.texts],
            'center': region.center.tolist()
        })
    
    # Print summary
    print("\n=== OCR Summary ===")
    print(f"Original boxes: {len(dt_polys)}")
    print(f"Merged regions: {len(regions)}")
    reduction_ratio = (1 - len(regions)/len(dt_polys))*100 if dt_polys else 0
    print(f"Reduction: {reduction_ratio:.1f}%")
    print(f"✨ Returning {len(bboxes)} bboxes")
    
    return bboxes


@pathtool(input="input_path", output="return")
def pdf_ocr(input_path: DocumentFile, config: Optional[Dict] = None) -> StructuredData:
    """
    OCR function specifically for PDF files
    
    Args:
        input_path: Path to input PDF file
        config: Optional configuration dictionary
        
    Returns:
        StructuredData containing OCR results as bboxes array
    """
    # Validate that the file is actually a PDF
    if not input_path.lower().endswith('.pdf'):
        raise ValueError(f"pdf_ocr expects PDF files, got: {input_path}")
    
    return _ocr_internal(input_path, config)


@pathtool(input="input_path", output="return")
def image_ocr(input_path: ImageFile, config: Optional[Dict] = None) -> StructuredData:
    """
    OCR function specifically for image files
    
    Args:
        input_path: Path to input image file
        config: Optional configuration dictionary
        
    Returns:
        StructuredData containing OCR results as bboxes array
    """
    
    return _ocr_internal(input_path, config)