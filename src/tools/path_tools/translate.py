from ...path import pathtool, StructuredData
from langchain_ollama import ChatOllama

@pathtool(input="text_data", output="return")
def translate(text_data: StructuredData, model: ChatOllama, target_language: str = 'english') -> StructuredData:
    """Translate text in list of objects with translation/text/is_cjk_translation fields"""
    import copy
    import re
    
    # Create a deep copy to preserve all original data structure and fields
    # Only translation/text/is_cjk_translation fields will be updated
    translated_data = copy.deepcopy(text_data)
    
    print(f"Translating text data to {target_language}")
    
    # Handle list of objects with translation/text/is_cjk_translation fields
    if isinstance(text_data, list):
        print(f"Processing {len(text_data)} text objects...")
        
        # Step 1: Collect all texts that need translation
        texts_to_translate = []
        text_positions = {}  # Maps text_index -> list_idx
        text_index = 0
        
        for list_idx, item in enumerate(text_data):
            # Check for text field and whether it needs translation
            if (hasattr(item, 'text') or 'text' in item) and (hasattr(item, 'translation') or 'translation' in item):
                text = getattr(item, 'text', None) if hasattr(item, 'text') else item.get('text', '')
                existing_translation = getattr(item, 'translation', None) if hasattr(item, 'translation') else item.get('translation', '')
                
                # Only translate if text exists and no translation exists or translation is empty
                if text and text.strip() and (not existing_translation or existing_translation.strip() == ''):
                    texts_to_translate.append(text)
                    text_positions[text_index] = list_idx
                    text_index += 1
        
        if not texts_to_translate:
            print("No texts found to translate")
            return translated_data
        
        print(f"Found {len(texts_to_translate)} texts to translate")
        
        # Step 2: Create batch prompts (group texts into batches)
        batch_size = 10  # Adjust based on model context limits
        batch_prompts = []
        batch_text_maps = []  # Maps batch results back to original positions
        
        for i in range(0, len(texts_to_translate), batch_size):
            batch_texts = texts_to_translate[i:i + batch_size]
            
            # Create numbered prompt
            numbered_texts = []
            for j, text in enumerate(batch_texts):
                numbered_texts.append(f"{j + 1}. {text}")
            
            prompt = f"Translate the following texts to {target_language}. Return only the translations in the same numbered format:\n\n" + "\n".join(numbered_texts)
            batch_prompts.append(prompt)
            
            # Map batch positions to global positions
            batch_map = {}
            for j in range(len(batch_texts)):
                global_text_idx = i + j
                batch_map[j + 1] = global_text_idx  # j+1 because prompts are 1-indexed
            batch_text_maps.append(batch_map)
        
        print(f"Created {len(batch_prompts)} batch prompts")
        
        # Step 3: Use LangChain's batch method
        try:
            print("Sending batch translation requests...")
            responses = model.batch(batch_prompts)
            print(f"Received {len(responses)} batch responses")
        except Exception as e:
            print(f"Batch translation failed: {e}")
            print("Falling back to original data")
            return translated_data
        
        # Step 4: Parse numbered responses
        all_translations = {}  # Maps global_text_idx -> translated_text
        
        for batch_idx, response in enumerate(responses):
            try:
                content = response.content.strip()
                batch_map = batch_text_maps[batch_idx]
                
                # Parse numbered format: "1. translation"
                lines = content.split('\n')
                for line in lines:
                    line = line.strip()
                    if not line:
                        continue
                    
                    # Match numbered format
                    match = re.match(r'^(\d+)\.\s*(.*)', line)
                    if match:
                        line_num = int(match.group(1))
                        translation = match.group(2).strip()
                        
                        if line_num in batch_map and translation:
                            global_text_idx = batch_map[line_num]
                            all_translations[global_text_idx] = translation
                            
            except Exception as e:
                print(f"Error parsing batch {batch_idx}: {e}")
        
        print(f"Successfully parsed {len(all_translations)} translations")
        
        # Step 5: Apply translations back to objects (preserving all other fields)
        applied_count = 0
        for global_text_idx, translation in all_translations.items():
            if global_text_idx in text_positions:
                list_idx = text_positions[global_text_idx]
                item = translated_data[list_idx]
                
                # Get original text for logging
                original = getattr(item, 'text', None) if hasattr(item, 'text') else item.get('text', '')
                
                # Update only the translation field (all other fields preserved)
                if hasattr(item, 'translation'):
                    item.translation = translation
                else:
                    item['translation'] = translation
                
                # Update only the is_cjk_translation field if it exists (all other fields preserved)
                if hasattr(item, 'is_cjk_translation'):
                    item.is_cjk_translation = _is_cjk_text(translation)
                elif 'is_cjk_translation' in item:
                    item['is_cjk_translation'] = _is_cjk_text(translation)
                
                print(f"  Item {list_idx+1}: '{original[:30]}...' -> '{translation[:30]}...'")
                applied_count += 1
        
        print(f"Applied {applied_count} translations to list items")
    
    else:
        print("Warning: Expected list input with translation/text/is_cjk_translation fields")
        return text_data
    
    print(f"Translation to {target_language} completed!")
    return translated_data

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