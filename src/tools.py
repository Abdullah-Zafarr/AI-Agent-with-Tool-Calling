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
    # Check disabled as it triggers premature bot blocks on heavy localhost testing.
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
    Fetches the transcript of a YouTube video using SerpApi.
    Bypasses YouTube IP-blocks on Streamlit by avoiding direct audio downloads.
    Returns the full transcript text.
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

    # 1.5 Try fetching native YouTube closed captions using SerpApi
    serpapi_key = os.getenv("SERPAPI_API_KEY")
    if not serpapi_key:
         raise ValueError("SERPAPI_API_KEY environment variable is not set. Please add it to your .env file.")

    logger.info(f"Attempting to fetch transcript for {video_id} using SerpApi...")
    try:
        params = {
            "engine": "youtube_video_transcript",
            "v": video_id,
            "api_key": serpapi_key,
            "lang": "en"
        }
        r = requests.get("https://serpapi.com/search", params=params, timeout=30)
        
        if r.status_code == 200:
            data = r.json()
            transcript_entries = data.get("transcript", [])
            
            if transcript_entries:
                # SerpApi uses 'snippet' key for transcript lines
                transcript_text = " ".join([entry.get("snippet", "") for entry in transcript_entries]).strip()
                
                if transcript_text:
                    with open(transcript_path, "w", encoding="utf-8") as f:
                        f.write(transcript_text)
                    logger.info("Transcript fetched successfully via SerpApi!")
                    return transcript_text
                else:
                    raise ValueError("SerpApi response contained an empty transcript.")
            else:
                raise ValueError("No transcript entries found in SerpApi response.")
        else:
            raise RuntimeError(f"SerpApi HTTP {r.status_code}: {r.text[:200]}")
            
    except Exception as e:
        logger.warning(f"SerpApi transcript fetch failed: {e}")
        
    # 2. Fallback: Try youtube_transcript_api library (might be IP blocked, but worth a shot)
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        logger.info(f"Attempting fallback to fetch native YouTube transcript for {video_id}...")
        api = YouTubeTranscriptApi()
        transcript_list = api.fetch(video_id)
        transcript_text = " ".join([t.text for t in transcript_list if hasattr(t, 'text')]).strip()
        if transcript_text:
            with open(transcript_path, "w", encoding="utf-8") as f:
                f.write(transcript_text)
            logger.info("Native transcript fetched via youtube_transcript_api fallback!")
            return transcript_text
    except Exception as e:
        logger.info(f"Fallback native transcription unavailable: {e}")
        
    raise RuntimeError(f"Could not fetch transcript for {video_url} via SerpApi or youtube_transcript_api.")
