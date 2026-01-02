# application/services/subtitle_service.py
import re
import concurrent.futures
from typing import Optional, Callable, List
from .translation_service import TranslationService


class SubtitleService:
    """
    Service for processing subtitle files, including cleaning, translating,
    and optimizing subtitle blocks.
    """

    def __init__(self, batch_size: int = 50, max_workers: int = 10):
        """
        Initializes the SubtitleService.

        Args:
            batch_size (int): The number of subtitle blocks to process in a batch
                              for operations like translation.
            max_workers (int): Maximum number of parallel translation workers.
        """
        self.translation_service = TranslationService()
        self.spam_patterns = [
            r"Subtitled by",
            r'-♪.*?♪-',
            r"We compress knowledge for you!",
            r"https://t.me/.*?",
            r"Subtitled\s*by",
            r"https?://[^\s]+",
            r"♪",
            r"We\s*compress\s*knowledge\s*for\s*you!",
            r"online|courses|club",
            r"<font.*?>.*?</font>",
            r"\bjoinchat\b",
            r".*?/[a-zA-Z0-9]{12}.*",  # Matches any line containing a Telegram ID
        ]
        self.batch_size = batch_size
        self.max_workers = max_workers

    def process_subtitles(self, file_path: str, translate: bool, target_language: Optional[str],
                          progress_callback: Callable) -> str:
        """
        Main method to process a subtitle file. It reads, cleans, translates (optional),
        optimizes, and formats the subtitles.

        Args:
            file_path (str): The path to the subtitle file.
            translate (bool): Whether to translate the subtitles.
            target_language (Optional[str]): The target language for translation.
            progress_callback (Callable): A function to call for progress updates.

        Returns:
            str: The processed subtitle content as a single string.
        """
        content = self._read_file(file_path)
        
        progress_callback('info', "Reading and parsing file...")

        processed_content = self._clean_content(content)
        subtitle_blocks = self._extract_blocks(processed_content, progress_callback)
        
        if not subtitle_blocks:
             progress_callback('error', "Could not find any valid subtitle blocks in the file.")
             return ""
        
        progress_callback('info', f"Total subtitles found: {len(subtitle_blocks)}")

        if translate:
            subtitle_blocks = self._translate_blocks(subtitle_blocks, target_language, progress_callback)

        subtitle_blocks = self._optimize_blocks(subtitle_blocks, progress_callback)
        return self._format_output(subtitle_blocks, progress_callback)

    def _read_file(self, file_path: str) -> str:
        """
        Reads the content of a file.

        Args:
            file_path (str): The path to the file.

        Returns:
            str: The content of the file.
        """
        with open(file_path, "r", encoding='UTF-8') as file:
            return file.read()

    def _clean_content(self, content: str) -> str:
        """
        Removes spam and unwanted patterns from the subtitle content.

        Args:
            content (str): The original subtitle content.

        Returns:
            str: The cleaned content.
        """
        cleaned = content
        for pattern in self.spam_patterns:
            cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
        return cleaned

    def _extract_blocks(self, content: str, progress_callback: Callable) -> List[List[str]]:
        """
        Extracts subtitle blocks from the content.
        支持标准SRT (00:00:20,000), VTT (00:00:20.000) 以及简易格式 (00:00:20).
        """
        parsed_blocks = []
        # Robust regex for various timestamp formats
        timestamp_pattern = re.compile(r'\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?')
        
        if content.strip().startswith('WEBVTT'):
            content = re.sub(r'WEBVTT.*?\n\s*\n', '', content, 1, flags=re.DOTALL | re.IGNORECASE)

        raw_blocks = re.split(r'\n\s*\n', content.strip())
        
        for raw_block in raw_blocks:
            lines = [line.strip() for line in raw_block.split('\n') if line.strip()]
            if not lines:
                continue

            # A valid block needs at least a timeline and a text line.
            if len(lines) >= 2:
                # Case 1: Standard SRT with index
                if lines[0].isdigit() and timestamp_pattern.search(lines[1]):
                    parsed_blocks.append(lines)
                # Case 2: Timeline on first line (with or without index)
                elif timestamp_pattern.search(lines[0]):
                    if '-->' in lines[0] or ' - ' in lines[0] or ':' in lines[0]:
                        # If it's a timestamp but doesn't have an index, add one.
                        new_block = [str(len(parsed_blocks) + 1)] + lines
                        parsed_blocks.append(new_block)
            
        return parsed_blocks

    def _translate_blocks(self, blocks: List[List[str]], target_language: str,
                          progress_callback: Callable) -> List[List[str]]:
        """
        Translates the text in each subtitle block using multi-threading.
        """
        total_blocks = len(blocks)
        progress_callback('status', f'Translating {total_blocks} subtitles (parallel)...')

        results = [None] * total_blocks
        
        def translate_single_block(index, block):
            if len(block) < 3:
                return index, block

            original_text = "\n".join(block[2:])
            if not original_text.strip():
                return index, block

            try:
                translated_text = self.translation_service.translate_text(original_text, target_language)
                translated_lines = translated_text.split("\n")
                new_block = [block[0], block[1]] + translated_lines
                return index, new_block
            except Exception as e:
                raise RuntimeError(f"Block #{block[0]} translation failed: {e}")

        completed_count = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_index = {executor.submit(translate_single_block, i, b): i for i, b in enumerate(blocks)}
            
            for future in concurrent.futures.as_completed(future_to_index):
                try:
                    index, translated_block = future.result()
                    results[index] = translated_block
                    completed_count += 1
                    
                    progress = (completed_count / total_blocks) * 0.8
                    progress_callback('progress', progress)
                except Exception as e:
                    progress_callback('error', str(e))
                    executor.shutdown(wait=False, cancel_futures=True)
                    raise

        return results


    def _optimize_blocks(self, blocks: List[List[str]], progress_callback: Callable) -> List[List[str]]:
        """
        Optimizes subtitle blocks by fixing timestamps and re-indexing.
        """
        optimized = []
        current_index = 1
        timestamp_pattern = re.compile(r'\d{1,2}:\d{2}(?::\d{2})?(?:[.,]\d{1,3})?')

        for i, block in enumerate(blocks):
            if len(block) < 2:
                continue
            
            timestamp_line = block[1]
            
            # Extract timestamps from the line
            actual_matches = [m.group(0) for m in timestamp_pattern.finditer(timestamp_line)]
            
            if not actual_matches:
                continue
            
            start_time = actual_matches[0]
            end_time = actual_matches[1] if len(actual_matches) > 1 else None

            # If no end time, try to get it from next block's start time
            if not end_time:
                if i + 1 < len(blocks):
                    next_timestamp_line = blocks[i+1][1]
                    next_matches = [m.group(0) for m in timestamp_pattern.finditer(next_timestamp_line)]
                    if next_matches:
                        end_time = next_matches[0]
                
                # If still no end time (last block), add a default duration (e.g., 3 seconds)
                if not end_time:
                    # Very simple logic: just add ":03" or something, but HH:MM:SS is tricky.
                    # For now, let's just repeat the start time or add a placeholder.
                    # A better way would be parsing time, but let's keep it simple.
                    end_time = start_time 

            # Standardize timestamp format
            block[1] = f"{start_time} --> {end_time}"
            block[0] = str(current_index)
            
            # Make sure it has text
            if len(block) < 3:
                continue

            # Ensure comma instead of dot for SRT if needed (optional, keeping as is for now)
            # block[1] = block[1].replace('.', ',')

            # Ensure continuity logic (optional)
            if optimized:
                prev_block = optimized[-1]
                prev_timeline = prev_block[1].split(' --> ')
                if len(prev_timeline) == 2:
                    prev_end = prev_timeline[1]
                    curr_timeline = block[1].split(' --> ')
                    curr_start = curr_timeline[0]
                    # If there's a gap or overlap, we can normalize it if we want, 
                    # but usually we want to respect the extracted timestamps if they are valid.
            
            optimized.append(block)
            current_index += 1

        return optimized

    def _format_output(self, blocks: List[List[str]], progress_callback: Callable) -> str:
        """
        Formats the final list of subtitle blocks into a single string.

        Args:
            blocks (List[List[str]]): The list of subtitle blocks.
            progress_callback (Callable): A function to call for progress updates.

        Returns:
            str: The formatted subtitle content.
        """
        formatted_content = []
        total_blocks = len(blocks)
        if total_blocks == 0:
            return ""
            
        for i, block in enumerate(blocks):
            formatted_content.extend(block)
            formatted_content.append('')
            progress = 0.8 + (i + 1) / total_blocks * 0.2
            progress_callback('progress', progress)
        return '\n'.join(formatted_content)
