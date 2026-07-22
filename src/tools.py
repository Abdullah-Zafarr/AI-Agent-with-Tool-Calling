import os
import time
import logging
import re
import urllib.parse as urlparse
import hashlib
import requests
import yt_dlp
from google import genai

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

YOUTUBE_VIDEO_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?[^ ]*?v=|embed/|v/|live/|shorts/)|youtu\.be/)([A-Za-z0-9_-]{11})"
)

def sanitize_youtube_url(url: str) -> str:
    """
    Normalizes noisy model-generated YouTube URLs into a clean watch URL.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("A non-empty YouTube video URL is required.")

    match = YOUTUBE_VIDEO_ID_RE.search(url.strip())
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"

    parsed = urlparse.urlparse(url.strip().strip("[]'\"{}()"))
    if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com') and parsed.path == '/watch':
        video_id = urlparse.parse_qs(parsed.query).get('v', [None])[0]
        if video_id:
            return f"https://www.youtube.com/watch?v={video_id[:11]}"

    raise ValueError(f"Could not extract a valid YouTube video ID from: {url}")

def extract_video_id(url: str) -> str:
    """
    Extracts the video ID from a YouTube URL.
    """
    try:
        url = sanitize_youtube_url(url)
    except ValueError:
        pass
    try:
        parsed = urlparse.urlparse(url)
        if parsed.hostname in ('youtu.be', 'www.youtu.be'):
            return parsed.path[1:]
        if parsed.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if parsed.path == '/watch':
                p = urlparse.parse_qs(parsed.query)
                v = p.get('v')
                if v:
                    return v[0]
            if parsed.path.startswith(('/embed/', '/v/')):
                return parsed.path.split('/')[2]
            if parsed.path.startswith('/live/'):
                return parsed.path.split('/')[2]
    except Exception as e:
        logger.warning(f"Error parsing video URL: {e}")
    
    # Fallback to MD5 hash if extraction fails
    return hashlib.md5(url.encode()).hexdigest()[:11]

def _can_download_audio(video_url: str) -> tuple[bool, str]:
    """
    Checks whether yt-dlp can access audio metadata without downloading it.
    This filters out DRM/private/unavailable videos before the agent transcribes.
    Uses default yt-dlp client selection to avoid false DRM positives caused
    by restrictive player_client configurations.
    """
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(video_url, download=False)
    except Exception as e:
        return False, str(e)

    if info.get("is_live"):
        return False, "Live videos are skipped because their transcript is unstable."
    if info.get("live_status") in {"is_live", "is_upcoming"}:
        return False, "Live or upcoming videos are skipped."

    formats = info.get("formats") or []
    has_audio = any(fmt.get("acodec") and fmt.get("acodec") != "none" for fmt in formats)
    if not has_audio:
        return False, "No downloadable audio format was found."

    return True, ""

def video_search_tool(query: str) -> str:
    """
    Calls SerpApi to get a YouTube video link based on a query.
    Returns the first downloadable, non-DRM video's URL.
    """
    api_key = os.getenv("SERPAPI_API_KEY")
    if not api_key:
         # Check if it was loaded but is empty
         raise ValueError("SERPAPI_API_KEY environment variable is not set. Please add it to your .env file.")
         
    url = "https://serpapi.com/search.json"
    params = {
        "engine": "youtube",
        "search_query": query,
        "api_key": api_key
    }
    
    logger.info(f"Searching SerpApi YouTube for: {query}")
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except Exception as e:
        raise RuntimeError(f"SerpApi request failed: {e}")
        
    video_results = data.get("video_results", [])
    if not video_results:
        raise ValueError(f"No video results found on YouTube for query: '{query}'")
        
    skipped = []
    for result in video_results:
        video_url = result.get("link")
        if not video_url:
            continue

        try:
            clean_url = sanitize_youtube_url(video_url)
        except ValueError as e:
            skipped.append(f"{video_url}: {e}")
            continue

        can_download, reason = _can_download_audio(clean_url)
        if can_download:
            logger.info(f"Found downloadable YouTube video: {clean_url}")
            return clean_url

        title = result.get("title", clean_url)
        logger.info(f"Skipping unavailable video '{title}': {reason}")
        skipped.append(f"{title}: {reason}")

    details = "; ".join(skipped[:3])
    raise ValueError(
        "No downloadable non-DRM YouTube video results were found for this query."
        + (f" Skipped examples: {details}" if details else "")
    )

def transcription_tool(video_url: str) -> str:
    """
    Downloads the audio of a YouTube video, uploads it to the Gemini API,
    transcribes it, stores the transcript in a text file, and cleans up.
    Returns a status message with the saved file path.
    """
    # 1. Setup paths
    video_url = sanitize_youtube_url(video_url)
    video_id = extract_video_id(video_url)
    os.makedirs("transcripts", exist_ok=True)
    transcript_path = os.path.join("transcripts", f"{video_id}.txt")
    
    # Check if we already transcribed this video
    if os.path.exists(transcript_path):
        logger.info(f"Transcription file already exists: {transcript_path}")
        with open(transcript_path, "r", encoding="utf-8") as f:
            return f.read()
        
    # 2. Download audio using yt-dlp
    logger.info(f"Downloading audio from: {video_url}")
    import tempfile
    temp_dir = tempfile.gettempdir()
    output_template = os.path.join(temp_dir, f'youtube_{video_id}_temp.%(ext)s')
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }
    
    local_file = None
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(video_url, download=True)
            candidate_file = ydl.prepare_filename(info_dict)
            
            # Resolve the actual file path
            if os.path.exists(candidate_file):
                local_file = candidate_file
            else:
                base, _ = os.path.splitext(candidate_file)
                for ext in ['.m4a', '.mp3', '.webm', '.wav']:
                    if os.path.exists(base + ext):
                        local_file = base + ext
                        break
                        
        if not local_file or not os.path.exists(local_file):
            raise FileNotFoundError(f"Failed to find downloaded audio file for template: {output_template}")
            
        logger.info(f"Audio downloaded locally to: {local_file}")
        
        # 3. Upload audio to Gemini API
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        if not gemini_api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set. Please add it to your .env file.")
            
        client = genai.Client(api_key=gemini_api_key)
        
        logger.info("Uploading audio file to Gemini...")
        uploaded_file = client.files.upload(file=local_file)
        logger.info(f"Uploaded to Gemini. Remote name: {uploaded_file.name}. State: {uploaded_file.state.name}")
        
        # Wait for file to be processed if necessary
        while uploaded_file.state.name == "PROCESSING":
            logger.info("Gemini is processing the uploaded file. Waiting 5 seconds...")
            time.sleep(5)
            uploaded_file = client.files.get(name=uploaded_file.name)
            
        if uploaded_file.state.name == "FAILED":
            raise RuntimeError("Gemini file processing failed.")
            
        logger.info("File is active. Starting transcript generation with Gemini...")
        
        # 4. Transcribe using Gemini Model (trying latest models with fallback)
        model_candidates = ["gemini-3.1-flash-lite"]
        response = None
        last_error = None
        
        prompt = (
            "Please transcribe the following audio file completely and accurately. "
            "Ensure you catch all spoken words. Do not insert any commentary or pleasantries, "
            "just provide the direct transcript."
        )
        
        for model_name in model_candidates:
            try:
                logger.info(f"Attempting transcription using model: {model_name}...")
                response = client.models.generate_content(
                    model=model_name,
                    contents=[uploaded_file, prompt]
                )
                logger.info(f"Transcription successful using model: {model_name}")
                break
            except Exception as e:
                logger.warning(f"Model {model_name} failed: {e}")
                last_error = e
                
        if response is None:
            raise RuntimeError(f"All transcription model candidates failed. Last error: {last_error}")
        
        transcript_text = response.text
        if not transcript_text:
            raise ValueError("Gemini returned an empty transcription response.")
            
        # 5. Save the transcript to file
        with open(transcript_path, "w", encoding="utf-8") as f:
            f.write(transcript_text)
            
        logger.info(f"Successfully saved transcript to {transcript_path}")
        
        # Clean up files in Gemini
        try:
            client.files.delete(name=uploaded_file.name)
            logger.info(f"Cleaned up remote Gemini file: {uploaded_file.name}")
        except Exception as e:
            logger.warning(f"Failed to clean up remote Gemini file: {e}")
            
        return transcript_text
        
    finally:
        # Clean up local audio file
        if local_file and os.path.exists(local_file):
            try:
                os.remove(local_file)
                logger.info(f"Cleaned up local temporary audio file: {local_file}")
            except Exception as e:
                logger.warning(f"Failed to delete local audio file {local_file}: {e}")
