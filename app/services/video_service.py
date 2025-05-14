import os
import uuid
import asyncio
import logging
import aiofiles
import shutil
import time # Added for timing
from typing import List

from core.config import settings
from utils.file_utils import ensure_dir, cleanup_dir, download_file, get_file_extension_from_url
from utils.ffmpeg_utils import run_ffmpeg_async, get_media_duration
from services.supabase_service import update_video_record_status, upload_to_supabase_storage
# New imports for subtitle processing
from utils.transcription_utils import generate_srt_from_audio
from utils.srt_utils import reformat_srt_file_timed_async
import shlex # For escaping subtitle font file path if needed

logger = logging.getLogger(__name__)

async def create_video_task(
    video_id: str,
    user_id: str,
    image_urls: List[str],
    audio_url: str
):
    """The background task performing the video generation."""
    start_time = time.monotonic() # Record start time
    unique_suffix = f"{video_id[:8]}-{uuid.uuid4().hex[:6]}" # Short unique ID for temp files
    temp_dir = os.path.join(settings.temp_dir_base, unique_suffix)
    final_video_path_local = ""
    
    # Paths for subtitle files
    initial_srt_path = os.path.join(temp_dir, f"subtitles_initial-{unique_suffix}.srt")
    reformatted_srt_path = os.path.join(temp_dir, f"subtitles_reformatted-{unique_suffix}.srt")
    video_with_subs_path = "" # Will be set if subtitles are added

    try:
        ensure_dir(temp_dir)
        ensure_dir(settings.output_dir) # Ensure final output dir exists
        logger.info(f"[{video_id}] Starting video creation. Temp dir: {temp_dir}")
        await update_video_record_status(video_id, status="processing")

        # --- Download Files --- 
        download_tasks = []
        downloaded_image_paths = {}
        downloaded_audio_path = None

        # Download Images
        for i, img_url in enumerate(image_urls):
            ext = get_file_extension_from_url(img_url)
            img_filename = f"image-{i}{ext}"
            img_path = os.path.join(temp_dir, img_filename)
            download_tasks.append(asyncio.create_task(download_file(img_url, img_path), name=f"img-{i}"))
            downloaded_image_paths[f"img-{i}"] = img_path

        # Download Audio
        audio_ext = get_file_extension_from_url(audio_url)
        audio_filename = f"audio{audio_ext}"
        audio_path = os.path.join(temp_dir, audio_filename)
        download_tasks.append(asyncio.create_task(download_file(audio_url, audio_path), name="audio"))
        downloaded_audio_path = audio_path

        results = await asyncio.gather(*download_tasks, return_exceptions=True)
        
        successfully_downloaded_images = []
        successfully_downloaded_audio = None
        download_errors = []

        for i, result in enumerate(results):
            task_name = download_tasks[i].get_name()
            if isinstance(result, Exception) or result is False:
                error_msg = f"Failed to download {task_name}: {result if isinstance(result, Exception) else 'Unknown error'}"
                logger.error(f"[{video_id}] {error_msg}")
                download_errors.append(error_msg)
            else:
                if task_name.startswith("img-"):
                    successfully_downloaded_images.append(downloaded_image_paths[task_name])
                elif task_name == "audio":
                    successfully_downloaded_audio = downloaded_audio_path
        
        if not successfully_downloaded_images:
            raise ValueError("Failed to download any images.")
        if not successfully_downloaded_audio:
             logger.warning(f"[{video_id}] Failed to download audio, proceeding without audio and subtitles.")

        logger.info(f"[{video_id}] Successfully downloaded images: {len(successfully_downloaded_images)}/{len(image_urls)}")
        if successfully_downloaded_audio:
             logger.info(f"[{video_id}] Successfully downloaded audio: {successfully_downloaded_audio}")

        # --- Get Audio Duration --- 
        audio_duration_seconds = None
        if successfully_downloaded_audio:
            audio_duration_seconds = await get_media_duration(successfully_downloaded_audio)
            if audio_duration_seconds:
                logger.info(f"[{video_id}] Detected audio duration: {audio_duration_seconds:.2f} seconds")
            else:
                logger.warning(f"[{video_id}] Could not determine audio duration. Using default video timings.")

        # --- Calculate Video Part Durations --- 
        default_slideshow_duration = 60.0
        default_zoom_duration = 60.0

        if audio_duration_seconds is not None and audio_duration_seconds > 0:
            actual_slideshow_duration = min(audio_duration_seconds, default_slideshow_duration)
            actual_zoom_duration = max(0.0, audio_duration_seconds - actual_slideshow_duration)
            logger.info(f"[{video_id}] Calculated durations - Slideshow: {actual_slideshow_duration:.2f}s, Zoom: {actual_zoom_duration:.2f}s")
        else:
            actual_slideshow_duration = default_slideshow_duration
            actual_zoom_duration = default_zoom_duration
            logger.info(f"[{video_id}] Using default durations - Slideshow: {actual_slideshow_duration:.2f}s, Zoom: {actual_zoom_duration:.2f}s")

        # --- Video Processing Steps --- 
        video_parts_to_concat = []
        
        # --- PART 1: Slideshow --- 
        part1_filename = f"part1-{unique_suffix}.mp4"
        part1_output_path = os.path.join(temp_dir, part1_filename)
        # Calculate duration per image based on the actual slideshow duration
        duration_per_image_part1 = actual_slideshow_duration / len(successfully_downloaded_images)
        duration_per_image_part1 = max(0.01, duration_per_image_part1) # Ensure positive duration

        # Create file list for ffmpeg concat demuxer
        filelist_content_part1 = "\n".join([f"file '{os.path.relpath(p, temp_dir).replace(os.sep, '/')}'\nduration {duration_per_image_part1:.6f}" for p in successfully_downloaded_images])
        filelist_path_part1 = os.path.join(temp_dir, f"filelist_part1-{unique_suffix}.txt")
        async with aiofiles.open(filelist_path_part1, 'w') as f:
            await f.write(filelist_content_part1)
        
        # New VF for Part 1: Scale to cover 1024x720, then center crop
        # Input images are 1792x1024. Target is 1024x720.
        # We need to scale so that the image covers the 1024x720 area, then crop.
        # scale=w='max(iw*target_h/ih,target_w)':h='max(target_h,ih*target_w/iw)'
        # Simplified: scale to be at least target_w wide and target_h tall, then crop.
        # Example: scale='max(1024,ih*1024/720)':'max(720,iw*720/1024)' - this is a bit complex.
        # Easier: scale so one dimension fits and the other overflows, then crop.
        # To cover 1024x720: scale to width 1024, height will be 1024 * (1024/1792) = 585 (too small)
        # OR scale to height 720, width will be 720 * (1792/1024) = 1260 (covers width)
        # So, we scale to the height that ensures coverage, or width that ensures coverage.
        # General formula: scale=w=max(iw*Th/ih, Tw):h=max(Th, ih*Tw/iw)
        # iw=1792, ih=1024, Tw=1024, Th=720
        # w = max(1792*720/1024, 1024) = max(1260, 1024) = 1260
        # h = max(720, 1024*1024/1792) = max(720, 585.14) = 720
        # So scale=1260:720. Then crop to 1024x720.
        # The filter [0:v]scale=iw*max(1024/iw\,720/ih):ih*max(1024/iw\,720/ih),crop=1024:720
        # A more common "cover" approach:
        vf_part1 = (
            f"scale='{settings.target_video_width}:{settings.target_video_height}:force_original_aspect_ratio=increase',"
            f"crop={settings.target_video_width}:{settings.target_video_height}:(iw-{settings.target_video_width})/2:(ih-{settings.target_video_height})/2,"
            f"format=pix_fmts=yuv420p"
        )

        ffmpeg_args_part1 = [
            '-f', 'concat','-safe', '0','-i', filelist_path_part1,
            '-vf', vf_part1, # Use the new cover & crop vf
            '-r', str(settings.target_fps), '-y', part1_output_path # Removed -t, duration should be controlled by filelist
        ]
        success, _, stderr = await run_ffmpeg_async(ffmpeg_args_part1, f"[{video_id}] Part 1 (Slideshow)")
        if not success:
            raise RuntimeError(f"Failed to generate Part 1 (Slideshow): {stderr}")
        video_parts_to_concat.append(part1_output_path)
        logger.info(f"[{video_id}] Part 1 (Slideshow - {actual_slideshow_duration:.2f}s) generated: {part1_output_path}")

        # --- PART 2: Zoom Effect on Last Image (Conditional) --- 
        if actual_zoom_duration > 0 and successfully_downloaded_images:
            last_image_path = successfully_downloaded_images[-1]
            part2_filename = f"part2-{unique_suffix}.mp4"
            part2_output_path = os.path.join(temp_dir, part2_filename)
            
            # Check if high-quality zoom is enabled in settings
            use_hq_zoom = getattr(settings, 'use_high_quality_zoom', False)
            
            if use_hq_zoom:
                # High-quality alternating (ping-pong) zoom effect
                logger.info(f"[{video_id}] Using high-quality alternating zoom effect.")
                
                # Get alternating zoom settings from config
                input_fps = settings.hq_zoom_input_framerate # e.g., 25
                output_fps = settings.hq_zoom_output_framerate # e.g., 25
                initial_scale_width = settings.hq_zoom_initial_scale # e.g., 4000
                
                pingpong_increment = settings.hq_zoom_pingpong_increment # e.g., 0.0015
                one_direction_duration_s = settings.hq_zoom_pingpong_duration_s # e.g., 20 seconds
                max_zoom_factor = settings.hq_zoom_max_factor # e.g., 1.5
                min_zoom_factor = 1.0 # Standard minimum zoom

                one_direction_frames = int(one_direction_duration_s * output_fps)
                full_cycle_frames = one_direction_frames * 2
                
                # Total frames for the entire zoom duration of this video part
                total_duration_frames = int(actual_zoom_duration * output_fps)
                
                # Construct the z expression for zoompan
                # 'on' is the output frame number, starting from 0
                # 'zoom' is the zoom level from the previous frame (starts at 1.0)
                z_expression = (
                    f"if(lt(mod(on,{full_cycle_frames}),{one_direction_frames}),"
                    f"min(zoom+{pingpong_increment},{max_zoom_factor}),"
                    f"max(zoom-{pingpong_increment},{min_zoom_factor}))"
                )
                
                zoom_pan_vf = (
                    f"scale={initial_scale_width}:-1," # Upscale width, maintain aspect ratio
                    f"zoompan=z='{z_expression}':" 
                    f"x='iw/2-(iw/zoom/2)':" 
                    f"y='ih/2-(ih/zoom/2)':" 
                    f"d={total_duration_frames}:" # Duration in frames for the entire output segment
                    f"s={settings.target_video_width}x{settings.target_video_height}:" # Output resolution
                    f"fps={output_fps}," 
                    f"format=pix_fmts=yuv420p"
                )
                
                ffmpeg_args_part2 = [
                    '-loop', '1',
                    '-framerate', str(input_fps),
                    '-i', last_image_path,
                    '-vf', zoom_pan_vf,
                    '-t', str(actual_zoom_duration), # Total duration of this zoom part
                    '-c:v', 'libx264',
                    '-preset', settings.ffmpeg_preset,
                    '-crf', str(settings.ffmpeg_crf),
                    '-y',
                    part2_output_path
                ]
            else:
                # Original approach with sinusoidal zoom (default)
                logger.info(f"[{video_id}] Using standard zoom effect")
                zoom_cycle_duration_seconds = 15 # Keep zoom cycle speed
                zoom_amplitude = 0.25 # Keep zoom amplitude
                total_zoom_frames = int(actual_zoom_duration * settings.target_fps)

                zoom_pan_vf = (
                    f"scale=w='max(iw*{settings.target_video_height}/ih,{settings.target_video_width})':h='max({settings.target_video_height},ih*{settings.target_video_width}/iw)':force_original_aspect_ratio=increase," # Scale to cover
                    f"crop=w={settings.target_video_width}:h={settings.target_video_height}," # Crop to target
                    f"zoompan=z='1+{zoom_amplitude}*sin(2*PI*on/({settings.target_fps}*{zoom_cycle_duration_seconds}))':" # Zoom expr
                    f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':" # Center expr
                    f"d={total_zoom_frames}:" # Duration in frames
                    f"s={settings.target_video_width}x{settings.target_video_height}:" # Output size
                    f"fps={settings.target_fps}," # Output FPS for zoompan
                    f"format=pix_fmts=yuv420p" # Ensure pixel format
                )

                ffmpeg_args_part2 = [
                    '-loop', '1',
                    '-i', last_image_path,
                    '-vf', zoom_pan_vf,
                    '-t', str(actual_zoom_duration),
                    '-r', str(settings.target_fps),
                    '-y',
                    part2_output_path
                ]
            
            success, _, stderr = await run_ffmpeg_async(ffmpeg_args_part2, f"[{video_id}] Part 2 (Zoom Effect)")
            if success:
                 video_parts_to_concat.append(part2_output_path)
                 logger.info(f"[{video_id}] Part 2 (Zoom Effect - {actual_zoom_duration:.2f}s) generated: {part2_output_path}")
            else:
                 # Log warning but continue, video will be shorter
                 logger.warning(f"[{video_id}] Failed to generate Part 2 (Zoom Effect), proceeding without it. Error: {stderr}")
        else:
            logger.info(f"[{video_id}] Skipping Part 2 (Zoom Effect) as calculated duration is zero or negative.")
        
        # --- PART 3: Concatenate Video Parts (Intermediate Step) --- 
        combined_video_no_audio_subs_filename = f"combined_no_audio_subs-{unique_suffix}.mp4"
        combined_video_no_audio_subs_path = os.path.join(temp_dir, combined_video_no_audio_subs_filename)

        if len(video_parts_to_concat) == 1:
            logger.info(f"[{video_id}] Only one video part, copying to intermediate path.")
            shutil.copyfile(video_parts_to_concat[0], combined_video_no_audio_subs_path)
        else:
            logger.info(f"[{video_id}] Concatenating {len(video_parts_to_concat)} video parts.")
            concat_list_content_intermediate = "\n".join([f"file '{os.path.relpath(p, temp_dir).replace(os.sep, '/')}'" for p in video_parts_to_concat])
            concat_list_path_intermediate = os.path.join(temp_dir, f"concat_list_intermediate-{unique_suffix}.txt")
            async with aiofiles.open(concat_list_path_intermediate, 'w') as f:
                await f.write(concat_list_content_intermediate)
            logger.debug(f"[{video_id}] Intermediate concat list:\n{concat_list_content_intermediate}")

            ffmpeg_args_concat_intermediate = [
                '-f', 'concat',
                '-safe', '0',
                '-i', concat_list_path_intermediate,
                '-c', 'copy', # Fast concatenation if codecs match
                '-y', # Add this flag to overwrite output without asking
                combined_video_no_audio_subs_path
            ]
            success, _, stderr = await run_ffmpeg_async(ffmpeg_args_concat_intermediate, f"[{video_id}] Intermediate Concatenation")
            if not success:
                raise RuntimeError(f"Failed intermediate concatenation: {stderr}")

        logger.info(f"[{video_id}] Intermediate combined video (no audio/subs): {combined_video_no_audio_subs_path}")

        # --- NEW: SUBTITLE GENERATION AND PROCESSING (COMMENTED OUT) --- 
        generated_srt_ready_for_burn = False # Subtitles are disabled
        # if successfully_downloaded_audio:
        #     logger.info(f"[{video_id}] Starting audio transcription for subtitles...")
        #     transcribed_ok = await generate_srt_from_audio(successfully_downloaded_audio, initial_srt_path, model_name=settings.whisper_model)
        #     if transcribed_ok and os.path.exists(initial_srt_path):
        #         logger.info(f"[{video_id}] Transcription successful: {initial_srt_path}. Reformatting SRT...")
        #         reformatted_ok = await reformat_srt_file_timed_async(initial_srt_path, reformatted_srt_path, max_words=settings.srt_max_words_per_line)
        #         if reformatted_ok and os.path.exists(reformatted_srt_path):
        #             logger.info(f"[{video_id}] SRT reformatted successfully: {reformatted_srt_path}")
        #             generated_srt_ready_for_burn = True
        #         else:
        #             logger.warning(f"[{video_id}] SRT reformatting failed for {initial_srt_path}")
        #     else:
        #         logger.warning(f"[{video_id}] Transcription failed or initial SRT not found. Skipping subtitles.")
        # else:
        #     logger.info(f"[{video_id}] No audio downloaded, skipping subtitle generation.")
        logger.info(f"[{video_id}] Subtitle generation and burning is currently commented out.")

        # --- NEW: BURN SUBTITLES ONTO VIDEO (COMMENTED OUT) --- 
        current_video_base_for_final_step = combined_video_no_audio_subs_path # Default to video without subs
        # if generated_srt_ready_for_burn: # This condition will now always be false
        #     video_with_subs_path = os.path.join(temp_dir, f"video_with_subs-{unique_suffix}.mp4")
        #     logger.info(f"[{video_id}] Burning subtitles from {reformatted_srt_path} onto {combined_video_no_audio_subs_path}")
            
        #     font_file_path = os.path.abspath(settings.subtitle_font_file) 
        #     if not os.path.exists(font_file_path):
        #         logger.warning(f"[{video_id}] Subtitle font file not found: {font_file_path}. Subtitles might not use custom font.")
        #         font_file_filter_path = "" 
        #     else:
        #         font_file_filter_path = font_file_path.replace(os.sep, '/')
            
        #     abs_reformatted_srt_path = os.path.abspath(reformatted_srt_path).replace(os.sep, '/')

        #     base_subtitle_string = f"subtitles='{abs_reformatted_srt_path}'"
        #     style_parts = []
        #     if font_file_filter_path:
        #          style_parts.append(f"Fontfile='{font_file_filter_path}'")
        #     style_parts.append(f"Fontsize={settings.subtitle_font_size}")
        #     style_parts.append(f"PrimaryColour={settings.subtitle_primary_colour}")
        #     style_parts.append(f"OutlineColour={settings.subtitle_outline_colour}")
        #     style_parts.append(f"BorderStyle={settings.subtitle_border_style}")
        #     style_parts.append(f"Outline={settings.subtitle_outline_thickness}")
        #     style_parts.append(f"MarginV={settings.subtitle_margin_v}")
        #     style_parts.append(f"WrapStyle={settings.subtitle_wrap_style}")
            
        #     force_style_value = ",".join(style_parts)
        #     subtitle_filter_value = f"{base_subtitle_string}:force_style='{force_style_value}'"

        #     ffmpeg_args_burn_subs = [
        #         '-i', combined_video_no_audio_subs_path,
        #         '-vf', subtitle_filter_value,
        #         '-c:a', 'copy',
        #         '-c:v', 'libx264', '-preset', 'fast', '-crf', '23',
        #         '-y', video_with_subs_path
        #     ]
        #     success, _, stderr = await run_ffmpeg_async(ffmpeg_args_burn_subs, f"[{video_id}] Burning Subtitles")
        #     if success:
        #         logger.info(f"[{video_id}] Subtitles burned successfully: {video_with_subs_path}")
        #         current_video_base_for_final_step = video_with_subs_path
        #     else:
        #         logger.error(f"[{video_id}] Failed to burn subtitles. Error: {stderr}. Proceeding without hardcoded subtitles.")

        # --- PART 4: Add Audio (and potentially other overlays like Dust) --- 
        final_video_filename = f"video-{video_id}.mp4" # Use persistent ID in final name
        final_video_path_local = os.path.join(settings.output_dir, final_video_filename)
        
        # --- Overlay logic commented out ---
        # dust_overlay_video_path = os.path.join(os.getcwd(), settings.dust_overlay_file_name)
        # dust_overlay_exists = os.path.exists(dust_overlay_video_path)
        # if not dust_overlay_exists:
        #      logger.warning(f"[{video_id}] Dust overlay video not found at {dust_overlay_video_path}. Skipping overlay.")

        # --- Corrected Input and Index Logic for FFmpeg --- 
        ffmpeg_input_flags = [] # Stores the actual ffmpeg -i, -stream_loop flags and paths
        current_ffmpeg_input_index = 0
        
        # Input 0: Main video
        main_video_ffmpeg_index = current_ffmpeg_input_index
        ffmpeg_input_flags.extend(['-i', current_video_base_for_final_step])
        current_ffmpeg_input_index += 1
        
        # Optional: Dust Overlay - Commented out
        overlay_ffmpeg_index = -1 # This will ensure overlay is not applied
        # if dust_overlay_exists:
        #     overlay_ffmpeg_index = current_ffmpeg_input_index
        #     ffmpeg_input_flags.extend(['-stream_loop', '-1'])
        #     ffmpeg_input_flags.extend(['-i', dust_overlay_video_path])
        #     current_ffmpeg_input_index += 1
        #     logger.info(f"[{video_id}] Applying dust overlay (FFmpeg Input {overlay_ffmpeg_index}): {dust_overlay_video_path}")
            
        # Optional: Audio
        audio_ffmpeg_index = -1
        if successfully_downloaded_audio:
            audio_ffmpeg_index = current_ffmpeg_input_index
            ffmpeg_input_flags.extend(['-i', successfully_downloaded_audio])
            current_ffmpeg_input_index += 1
            logger.info(f"[{video_id}] Adding audio track (FFmpeg Input {audio_ffmpeg_index}): {successfully_downloaded_audio}")
            
        # --- Build Filter Complex and Maps using correct FFmpeg indices ---
        filter_complex_string = ""
        map_flags = []

        video_output_node = f"[{main_video_ffmpeg_index}:v]"

        if overlay_ffmpeg_index != -1: # This block will now be skipped
            filter_complex_string = (
                f"[{overlay_ffmpeg_index}:v]format=rgba,scale={settings.target_video_width}:{settings.target_video_height},setsar=1,colorchannelmixer=aa=1[overlay_scaled];"
                f"{video_output_node}[overlay_scaled]blend=all_mode=screen:shortest=1[out_v]"
            )
            video_output_node = "[out_v]"

        # Determine the correct video map label
        final_video_map_label = ""
        if filter_complex_string: # If a video filter complex is active
            final_video_map_label = video_output_node # Should be like [out_v]
        else: # No video filter complex active, map directly from input
            final_video_map_label = f"{main_video_ffmpeg_index}:v" # Should be like 0:v

        map_flags.extend(['-map', final_video_map_label])

        if audio_ffmpeg_index != -1:
            map_flags.extend(['-map', f"{audio_ffmpeg_index}:a"])
        # else: pass # Assuming combined video has no audio we want

        # --- Assemble the final command list --- 
        ffmpeg_command_final = list(ffmpeg_input_flags) # Start with input flags

        if filter_complex_string:
             ffmpeg_command_final.extend(['-filter_complex', filter_complex_string])

        ffmpeg_command_final.extend(map_flags) # Add map flags

        # Add encoding parameters
        encoding_flags = [
            '-c:v', 'libx264',
            '-preset', 'fast',
            '-crf', '23',
            '-pix_fmt', 'yuv420p',
            '-c:a', 'aac',
            '-b:a', '192k',
            '-r', str(settings.target_fps),
        ]
        ffmpeg_command_final.extend(encoding_flags)
        
        # Add '-shortest' flag conditionally (before output)
        if audio_ffmpeg_index != -1:
            ffmpeg_command_final.append('-shortest')

        # Add output file path (and -y flag before it)
        ffmpeg_command_final.append('-y') # Add this flag to overwrite output without asking
        ffmpeg_command_final.append(final_video_path_local)

        # Log the final command for debugging
        logger.debug(f"[{video_id}] Executing FFmpeg command: {' '.join(ffmpeg_command_final)}")

        success, _, stderr = await run_ffmpeg_async(ffmpeg_command_final, f"[{video_id}] Final Processing (Audio/Overlay)")
        if not success:
            # Log the command again on failure for easier debugging
            logger.error(f"[{video_id}] Failed FFmpeg command: {' '.join(ffmpeg_command_final)}")
            raise RuntimeError(f"Failed final video processing: {stderr}")

        logger.info(f"[{video_id}] Final video generated locally: {final_video_path_local}")

        # --- Upload to Supabase Storage --- 
        # Commented out Supabase upload
        supabase_destination_path = f"user_{user_id}/{os.path.basename(final_video_path_local)}"
        public_video_url = await upload_to_supabase_storage(final_video_path_local, supabase_destination_path)

        if not public_video_url:
            raise RuntimeError("Failed to upload final video to Supabase Storage.")

        # --- Calculate Duration & Update Database ---
        end_time = time.monotonic() # Record end time
        processing_duration_seconds = end_time - start_time
        minutes_taken = round(processing_duration_seconds / 60, 2) # Calculate minutes_taken
        
        await update_video_record_status(
            video_id, 
            status="completed", 
            final_video_url=public_video_url, 
            minutes_taken=minutes_taken # Pass minutes_taken
        )
        logger.info(f"[{video_id}] Video creation process completed successfully in {minutes_taken:.2f} minutes. Saved locally at: {final_video_path_local}")

    except Exception as e:
        logger.exception(f"[{video_id}] Error during video creation task: {e}")
        # Update DB with error status
        await update_video_record_status(video_id, status="failed", error_message=str(e))

    finally:
        # --- Cleanup --- 
        cleanup_dir(temp_dir)
        # Optionally remove local final video if only cloud storage is needed
        # if os.path.exists(final_video_path_local):
        #     try:
        #         os.remove(final_video_path_local)
        #         logger.info(f"[{video_id}] Removed local final video: {final_video_path_local}")
        #     except OSError as e:
        #         logger.error(f"[{video_id}] Failed to remove local final video {final_video_path_local}: {e}")
        pass # Keep local file in public/generated-videos for now 