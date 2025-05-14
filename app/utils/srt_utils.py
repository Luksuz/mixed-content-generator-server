import os
import asyncio

MAX_WORDS_PER_LINE = 4 # As per user request for 5 words max

def parse_timestamp_to_ms(ts_str: str) -> int:
    """Converts an SRT timestamp string (HH:MM:SS,mmm) to milliseconds."""
    try:
        time_part, ms_part = ts_str.split(',')
        h, m, s = map(int, time_part.split(':'))
        return (h * 3600 * 1000) + (m * 60 * 1000) + (s * 1000) + int(ms_part)
    except ValueError:
        # logger.warning(f"Malformed timestamp encountered: {ts_str}")
        print(f"Warning: Malformed timestamp encountered: {ts_str}") # Placeholder for logger
        return 0 # Or raise an error

def format_ms_to_timestamp(total_ms: int) -> str:
    """Converts milliseconds to an SRT timestamp string (HH:MM:SS,mmm)."""
    if total_ms < 0:
        # logger.warning(f"Received negative milliseconds {total_ms}, clamping to 0.")
        print(f"Warning: Received negative milliseconds {total_ms}, clamping to 0.")
        total_ms = 0
    ms = total_ms % 1000
    total_seconds = total_ms // 1000
    s = total_seconds % 60
    total_minutes = total_seconds // 60
    m = total_minutes % 60
    h = total_minutes // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

def _split_text_into_segments(original_text_lines: list[str], max_words: int) -> list[str]:
    """
    Reformats a list of text lines to adhere to a maximum number of words per line.
    Each string in the returned list is a new text segment.
    """
    if not original_text_lines:
        return []
    full_text = " ".join(line.strip() for line in original_text_lines if line.strip())
    words = full_text.split()
    if not words:
        return [""] # Represents an originally empty text block
    
    new_text_segments = []
    current_line_words = []
    for word in words:
        current_line_words.append(word)
        if len(current_line_words) == max_words:
            new_text_segments.append(" ".join(current_line_words))
            current_line_words = []
    if current_line_words:
        new_text_segments.append(" ".join(current_line_words))
    
    return new_text_segments if new_text_segments else [""] # Should always have at least one segment if words existed

def _blocking_reformat_srt_file_timed(input_srt_path: str, output_srt_path: str, max_words: int) -> bool:
    """
    Reads an SRT file, reformats its subtitle text blocks into new cues
    with adjusted timestamps, and writes to a new SRT file. Blocking version.
    """
    try:
        with open(input_srt_path, 'r', encoding='utf-8') as infile:
            content = infile.read()
    except FileNotFoundError:
        # logger.error(f"Input SRT file not found at {input_srt_path}")
        print(f"Error: Input SRT file not found at {input_srt_path}")
        return False
    except Exception as e:
        # logger.error(f"Error reading input SRT file {input_srt_path}: {e}", exc_info=True)
        print(f"Error reading input SRT file {input_srt_path}: {e}")
        return False

    blocks = content.strip().split('\n\n')
    output_srt_blocks = []
    new_subtitle_index = 1
    min_segment_duration_ms = 200 # Minimum duration for a newly created segment (ms)

    for block_str in blocks:
        if not block_str.strip():
            continue
        lines = block_str.split('\n')
        if len(lines) < 2:
            if block_str.strip(): output_srt_blocks.append(block_str) # Preserve malformed but non-empty
            continue

        original_index_line = lines[0]
        timestamp_line = lines[1]
        original_text_lines = lines[2:]

        if not original_index_line.strip().isdigit() or "-->" not in timestamp_line:
            if block_str.strip(): output_srt_blocks.append(block_str)
            continue
        
        try:
            start_ts_str, end_ts_str = timestamp_line.split(" --> ")
            original_start_ms = parse_timestamp_to_ms(start_ts_str.strip())
            original_end_ms = parse_timestamp_to_ms(end_ts_str.strip())
            original_duration_ms = original_end_ms - original_start_ms
        except ValueError:
            # logger.warning(f"Could not parse timestamp line in {input_srt_path}: {timestamp_line}")
            print(f"Warning: Could not parse timestamp line in {input_srt_path}: {timestamp_line}")
            if block_str.strip(): output_srt_blocks.append(block_str)
            continue

        if original_duration_ms <= 0: 
            # logger.warning(f"Cue {original_index_line.strip()} has zero or negative duration. Keeping original.")
            newline = '\n'  # Define newline outside f-string
            output_srt_blocks.append(f"{new_subtitle_index}\n{timestamp_line}\n{newline.join(original_text_lines)}\n")
            new_subtitle_index += 1
            continue

        text_segments = _split_text_into_segments(original_text_lines, max_words)
        num_segments = len(text_segments)

        if num_segments == 0 or (num_segments == 1 and not text_segments[0].strip()):
            # logger.info(f"Cue {original_index_line.strip()} resulted in no text segments. Skipping.")
            continue
        
        if num_segments == 1: # Text fits in one segment, or was empty and handled by _split_text_into_segments
            output_srt_blocks.append(f"{new_subtitle_index}\n{timestamp_line}\n{text_segments[0]}\n")
            new_subtitle_index += 1
            continue

        # Proceed with splitting into multiple timed segments
        current_segment_start_ms = float(original_start_ms)
        # Distribute duration proportionally, but ensure it sums up correctly.
        # Using word count for proportionality might be more accurate for reading speed.
        # For now, simple equal division of time.
        duration_per_segment_ms = float(original_duration_ms) / num_segments

        for i, segment_text in enumerate(text_segments):
            segment_start_ms = current_segment_start_ms
            
            if i == num_segments - 1: # Last segment takes all remaining time to match original end
                segment_end_ms = float(original_end_ms)
            else:
                segment_end_ms = segment_start_ms + duration_per_segment_ms
            
            # Ensure segments have a minimum duration and don't create invalid timings
            if segment_end_ms < segment_start_ms + min_segment_duration_ms:
                segment_end_ms = segment_start_ms + min_segment_duration_ms
            
            if segment_end_ms > original_end_ms: # Don't exceed original total duration
                segment_end_ms = float(original_end_ms)
            
            # If, after adjustments, the segment is invalid, skip it or log warning
            if segment_start_ms >= segment_end_ms:
                # logger.warning(f"Invalid segment duration for cue {original_index_line.strip()}, segment '{segment_text[:20]}...'. Skipping segment.")
                print(f"Warning: Invalid segment duration for cue {original_index_line.strip()}, segment '{segment_text[:20]}...'. Skipping segment.")
                if i == num_segments -1 : # If it's the last segment and it became invalid, try to give it minimal time at least
                    current_segment_start_ms = original_end_ms # effectively ending it
                else: # For intermediate segments, just move the start pointer
                    current_segment_start_ms = segment_end_ms # This might consume the time but let's see
                continue 

            new_ts_line = f"{format_ms_to_timestamp(int(round(segment_start_ms)))} --> {format_ms_to_timestamp(int(round(segment_end_ms)))}"
            output_srt_blocks.append(f"{new_subtitle_index}\n{new_ts_line}\n{segment_text}\n")
            new_subtitle_index += 1
            current_segment_start_ms = segment_end_ms

            if current_segment_start_ms >= original_end_ms and i < num_segments - 1:
                # logger.warning(f"Ran out of allocatable time for cue {original_index_line.strip()} after segment {i + 1}. Remaining segments dropped.")
                print(f"Warning: Ran out of allocatable time for cue {original_index_line.strip()} after segment {i + 1}. Remaining segments dropped.")
                break

    final_output_str = "\n\n".join(output_srt_blocks).strip()
    if final_output_str: # Add a final newline if there's any content
        final_output_str += "\n"

    try:
        with open(output_srt_path, 'w', encoding='utf-8') as outfile:
            outfile.write(final_output_str)
        # logger.info(f"Reformatted SRT file with new timestamps saved to: {output_srt_path}")
        print(f"Reformatted SRT file with new timestamps saved to: {output_srt_path}")
        return True
    except Exception as e:
        # logger.error(f"Error writing output SRT file {output_srt_path}: {e}", exc_info=True)
        print(f"Error writing output SRT file {output_srt_path}: {e}")
        return False

async def reformat_srt_file_timed_async(input_srt_path: str, output_srt_path: str, max_words: int = MAX_WORDS_PER_LINE) -> bool:
    """
    Asynchronously reformats an SRT file, adjusting text and timestamps.
    """
    # logger.debug(f"Queueing SRT reformatting for {input_srt_path} to {output_srt_path}")
    return await asyncio.to_thread(_blocking_reformat_srt_file_timed, input_srt_path, output_srt_path, max_words) 