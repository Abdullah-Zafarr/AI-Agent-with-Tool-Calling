import os
import logging
import streamlit as st

import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import src.tools as tools

from dotenv import load_dotenv
load_dotenv(override=True)

# Import and reload tools and agent to prevent caching of stale function signatures
import src.tools as tools
import src.agent as agent
import importlib
importlib.reload(tools)
importlib.reload(agent)

st.set_page_config(
    page_title="Video Transcription Agent",
    page_icon=None,
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600&family=Outfit:wght@700;800;900&family=Syne:wght@700;800&family=DM+Serif+Display&display=swap');

    html, body, [data-testid="stAppViewContainer"] {
        background-color: #111214;
        background-image: 
            linear-gradient(to right, #18191C 1px, transparent 1px),
            linear-gradient(to bottom, #18191C 1px, transparent 1px);
        background-size: 50px 50px;
        color: #D4D4D8;
        font-family: 'Inter', sans-serif;
        font-size: 14px;
    }

    [data-testid="stSidebar"] {
        background-color: #111214 !important;
        background-image: 
            radial-gradient(circle at 50% 0%, #1E1F24 0%, transparent 75%),
            linear-gradient(to right, #18191C 1px, transparent 1px),
            linear-gradient(to bottom, #18191C 1px, transparent 1px) !important;
        background-size: 100% 100%, 50px 50px, 50px 50px !important;
        border-right: none !important;
    }

    [data-testid="stSidebar"] .block-container {
        padding-top: 1.5rem !important;
        padding-bottom: 1.5rem !important;
    }

    /* Header */
    .page-header {
        padding: 3.5rem 0 2.5rem 0;
        border-bottom: 1px solid #28292E;
        margin-bottom: 2.5rem;
        overflow: visible;
    }

    .page-title {
        font-family: 'Outfit', sans-serif;
        font-size: 4.6rem;
        font-weight: 900;
        color: #F4F4F5;
        letter-spacing: -2px;
        margin: 0;
        line-height: 1.1;
    }

    .page-subtitle {
        font-size: 0.9rem;
        color: #71717A;
        margin-top: 0.9rem;
        font-weight: 400;
        max-width: 480px;
    }

    /* Sidebar labels */
    .sidebar-label {
        font-size: 0.70rem;
        font-weight: 600;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: #52525B;
        margin-bottom: 0.4rem;
        margin-top: 0.8rem;
        display: block;
    }

    .sidebar-divider {
        border: none;
        border-top: 1px solid #28292E;
        margin: 0.8rem 0;
    }

    /* Input fields */
    .stTextInput > label, .stSelectbox > label {
        font-size: 0.8rem !important;
        font-weight: 500 !important;
        color: #A1A1AA !important;
        letter-spacing: 0.01em;
    }

    .stTextInput input {
        background-color: #1C1D20 !important;
        border: 1px solid #28292E !important;
        border-radius: 6px !important;
        color: #F4F4F5 !important;
        font-size: 0.95rem !important;
        padding: 0.85rem 1rem !important;
        min-height: 54px !important;
    }

    .stTextInput input:focus {
        border-color: #4B5563 !important;
        box-shadow: 0 0 0 1px #4B5563 !important;
    }

    .stSelectbox > div > div {
        background-color: #1C1D20 !important;
        border: 1px solid #28292E !important;
        border-radius: 6px !important;
        color: #F4F4F5 !important;
    }

    /* Primary button */
    .stButton > button {
        background-color: #F4F4F5;
        color: #111214;
        border: none;
        border-radius: 6px;
        padding: 0.55rem 1.25rem;
        font-size: 0.85rem;
        font-weight: 600;
        letter-spacing: 0.01em;
        transition: background-color 0.15s ease;
        width: auto;
    }

    .stButton > button:hover {
        background-color: #D4D4D8;
    }



    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: transparent;
        border-bottom: 1px solid #28292E;
        gap: 0;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent;
        border: none;
        color: #71717A;
        font-size: 0.85rem;
        font-weight: 500;
        padding: 0.6rem 1rem;
        border-bottom: 2px solid transparent;
        margin-bottom: -1px;
    }

    .stTabs [aria-selected="true"] {
        color: #F4F4F5 !important;
        border-bottom: 2px solid #F4F4F5 !important;
        background: transparent !important;
    }

    /* Override any Streamlit default red/theme accent on tabs */
    [data-baseweb="tab-highlight"],
    [data-baseweb="tab-border"] {
        display: none !important;
        background: transparent !important;
        background-color: transparent !important;
    }

    /* Section headings */
    .section-heading {
        font-family: 'Outfit', sans-serif;
        font-size: 2.2rem;
        font-weight: 800;
        color: #F4F4F5;
        letter-spacing: -1.0px;
        margin-bottom: 0.4rem;
    }

    .section-desc {
        font-size: 0.95rem;
        color: #71717A;
        margin-bottom: 1.5rem;
    }

    /* Tool card */
    .tool-card {
        background: #18191C;
        border: 1px solid #28292E;
        border-radius: 8px;
        padding: 1.5rem;
    }

    /* Alerts */
    .stAlert {
        border-radius: 6px !important;
        font-size: 0.85rem !important;
    }

    /* Success/info */
    .stSuccess {
        background-color: #14532D20 !important;
        border-left-color: #16A34A !important;
    }

    /* Text area - Main Query Input */
    .stTextArea textarea {
        background-color: #1C1D20 !important;
        border: 1px solid #28292E !important;
        border-radius: 6px !important;
        color: #F4F4F5 !important;
        font-size: 1.15rem !important;
        font-family: 'Inter', sans-serif !important;
        line-height: 1.5 !important;
    }

    /* Text area - Transcript Output */
    [data-testid="stColumn"] .stTextArea textarea {
        color: #D4D4D8 !important;
        font-size: 0.85rem !important;
        font-family: 'IBM Plex Mono', 'Courier New', monospace !important;
        line-height: 1.6 !important;
    }

    /* Download button */
    .stDownloadButton > button {
        background-color: #1C1D20;
        color: #A1A1AA;
        border: 1px solid #28292E;
        border-radius: 6px;
        font-size: 0.8rem;
        padding: 0.45rem 1rem;
        transition: all 0.15s ease;
    }

    .stDownloadButton > button:hover {
        background-color: #28292E;
        color: #F4F4F5;
    }

    /* Video element */
    iframe, video {
        border-radius: 8px;
        border: 1px solid #28292E;
    }

    /* Spinner */
    .stSpinner > div {
        border-color: #3F3F46 !important;
        border-top-color: #A1A1AA !important;
    }

    /* Status widget */
    [data-testid="stStatusWidget"] {
        background: #18191C !important;
        border: 1px solid #28292E !important;
        border-radius: 8px !important;
        font-size: 0.85rem !important;
    }

    /* Scrollbar */
    ::-webkit-scrollbar { width: 5px; height: 5px; }
    ::-webkit-scrollbar-track { background: #111214; }
    ::-webkit-scrollbar-thumb { background: #3F3F46; border-radius: 4px; }

    /* Hide Streamlit branding */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)

# --- Resolve keys ---
serpapi_key = os.getenv("SERPAPI_API_KEY", "")
gemini_key = os.getenv("GEMINI_API_KEY", "")
groq_key = os.getenv("GROQ_API_KEY", "")



# --- Sidebar Content ---
st.sidebar.markdown('<span class="sidebar-label">Provider</span>', unsafe_allow_html=True)
provider_option = st.sidebar.selectbox(
    "Provider",
    options=["Gemini", "Groq"],
    index=0,
    label_visibility="collapsed"
)

st.sidebar.markdown('<span class="sidebar-label">Model</span>', unsafe_allow_html=True)
if provider_option == "Gemini":
    model_option = st.sidebar.selectbox(
        "Gemini Model",
        options=["gemini-3.5-flash", "gemini-3.5-flash-lite", "gemini-3.1-flash-lite"],
        index=0,
        label_visibility="collapsed"
    )
else:
    model_option = st.sidebar.selectbox(
        "Groq Model",
        options=["llama-3.3-70b-versatile", "mixtral-8x7b-32768"],
        index=0,
        label_visibility="collapsed"
    )

st.sidebar.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)
st.sidebar.markdown('<span class="sidebar-label">Example Queries</span>', unsafe_allow_html=True)
st.sidebar.markdown(
    """
    <div style="color: #71717A; font-size: 0.80rem; line-height: 1.6;">
        <ul style="padding-left: 1.1rem; margin-top: 0.3rem; margin-bottom: 0;">
            <li style="margin-bottom: 0.3rem;">Python decorators explained</li>
            <li style="margin-bottom: 0.3rem;">Git branching tutorial</li>
            <li style="margin-bottom: 0.3rem;">Reinforcement learning intro</li>
            <li>QuickSort algorithm walkthrough</li>
        </ul>
    </div>
    """,
    unsafe_allow_html=True
)

st.sidebar.markdown('<hr class="sidebar-divider">', unsafe_allow_html=True)
st.sidebar.markdown('<span class="sidebar-label">How it works</span>', unsafe_allow_html=True)
st.sidebar.markdown(
    """
    <div style="color: #71717A; font-size: 0.80rem; line-height: 1.6;">
        <ul style="padding-left: 1.1rem; margin-top: 0.3rem; margin-bottom: 0;">
            <li style="margin-bottom: 0.3rem;"><strong>Search:</strong> Uses SerpAPI to locate a target YouTube video.</li>
            <li style="margin-bottom: 0.3rem;"><strong>Extraction:</strong> Employs yt-dlp to download video audio.</li>
            <li><strong>Transcription:</strong> Transcribes audio with the Gemini Files API.</li>
        </ul>
    </div>
    """,
    unsafe_allow_html=True
)

# --- Page Header ---
st.markdown("""
<div style="padding: 1.0rem 0 0.5rem 0; overflow: visible;">
    <div style="font-family: 'Outfit', sans-serif; font-size: 4.6rem; font-weight: 900; color: #F4F4F5; letter-spacing: -2px; line-height: 1.1; margin: 0; padding-bottom: 15px; display: block;">Video Transcription Agent</div>
</div>
""", unsafe_allow_html=True)

# --- Logo row (full width, clean border below) ---
st.markdown("""
<div style="display:flex; align-items:center; gap: 14px; padding: 0 0 1.8rem 0; border-bottom: 1px solid #28292E; margin-bottom: 2.5rem;">
    <span style="font-size: 0.9rem; color: #52525B; font-weight: 500;">Powered by</span>
    <span style="display:inline-flex;align-items:center;gap:8px;background:#1C1D20;border:1px solid #2E2E34;border-radius:7px;padding:7px 14px;">
        <svg viewBox="0 0 24 24" style="width:20px;height:20px;" xmlns="http://www.w3.org/2000/svg"><path fill="#FF0000" d="M23.5 6.2a3 3 0 0 0-2.1-2.1C19.5 3.5 12 3.5 12 3.5s-7.5 0-9.4.6A3 3 0 0 0 .5 6.2C0 8.1 0 12 0 12s0 3.9.5 5.8a3 3 0 0 0 2.1 2.1c1.9.6 9.4.6 9.4.6s7.5 0 9.4-.6a3 3 0 0 0 2.1-2.1C24 15.9 24 12 24 12s0-3.9-.5-5.8z"/><polygon fill="white" points="9.75,15.5 15.75,12 9.75,8.5"/></svg>
        <span style="color:#D4D4D8;font-size:0.9rem;font-weight:500;">YouTube</span>
    </span>
    <span style="display:inline-flex;align-items:center;gap:8px;background:#1C1D20;border:1px solid #2E2E34;border-radius:7px;padding:7px 14px;">
        <img src="https://www.gstatic.com/lamda/images/gemini_sparkle_v002_d4735304ff6292a690345.svg" style="width:20px;height:20px;" />
        <span style="color:#D4D4D8;font-size:0.9rem;font-weight:500;">Gemini</span>
    </span>
    <span style="display:inline-flex;align-items:center;gap:8px;background:#1C1D20;border:1px solid #2E2E34;border-radius:7px;padding:7px 14px;">
        <img src="https://serpapi.com/favicon.ico" style="width:20px;height:20px;border-radius:3px;" />
        <span style="color:#D4D4D8;font-size:0.9rem;font-weight:500;">SerpAPI</span>
    </span>
</div>
""", unsafe_allow_html=True)

# --- Agent Workflow Section ---
st.markdown('<div class="section-heading">Run a workflow</div>', unsafe_allow_html=True)
st.markdown('<div class="section-desc">Describe a video topic. The agent will search YouTube and produce a transcript.</div>', unsafe_allow_html=True)

# Full-width tall textarea
query_input = st.text_area(
    "Query",
    value="Find a short video explaining python hello world and transcribe it.",
    height=200,
    label_visibility="collapsed"
)

# Simple layout to align button to right corner
_, col_run = st.columns([9.1, 0.9])
with col_run:
    run = st.button("Run Agent", use_container_width=True)

# Extra breathing space below the button
st.markdown('<div style="margin-top: 2.0rem;"></div>', unsafe_allow_html=True)


if run:
    # Resolve necessary key based on provider
    active_key = gemini_key if provider_option == "Gemini" else groq_key
    
    if not serpapi_key or not active_key:
        st.error(f"API keys not found. Please check that SERPAPI_API_KEY and {'GEMINI_API_KEY' if provider_option == 'Gemini' else 'GROQ_API_KEY'} are set in your .env file.")
    else:
        status_container = st.status("Running agent...", expanded=True)
        try:
            found_video_url = None
            saved_transcript_path = None

            # Route execution to proper agent based on provider selection
            if provider_option == "Gemini":
                agent_iterator = agent.run_gemini_agent(query_input, gemini_key, model_option)
            else:
                agent_iterator = agent.run_groq_agent(query_input, groq_key)

            for event in agent_iterator:
                ev_type = event.get("event")
                if ev_type == "status":
                    status_container.write(event["text"])
                elif ev_type == "agent_response":
                    st.markdown(f"**Agent:** {event['text']}")
                elif ev_type == "tool_call":
                    status_container.write(f"Calling `{event['name']}` — {event['args']}")
                    if event["name"] == "transcription_tool":
                        status_container.write("Downloading audio. This may take up to a minute...")
                elif ev_type == "tool_result":
                    status_container.write("Tool executed successfully.")
                elif ev_type == "tool_error":
                    status_container.write(f"Error: {event['error']}")
                elif ev_type == "complete":
                    found_video_url = event.get("video_url")
                    saved_transcript_path = event.get("transcript_path")

            status_container.update(label="Completed.", state="complete")

            if found_video_url or saved_transcript_path:
                st.markdown("---")
                col_left, col_right = st.columns(2)
                with col_left:
                    if found_video_url:
                        st.markdown("**Video**")
                        st.video(found_video_url)
                with col_right:
                    if saved_transcript_path and os.path.exists(saved_transcript_path):
                        st.markdown("**Transcript**")
                        with open(saved_transcript_path, "r", encoding="utf-8") as f:
                            transcript_text = f.read()
                        st.text_area("", value=transcript_text, height=260, label_visibility="collapsed")
                        st.download_button(
                            "Download transcript",
                            data=transcript_text,
                            file_name=os.path.basename(saved_transcript_path),
                            mime="text/plain"
                        )
                    elif found_video_url:
                        st.info("Video found but no transcript was produced.")

        except Exception as e:
            status_container.update(label="Failed.", state="error")
            st.error(str(e))



