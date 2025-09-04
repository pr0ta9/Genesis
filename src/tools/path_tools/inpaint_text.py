from PIL import Image, ImageDraw, ImageFont
import textwrap
import math
import re
import os
import urllib.request
from ...path import ImageFile, StructuredData, pathtool

# Resolve local font directories (project-level)
_THIS_DIR = os.path.dirname(__file__)
# Go up three levels: path_tools -> tools -> src -> project root
_PROJECT_ROOT = os.path.abspath(os.path.join(_THIS_DIR, "../../../"))
_LOCAL_FONT_DIR_CANDIDATES = [
    os.path.abspath(os.path.join(_PROJECT_ROOT, "data", "font")),
    os.path.abspath(os.path.join(_PROJECT_ROOT, "font")),
    os.path.abspath(os.path.join(os.getcwd(), "data", "font")),
    os.path.abspath(os.path.join(os.getcwd(), "font")),
]

def _existing_local_font_dirs():
    return [d for d in _LOCAL_FONT_DIR_CANDIDATES if os.path.isdir(d)]

def _get_font_storage_dir():
    """Pick a directory to read/write fonts. Prefer existing local font dirs; otherwise create data/font under project root."""
    existing = _existing_local_font_dirs()
    if existing:
        return existing[0]
    default_dir = os.path.abspath(os.path.join(_PROJECT_ROOT, "data", "font"))
    os.makedirs(default_dir, exist_ok=True)
    return default_dir

@pathtool(input="bbox_data", output="return", requires={"image_input": ImageFile})
def inpaint_text(image_input: ImageFile, bbox_data: StructuredData, output_path: ImageFile, font_paths=None, min_font_size=20, max_font_size=100) -> ImageFile:
    """
    Fits and draws horizontal text strings into their specified bounding boxes using binary search.
    
    Args:
        image_input (ImageFile): Path to the input image file.
        bbox_data (StructuredData): List of dictionaries containing translation and box data.
        output_path (ImageFile): Path to the output image file.
        font_paths (list): List of font paths to try (will use Unicode-supporting defaults if None).
        min_font_size (int): Minimum readable font size.
        max_font_size (int): Maximum font size to start with.
    """
    try:
        img = Image.open(image_input)
    except FileNotFoundError:
        print(f"Error: Image file '{image_input}' not found.")
        return

    draw = ImageDraw.Draw(img)
    
    # Setup Unicode-supporting font system
    def get_unicode_font(size, font_paths=None, prefer_cjk=False):
        """Get a font that supports Unicode characters, preferring project fonts in data/font or font."""
        # Build local font candidates first
        local_dirs = _existing_local_font_dirs()
        local_candidates = []
        if prefer_cjk:
            for d in local_dirs:
                local_candidates.extend([
                    os.path.join(d, "SourceHanSerifK-Regular.otf"),
                    os.path.join(d, "NotoSerifCJK-Regular.ttc"),
                    os.path.join(d, "NotoSans-Regular.ttf"),
                ])
        else:
            for d in local_dirs:
                local_candidates.extend([
                    os.path.join(d, "NotoSans-Regular.ttf"),
                    os.path.join(d, "NotoSans-Bold.ttf"),
                ])

        if font_paths is None:
            if prefer_cjk:
                # Source Han Serif for CJK translations
                font_paths = local_candidates + [
                    # Source Han Serif Korean (best for CJK)
                    "SourceHanSerifK-Regular.otf",                    # Relative (legacy fallback)
                    "C:/Windows/Fonts/SourceHanSerifK-Regular.otf",  # Windows install
                    "C:/Windows/Fonts/NotoSerifCJK-Regular.ttc",     # Noto Serif CJK
                    "/usr/share/fonts/opentype/source-han-serif/SourceHanSerifK-Regular.otf", # Linux
                    "/System/Library/Fonts/SourceHanSerifK.otc",     # macOS
                    
                    # Fallback CJK fonts
                    "C:/Windows/Fonts/YuGothM.ttc",                  # Yu Gothic Medium
                    "C:/Windows/Fonts/msyh.ttc",                     # Microsoft YaHei
                    "C:/Windows/Fonts/simsun.ttc",                   # SimSun
                    
                    # General Unicode fonts as last resort
                    "NotoSans-Regular.ttf",
                    "C:/Windows/Fonts/seguibl.ttf",
                ]
            else:
                # Prioritize Google Noto fonts for best Unicode support
                font_paths = local_candidates + [
                    # Google Noto fonts (best Unicode coverage)
                    "NotoSans-Regular.ttf",                      # Relative (legacy fallback)
                    "C:/Windows/Fonts/NotoSans-Regular.ttf",     # Windows Noto Sans
                    "C:/Windows/Fonts/NotoSans-Bold.ttf",        # Windows Noto Sans Bold
                    "C:/Users/Public/Downloads/NotoSans-Regular.ttf",  # Common download location
                    "/usr/share/fonts/noto/NotoSans-Regular.ttf", # Linux Noto
                    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf", # Ubuntu Noto
                    "/System/Library/Fonts/Noto Sans.ttc",       # macOS Noto
                    
                    # Windows system fonts (good Unicode support)
                    "C:/Windows/Fonts/seguibl.ttf",              # Segoe UI Bold
                    "C:/Windows/Fonts/segoeui.ttf",              # Segoe UI Regular
                    "C:/Windows/Fonts/calibri.ttf",              # Calibri
                    "C:/Windows/Fonts/YuGothM.ttc",              # Yu Gothic Medium - good for CJK
                    "C:/Windows/Fonts/msyh.ttc",                 # Microsoft YaHei - good for CJK
                    
                    # Cross-platform fallbacks
                    "/usr/share/fonts/dejavu/DejaVuSans.ttf",    # Linux DejaVu
                    "/System/Library/Fonts/Arial.ttf",          # macOS Arial
                    "C:/Windows/Fonts/arial.ttf",               # Windows Arial (last resort)
                ]
        
        for font_path in font_paths:
            try:
                font = ImageFont.truetype(font_path, size)
                # Print which font was successfully loaded (only once per font type)
                font_type = "CJK" if prefer_cjk else "Regular"
                if not hasattr(get_unicode_font, f'_font_announced_{font_type}'):
                    print(f"Using {font_type} font: {os.path.basename(font_path)}")
                    setattr(get_unicode_font, f'_font_announced_{font_type}', True)
                return font
            except (IOError, OSError):
                continue
        
        # Try to download appropriate font if no good fonts found
        if prefer_cjk:
            # Download Source Han Serif Korean for CJK
            storage_dir = _get_font_storage_dir()
            han_download_path = os.path.join(storage_dir, "SourceHanSerifK-Regular.otf")
            if not os.path.exists(han_download_path):
                print("No CJK fonts found. Attempting to download Source Han Serif Korean...")
                try:
                    urllib.request.urlretrieve(
                        "https://github.com/adobe-fonts/source-han-serif/raw/release/OTF/Korean/SourceHanSerifK-Regular.otf",
                        han_download_path
                    )
                    print(f"Downloaded Source Han Serif Korean to {han_download_path}")
                    return ImageFont.truetype(han_download_path, size)
                except Exception as e:
                    print(f"Failed to download Source Han Serif: {e}")
            else:
                try:
                    print(f"Using downloaded CJK font: {han_download_path}")
                    return ImageFont.truetype(han_download_path, size)
                except:
                    pass
        else:
            # Download Noto Sans for regular text
            storage_dir = _get_font_storage_dir()
            noto_download_path = os.path.join(storage_dir, "NotoSans-Regular.ttf")
            if not os.path.exists(noto_download_path):
                print("No Unicode fonts found. Attempting to download Noto Sans...")
                try:
                    urllib.request.urlretrieve(
                        "https://github.com/googlefonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf",
                        noto_download_path
                    )
                    print(f"Downloaded Noto Sans to {noto_download_path}")
                    return ImageFont.truetype(noto_download_path, size)
                except Exception as e:
                    print(f"Failed to download Noto font: {e}")
            else:
                try:
                    print(f"Using downloaded font: {noto_download_path}")
                    return ImageFont.truetype(noto_download_path, size)
                except:
                    pass
        
        # Fallback to default font
        print("Warning: No Unicode fonts found, using default font")
        return ImageFont.load_default()
    
    def polygon_to_bbox(polygon_points):
        """Convert 4-point polygon to bounding box (x1, y1, x2, y2)"""
        x_coords = [point[0] for point in polygon_points]
        y_coords = [point[1] for point in polygon_points]
        return (min(x_coords), min(y_coords), max(x_coords), max(y_coords))
    
    def draw_vertical_text(draw, position, text, font, fill=(0, 0, 0)):
        """Draw text vertically (top to bottom) for CJK text"""
        x, y = position
        current_y = y
        
        # Remove line breaks and spaces for vertical text
        clean_text = text.replace('\n', '').replace(' ', '')
        
        for char in clean_text:
            # Get character dimensions
            bbox = draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            char_height = bbox[3] - bbox[1]
            
            # Center character horizontally within the column
            char_x = x + (font.size - char_width) // 2
            
            # Draw the character
            draw.text((char_x, current_y), char, font=font, fill=fill)
            
            # Move to next character position (down)
            current_y += font.size * 1.2  # Add spacing between characters
    
    def get_text_dimensions(text, font, draw, is_vertical=False):
        """Get text dimensions including line spacing"""
        if not text.strip():
            return 0, 0
        
        if is_vertical:
            # For vertical text, each character is essentially a "line"
            chars = text.replace('\n', '').replace(' ', '')  # Remove line breaks and spaces for vertical
            char_width = font.size  # Approximate character width
            char_height = font.size * 1.2  # Character height with spacing
            
            total_width = char_width
            total_height = len(chars) * char_height
            return total_width, total_height
        else:
            # Horizontal text (original logic)
            lines = text.split('\n')
            line_height = font.size * 1.2  # 1.2x font size for line height
            
            max_width = 0
            for line in lines:
                bbox = draw.textbbox((0, 0), line, font=font)
                line_width = bbox[2] - bbox[0]
                max_width = max(max_width, line_width)
            
            total_height = len(lines) * line_height
            return max_width, total_height
    
    def split_text_into_lines(text, target_lines):
        """Split text into approximately equal lines, handling hyphens as break points"""
        # First, identify all potential break points (spaces and hyphens)
        
        # Split on spaces but keep hyphenated words as potential break points
        words = text.split()
        
        # Create a list of breakable units (words that might contain hyphens)
        breakable_units = []
        for word in words:
            # Check if word contains hyphens/dashes that we can break on
            if re.search(r'[-‑–—]', word):  # hyphen, non-breaking hyphen, en-dash, em-dash
                # Split on hyphens but keep the hyphen with the first part
                parts = re.split(r'([-‑–—])', word)
                current_part = ""
                for i, part in enumerate(parts):
                    if re.match(r'[-‑–—]', part):
                        current_part += part
                        if current_part.strip():
                            breakable_units.append(current_part)
                        current_part = ""
                    else:
                        current_part += part
                if current_part.strip():
                    breakable_units.append(current_part)
            else:
                breakable_units.append(word)
        
        if len(breakable_units) <= target_lines:
            return breakable_units
        
        # Now distribute units across target lines for optimal balance
        return distribute_units_optimally(breakable_units, target_lines)
    
    def distribute_units_optimally(units, target_lines):
        """Distribute text units across lines for optimal character balance"""
        if len(units) <= target_lines:
            return units
        
        # Calculate total character count
        total_chars = sum(len(unit) for unit in units) + len(units) - 1  # +spaces
        target_chars_per_line = total_chars / target_lines
        
        lines = []
        current_line = []
        current_chars = 0
        
        for i, unit in enumerate(units):
            unit_chars = len(unit)
            
            # If adding this unit would exceed target significantly, start new line
            # (unless it's the first unit in the line or we'd exceed target_lines)
            if (current_line and 
                current_chars + unit_chars + 1 > target_chars_per_line * 1.3 and 
                len(lines) < target_lines - 1):
                
                lines.append(' '.join(current_line))
                current_line = [unit]
                current_chars = unit_chars
            else:
                if current_line:
                    current_chars += 1  # space
                current_line.append(unit)
                current_chars += unit_chars
        
        # Add remaining units to last line
        if current_line:
            lines.append(' '.join(current_line))
        
        return lines
    
    def balance_line_lengths(lines, tolerance=0.1):
        """Balance line lengths within tolerance, redistributing words and breaking long words if needed"""
        if len(lines) <= 1:
            return lines
        
        # Calculate line lengths
        line_lengths = [len(line) for line in lines]
        avg_length = sum(line_lengths) / len(line_lengths)
        max_length = max(line_lengths)
        min_length = min(line_lengths)
        
        # Check if within tolerance (avoid division by zero)
        if avg_length == 0 or (max_length - min_length) / avg_length <= tolerance:
            return lines
        
        # If unbalanced, redistribute all words optimally
        all_words = []
        for line in lines:
            all_words.extend(line.split())
        
        # Use optimal distribution
        redistributed_lines = distribute_units_optimally(all_words, len(lines))
        
        # Check if redistribution improved balance
        new_line_lengths = [len(line) for line in redistributed_lines]
        new_avg = sum(new_line_lengths) / len(new_line_lengths)
        new_max = max(new_line_lengths)
        new_min = min(new_line_lengths)
        
        # If still unbalanced, check for long words that need breaking
        if new_avg > 0 and (new_max - new_min) / new_avg > tolerance:
            final_lines = []
            for line in redistributed_lines:
                words = line.split()
                line_needs_breaking = False
                
                # Check if any single word is too long compared to average
                for word in words:
                    if len(word) > new_avg * 1.5:  # Word is significantly longer than average
                        line_needs_breaking = True
                        break
                
                if line_needs_breaking and len(words) == 1:
                    # Break the long word
                    max_word_length = max(8, int(new_avg * 0.8))  # Reasonable word length
                    wrapped = textwrap.fill(line, width=max_word_length, break_long_words=True)
                    final_lines.extend(wrapped.split('\n'))
                else:
                    final_lines.append(line)
            
            return final_lines
        
        return redistributed_lines
    
    def check_single_word_dominance(lines):
        """Check if most lines contain only single words"""
        if not lines:
            return False
        
        single_word_lines = sum(1 for line in lines if len(line.split()) == 1)
        return single_word_lines / len(lines) > 0.6  # More than 60% are single words
    
    def find_optimal_font_and_layout(text, box_width, box_height, font_paths, min_font_size, max_font_size, prefer_cjk=False, is_vertical=False):
        """Use binary search to find optimal font size and layout"""
        
        def test_layout(font_size, max_lines):
            """Test if text fits with given font size and max lines"""
            font = get_unicode_font(font_size, font_paths, prefer_cjk)
            
            # Try different line counts
            for num_lines in range(1, max_lines + 1):
                lines = split_text_into_lines(text, num_lines)
                lines = balance_line_lengths(lines)
                
                text_block = '\n'.join(lines) if not is_vertical else ''.join(lines)
                width, height = get_text_dimensions(text_block, font, draw, is_vertical)
                
                if width <= box_width and height <= box_height:
                    return True, lines, font, width, height
            
            return False, [], None, 0, 0
        
        # Calculate maximum possible lines based on minimum font size
        max_possible_lines = int(box_height / (min_font_size * 1.2))
        max_possible_lines = max(1, min(max_possible_lines, 10))  # Reasonable upper limit
        
        # Binary search for optimal font size
        low = min_font_size
        high = max_font_size
        best_result = None
        
        while low <= high:
            mid_font = (low + high) // 2
            fits, lines, font, width, height = test_layout(mid_font, max_possible_lines)
            
            if fits:
                best_result = (mid_font, lines, font, width, height)
                low = mid_font + 1  # Try larger font
            else:
                high = mid_font - 1  # Try smaller font
        
        if best_result is None:
            # Fallback to minimum font size
            fits, lines, font, width, height = test_layout(min_font_size, max_possible_lines)
            if fits:
                best_result = (min_font_size, lines, font, width, height)
        
        # Post-process: Check for single-word dominance and adjust if possible
        if best_result:
            font_size, lines, font, width, height = best_result
            
            if check_single_word_dominance(lines) and font_size > min_font_size:
                # Try to reduce font size to get more words per line
                for reduced_font in range(font_size - 1, min_font_size - 1, -1):
                    fits, new_lines, new_font, new_width, new_height = test_layout(reduced_font, max_possible_lines)
                    if fits and not check_single_word_dominance(new_lines):
                        return reduced_font, new_lines, new_font, new_width, new_height
            
            return best_result
        
        return None
    
    def force_fit_with_hyphen_breaking(text, bbox, font_paths, min_font_size, draw, prefer_cjk=False, is_vertical=False):
        """Force fit text by aggressively breaking words with hyphens"""
        box_width = bbox[2] - bbox[0]
        box_height = bbox[3] - bbox[1]
        
        # Use smaller margins for fallback
        margin_factor = 0.95
        available_width = box_width * margin_factor
        available_height = box_height * margin_factor
        
        # Use minimum font size
        font = get_unicode_font(min_font_size, font_paths, prefer_cjk)
        
        line_height = min_font_size * 1.2
        max_lines = int(available_height / line_height)
        max_lines = max(1, max_lines)
        
        # Start with increasingly aggressive word breaking
        for word_break_length in [15, 12, 10, 8, 6, 4]:  # Progressively shorter word chunks
            # Break all words longer than word_break_length
            broken_text = break_long_words_with_hyphens(text, word_break_length)
            
            # Try to fit with this level of breaking
            for num_lines in range(1, max_lines + 1):
                lines = distribute_units_optimally(broken_text.split(), num_lines)
                text_block = '\n'.join(lines) if not is_vertical else ''.join(lines)
                
                width, height = get_text_dimensions(text_block, font, draw, is_vertical)
                
                if width <= available_width and height <= available_height:
                    return font, text_block, width, height, min_font_size
        
        # Last resort: break into single characters with hyphens
        words = text.split()
        char_lines = []
        current_line = ""
        
        for word in words:
            for char in word:
                if current_line and len(current_line + "-" + char) * min_font_size * 0.6 > available_width:
                    char_lines.append(current_line + "-")
                    current_line = char
                else:
                    if current_line:
                        current_line += "-"
                    current_line += char
            
            # Add space after word if not last
            if word != words[-1]:
                current_line += " "
        
        if current_line:
            char_lines.append(current_line)
        
        # Limit to max_lines
        if len(char_lines) > max_lines:
            char_lines = char_lines[:max_lines]
            char_lines[-1] += "..."
        
        final_text = '\n'.join(char_lines) if not is_vertical else ''.join(char_lines)
        width, height = get_text_dimensions(final_text, font, draw, is_vertical)
        
        return font, final_text, width, height, min_font_size
    
    def break_long_words_with_hyphens(text, max_word_length):
        """Break words longer than max_word_length by inserting hyphens"""
        words = text.split()
        broken_words = []
        
        for word in words:
            if len(word) <= max_word_length:
                broken_words.append(word)
            else:
                # Break long word into chunks with hyphens
                chunks = []
                remaining = word
                
                while len(remaining) > max_word_length:
                    chunk = remaining[:max_word_length-1] + "-"
                    chunks.append(chunk)
                    remaining = remaining[max_word_length-1:]
                
                if remaining:
                    chunks.append(remaining)
                
                broken_words.extend(chunks)
        
        return ' '.join(broken_words)

    def fit_text_in_box(text, bbox, font_paths, min_font_size, max_font_size, prefer_cjk=False, is_vertical=False):
        """Main text fitting function"""
        box_width = bbox[2] - bbox[0]
        box_height = bbox[3] - bbox[1]
        
        # Add some margin (10% on each side)
        margin_factor = 0.9
        available_width = box_width * margin_factor
        available_height = box_height * margin_factor
        
        result = find_optimal_font_and_layout(text, available_width, available_height, 
                                            font_paths, min_font_size, max_font_size, prefer_cjk, is_vertical)
        
        if result is None:
            return None, "", 0, 0, 0
        
        font_size, lines, font, text_width, text_height = result
        wrapped_text = '\n'.join(lines)
        
        return font, wrapped_text, text_width, text_height, font_size

    # Ensure text_data_list is actually a list
    if not isinstance(bbox_data, list):
        print(f"Error: bbox_data should be a list, got {type(bbox_data)}")
        return

    # Process each text data item
    for text_data in bbox_data:
        # Check if text_data is a dictionary with required keys
        if not isinstance(text_data, dict):
            print(f"Warning: Skipping invalid text data item (not a dict): {text_data}")
            continue
            
        if 'translation' not in text_data or 'boxes' not in text_data:
            print(f"Warning: Skipping text data item missing required keys: {text_data.keys()}")
            continue
            
        translation = text_data['translation']
        boxes = text_data['boxes']
        is_cjk_translation = text_data.get('is_cjk_translation', False)
        direction = text_data.get('direction', 'h')  # horizontal by default
        
        # Determine if we need vertical CJK rendering
        # ONLY render vertically if BOTH conditions are true:
        # 1. direction == 'v' (original text was vertical)
        # 2. is_cjk_translation == True (user wants CJK-style rendering)
        # If is_cjk_translation=False, ALWAYS use horizontal regardless of content or direction
        is_vertical_cjk = (direction == 'v' and is_cjk_translation == True)
        
        # Convert all polygon boxes to bounding boxes and merge them into one large box
        all_bboxes = [polygon_to_bbox(box_polygon) for box_polygon in boxes]
        
        # Merge all bounding boxes into one large bounding box
        min_x = min(bbox[0] for bbox in all_bboxes)
        min_y = min(bbox[1] for bbox in all_bboxes)
        max_x = max(bbox[2] for bbox in all_bboxes)
        max_y = max(bbox[3] for bbox in all_bboxes)
        
        # Add some padding for better space utilization
        padding_x = (max_x - min_x) * 0.05  # 5% padding horizontally
        padding_y = (max_y - min_y) * 0.05  # 5% padding vertically
        
        merged_bbox = (
            max(0, min_x - padding_x), 
            max(0, min_y - padding_y), 
            max_x + padding_x, 
            max_y + padding_y
        )
        
        # Fit text in the merged bounding box
        result = fit_text_in_box(translation, merged_bbox, font_paths, min_font_size, max_font_size, is_cjk_translation, is_vertical_cjk)
        
        if len(result) == 5:
            font, wrapped_text, text_width, text_height, font_size = result
        else:
            font, wrapped_text, text_width, text_height = result
            font_size = min_font_size  # fallback font size
        
        if font is None:
            # Fallback: Force fit by aggressively breaking words with hyphens
            print(f"Using fallback hyphen-breaking for text '{translation[:30]}...'")
            result = force_fit_with_hyphen_breaking(translation, merged_bbox, font_paths, min_font_size, draw, is_cjk_translation, is_vertical_cjk)
            
            if len(result) == 5:
                font, wrapped_text, text_width, text_height, font_size = result
            else:
                font, wrapped_text, text_width, text_height = result
                font_size = min_font_size
            
            if font is None:
                print(f"Warning: Even fallback failed for text '{translation[:30]}...' in merged box {merged_bbox}")
                continue

        # Calculate text position - center in the merged box
        box_width = merged_bbox[2] - merged_bbox[0]
        box_height = merged_bbox[3] - merged_bbox[1]
        
        x_pos = merged_bbox[0] + (box_width - text_width) / 2
        y_pos = merged_bbox[1] + (box_height - text_height) / 2
        
        # Ensure text stays within bounds
        x_pos = max(merged_bbox[0], min(x_pos, merged_bbox[2] - text_width))
        y_pos = max(merged_bbox[1], min(y_pos, merged_bbox[3] - text_height))

        # Draw the translation text
        if is_vertical_cjk:
            # Draw vertical CJK text
            draw_vertical_text(draw, (x_pos, y_pos), wrapped_text, font, fill=(0, 0, 0))
        else:
            # Draw horizontal text (original method)
            line_spacing = int(font_size * 0.2)  # 20% of font size for spacing between lines
            draw.multiline_text((x_pos, y_pos), wrapped_text, font=font, 
                               spacing=line_spacing, fill=(0, 0, 0))  # Black text
        
        print(f"Text '{translation[:30]}...' fitted with font size {font_size} ({'vertical' if is_vertical_cjk else 'horizontal'})")

    img.save(output_path)
    print(f"Image saved as '{output_path}'")
    return output_path