import numpy as np
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass, field

@dataclass
class ImageText:
    """Unified text class for OCR detection, merging, and overlay rendering"""
    
    # Core text data
    text: str = ''
    translation: str = ''
    score: float = 1.0
    
    # Geometry - support both polygon and rectangular representations
    points: Optional[np.ndarray] = None  # Polygon points (OCR output)
    xyxy: Optional[List[int]] = None     # Simple rectangle [x1,y1,x2,y2]
    
    # Rendering properties (overlay-specific)
    font_size: int = 32
    color: Tuple[int, int, int] = (0, 0, 0)
    stroke_color: Tuple[int, int, int] = (255, 255, 255)
    alignment: str = 'center'
    target_lang: str = 'en'
    
    # Direction and orientation
    direction: str = 'auto'  # 'h', 'v', 'auto', 'horizontal', 'vertical'
    # Note: angle is now a calculated property, not a stored field
    
    # Cached properties
    _bbox: Optional[Dict] = field(default=None, init=False, repr=False)
    _center: Optional[np.ndarray] = field(default=None, init=False, repr=False)
    
    def __post_init__(self):
        """Initialize computed properties"""
        # Ensure we have at least one coordinate representation
        if self.points is not None:
            self.points = np.array(self.points, dtype=np.float32)
            if len(self.points.shape) == 1:
                self.points = self.points.reshape(-1, 2)
        elif self.xyxy is not None:
            # Convert xyxy to polygon points for compatibility
            x1, y1, x2, y2 = self.xyxy
            self.points = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
        else:
            raise ValueError("Either points or xyxy must be provided")
    
    @property
    def bbox(self) -> Dict[str, float]:
        """Get axis-aligned bounding box"""
        if self._bbox is None:
            x_coords = self.points[:, 0]
            y_coords = self.points[:, 1]
            self._bbox = {
                'x': float(np.min(x_coords)),
                'y': float(np.min(y_coords)),
                'w': float(np.max(x_coords) - np.min(x_coords)),
                'h': float(np.max(y_coords) - np.min(y_coords))
            }
        return self._bbox
    
    @property
    def xyxy_coords(self) -> List[int]:
        """Get rectangular coordinates [x1, y1, x2, y2]"""
        if self.xyxy is not None:
            return self.xyxy
        bbox = self.bbox
        return [int(bbox['x']), int(bbox['y']), 
                int(bbox['x'] + bbox['w']), int(bbox['y'] + bbox['h'])]
    
    @property
    def center(self) -> np.ndarray:
        """Get center point"""
        if self._center is None:
            self._center = np.mean(self.points, axis=0)
        return self._center
    
    @property
    def area(self) -> float:
        """Get polygon area using shoelace formula"""
        if len(self.points) < 3:
            return 0.0
        x = self.points[:, 0]
        y = self.points[:, 1]
        return 0.5 * abs(sum(x[i] * y[i+1] - x[i+1] * y[i] for i in range(-1, len(x)-1)))
    
    @property
    def aspect_ratio(self) -> float:
        """Get width/height ratio"""
        bbox = self.bbox
        return bbox['w'] / max(bbox['h'], 1)
    
    @property
    def auto_direction(self) -> str:
        """Auto-detect text direction based on aspect ratio"""
        return 'h' if self.aspect_ratio > 1.5 else 'v'
    
    @property
    def ocr_font_size(self) -> float:
        """Dynamic font size calculation for OCR merging - EXACT MATCH to TextBox"""
        # Match TextBox.font_size calculation exactly
        return self.bbox['h'] if self.auto_direction == 'h' else self.bbox['w']
    
    @property
    def angle(self) -> float:
        """Calculate text box angle from first two points - EXACT MATCH to TextBox"""
        if len(self.points) >= 2:
            p1, p2 = self.points[0], self.points[1]
            return np.arctan2(p2[1] - p1[1], p2[0] - p1[0])
        return 0.0
    
    @property
    def is_axis_aligned(self) -> bool:
        """Check if approximately axis-aligned (within 5 degrees) - EXACT MATCH to TextBox"""
        angle_deg = np.abs(np.rad2deg(self.angle))
        return angle_deg < 5 or angle_deg > 175 or (85 < angle_deg < 95)
    
    @property
    def horizontal(self) -> bool:
        """Check if text should be rendered horizontally"""
        if self.direction == 'auto':
            return self.auto_direction == 'h'
        return self.direction in ['h', 'horizontal']
    
    @property
    def vertical(self) -> bool:
        """Check if text should be rendered vertically"""
        return not self.horizontal
    
    # Properties for overlay compatibility
    @property
    def xywh(self) -> np.ndarray:
        """Get [x, y, width, height] format"""
        bbox = self.bbox
        return np.array([bbox['x'], bbox['y'], bbox['w'], bbox['h']])
    
    @property
    def min_rect(self) -> np.ndarray:
        """Get properly shaped min_rect for overlay (fixes the rectangle bug!)"""
        return self.points.reshape(1, -1, 2)
    
    @property
    def unrotated_min_rect(self) -> List[np.ndarray]:
        """Get unrotated rectangle points"""
        return [self.points.copy()]
    
    @property
    def unrotated_size(self) -> Tuple[float, float]:
        """Get unrotated size (width, height)"""
        bbox = self.bbox
        return (bbox['w'], bbox['h'])
    
    @property
    def texts(self) -> List[str]:
        """Compatibility property for overlay"""
        return [self.text]
    
    # OCR-specific methods
    def distance_to(self, other: 'ImageText') -> float:
        """Calculate minimum distance to another text block (for merging) - EXACT MATCH to TextBox"""
        # Use Shapely polygon distance for exact compatibility with ocr_opt.py
        try:
            from shapely.geometry import Polygon
            poly_self = Polygon(self.points)
            poly_other = Polygon(other.points)
            return poly_self.distance(poly_other)
        except ImportError:
            # Fallback to simplified calculation if Shapely not available
            min_dist = float('inf')
            for i in range(len(self.points)):
                for j in range(len(other.points)):
                    p1, p2 = self.points[i], self.points[(i+1) % len(self.points)]
                    p3, p4 = other.points[j], other.points[(j+1) % len(other.points)]
                    
                    # Distance between line segments (simplified)
                    dist = min(
                        np.linalg.norm(p1 - p3), np.linalg.norm(p1 - p4),
                        np.linalg.norm(p2 - p3), np.linalg.norm(p2 - p4)
                    )
                    min_dist = min(min_dist, dist)
            return min_dist
    
    # Overlay-specific methods  
    def get_font_colors(self) -> Tuple[Tuple[int, int, int], Tuple[int, int, int]]:
        """Get foreground and background colors for rendering"""
        return self.color, self.stroke_color
    
    def get_translation_for_rendering(self) -> str:
        """Get text for rendering (translation or original)"""
        return self.translation or self.text