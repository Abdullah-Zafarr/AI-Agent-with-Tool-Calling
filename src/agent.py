import os
import sys
import json
import argparse
import logging
from dotenv import load_dotenv
from google import genai
from google.genai import types
from groq import Groq

import src.tools as tools

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def get_tool_function(name: str):
    """
    Dynamically resolve tools from the tools module.
    Crucial for unit testing to allow mocking.
    """
    import src.tools as tools
    if name == "video_search_tool":
        return tools.video_search_tool
    elif name == "transcription_tool":
        return tools.transcription_tool
    return None


def run_gemini_agent(user_query: str, api_key: str, preferred_model: str = "gemini-3.1-flash-lite"):
    """
    Runs the agent loop using Gemini's native tool calling framework.
    Yields structured dictionary events for UI / CLI logs streaming.
    """
    yield {"event": "status", "text": "Initializing Gemini Agent..."}
    client = genai.Client(api_key=api_key)
    
    # Register functions directly as tools
    gemini_tools = [tools.video_search_tool, tools.transcription_tool]
    
    # Initialize session history
    history = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_query)]
        )
    ]
    
    # Arrange candidates so preferred is tried first
    model_candidates = [preferred_model]
    for m in ["gemini-3.1-flash-lite", "gemini-2.5-flash", "gemini-2.5-pro"]:
        if m not in model_candidates:
            model_candidates.append(m)
            
    max_turns = 5
    found_video_url = None
    saved_transcript_path = None
    
    for turn in range(max_turns):
        yield {"event": "status", "text": f"Gemini Agent Turn {turn + 1}: Querying LLM..."}
        
        response = None
        last_error = None
        for model_name in model_candidates:
            try:
                yield {"event": "status", "text": f"Trying Gemini model {model_name}..."}
                response = client.models.generate_content(
                    model=model_name,
                    contents=history,
                    config=types.GenerateContentConfig(
                        system_instruction=(
                            "You are a professional Video Search & Transcription Agent. Your goal is to help users find and transcribe videos.\n"
                            "When you successfully retrieve a video link and its transcript:\n"
                            "1. You MUST include the exact YouTube video URL (as a hyperlink) and the video's title in your response.\n"
                            "2. Crucially: You MUST output the complete, verbatim, word-for-word transcription text returned by the transcription_tool.\n"
                            "3. Do NOT summarize reference text, do NOT shorten or truncate it, and do NOT clean up or alter the transcript. Output it exactly as returned by the tool."
                        ),
                        tools=gemini_tools,
                        temperature=0.0,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(
                            disable=True
                        )
                    )
                )
                break
            except Exception as e:
                logger.warning(f"Model {model_name} failed in agent loop: {e}")
                last_error = e
                
        if response is None:
            raise RuntimeError(f"All agent model candidates failed. Last error: {last_error}")
        
        # Output text response if available
        has_text = False
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            has_text = any(hasattr(p, 'text') and p.text for p in response.candidates[0].content.parts)
        if has_text and response.text:
            yield {"event": "agent_response", "text": response.text}
            
        function_calls = response.function_calls
        if not function_calls:
            yield {"event": "status", "text": "No further tool calls requested. Finished."}
            break
            
        # Record the model's response to the history before processing tool responses
        history.append(response.candidates[0].content)
        
        tool_response_parts = []
        for call in function_calls:
            func_name = call.name
            func_args = call.args if call.args else {}
            yield {"event": "tool_call", "name": func_name, "args": func_args}
            
            tool_func = get_tool_function(func_name)
            if tool_func:
                try:
                    result = tool_func(**func_args)
                    
                    if func_name == "video_search_tool":
                        found_video_url = result
                    elif func_name == "transcription_tool":
                        video_id = tools.extract_video_id(func_args["video_url"])
                        saved_transcript_path = os.path.join("transcripts", f"{video_id}.txt")
                        
                    yield {"event": "tool_result", "name": func_name, "args": func_args, "result": result}
                    
                    part = types.Part.from_function_response(
                        name=func_name,
                        response={"result": result}
                    )
                except Exception as e:
                    yield {"event": "tool_error", "name": func_name, "args": func_args, "error": str(e)}
                    part = types.Part.from_function_response(
                        name=func_name,
                        response={"error": str(e)}
                    )
            else:
                yield {"event": "tool_error", "name": func_name, "args": func_args, "error": f"Tool '{func_name}' not registered."}
                part = types.Part.from_function_response(
                    name=func_name,
                    response={"error": f"Tool '{func_name}' is not registered."}
                )
                
            tool_response_parts.append(part)
            
        # Append the tool's output back to history
        history.append(
            types.Content(
                role="tool",
                parts=tool_response_parts
            )
        )
    else:
        yield {"event": "status", "text": "Agent reached max execution turns without self-termination."}

    # If transcription_tool wasn't called successfully in this session but a prior run
    # already wrote the transcript to disk, surface it.
    if found_video_url and not saved_transcript_path:
        try:
            video_id = tools.extract_video_id(found_video_url)
            candidate = os.path.join("transcripts", f"{video_id}.txt")
            if os.path.exists(candidate):
                saved_transcript_path = candidate
                logger.info(f"Surfacing cached transcript from disk: {candidate}")
        except Exception:
            pass

    yield {
        "event": "complete",
        "video_url": found_video_url,
        "transcript_path": saved_transcript_path
    }


def run_groq_agent(user_query: str, api_key: str):
    """
    Runs the agent loop using Groq's tool calling framework.
    Yields structured dictionary events for UI / CLI logs streaming.
    """
    yield {"event": "status", "text": "Initializing Groq Agent..."}
    client = Groq(api_key=api_key)
    
    groq_tools = [
        {
            "type": "function",
            "function": {
                "name": "video_search_tool",
                "description": "Calls SerpApi to search for a video on YouTube and returns its URL.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query, e.g., 'python decorator tutorial'"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "transcription_tool",
                "description": (
                    "Downloads the audio from a YouTube video URL, "
                    "uses Gemini to transcribe the audio, stores it in a file, and returns the path."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "video_url": {
                            "type": "string",
                            "description": "The YouTube video URL to retrieve and transcribe."
                        }
                    },
                    "required": ["video_url"]
                }
            }
        }
    ]
    
    messages = [
        {
            "role": "system",
            "content": (
                "You are a professional Video Search & Transcription Agent. Your goal is to help users find and transcribe videos.\n"
                "When you successfully retrieve a video link and its transcript:\n"
                "1. You MUST include the exact YouTube video URL (as a hyperlink) and the video's title in your response.\n"
                "2. Crucially: You MUST output the complete, verbatim, word-for-word transcription text returned by the transcription_tool.\n"
                "3. Do NOT summarize reference text, do NOT shorten or truncate it, and do NOT clean up or alter the transcript. Output it exactly as returned by the tool."
            )
        },
        {"role": "user", "content": user_query}
    ]
    
    max_turns = 5
    found_video_url = None
    saved_transcript_path = None
    
    for turn in range(max_turns):
        yield {"event": "status", "text": f"Groq Agent Turn {turn + 1}: Querying LLM..."}
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=messages,
            tools=groq_tools,
            temperature=0.0
        )
        
        msg = response.choices[0].message
        messages.append(msg)
        
        if msg.content:
            yield {"event": "agent_response", "text": msg.content}
            
        if not msg.tool_calls:
            yield {"event": "status", "text": "No further tool calls requested. Finished."}
            break
            
        for tool_call in msg.tool_calls:
            func_name = tool_call.function.name
            func_args = json.loads(tool_call.function.arguments) if tool_call.function.arguments else {}
            yield {"event": "tool_call", "name": func_name, "args": func_args}
            
            tool_func = get_tool_function(func_name)
            if tool_func:
                try:
                    result = tool_func(**func_args)
                    
                    if func_name == "video_search_tool":
                        found_video_url = result
                    elif func_name == "transcription_tool":
                        video_id = tools.extract_video_id(func_args["video_url"])
                        saved_transcript_path = os.path.join("transcripts", f"{video_id}.txt")
                        
                    yield {"event": "tool_result", "name": func_name, "args": func_args, "result": result}
                    result_str = json.dumps({"result": result})
                except Exception as e:
                    yield {"event": "tool_error", "name": func_name, "args": func_args, "error": str(e)}
                    result_str = json.dumps({"error": str(e)})
            else:
                yield {"event": "tool_error", "name": func_name, "args": func_args, "error": f"Tool '{func_name}' is not registered."}
                result_str = json.dumps({"error": f"Tool '{func_name}' not registered."})
                
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "name": func_name,
                "content": result_str
            })
    else:
        yield {"event": "status", "text": "Agent reached max execution turns without self-termination."}
        
    yield {
        "event": "complete",
        "video_url": found_video_url,
        "transcript_path": saved_transcript_path
    }


def main():
    # Load environment variables
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="AI Agent with Video Search + Transcription Tools")
    parser.add_argument(
        "query", 
        type=str, 
        nargs="?",
        default="Search for a video about 'git branches explanation' and transcribe it.",
        help="The instruction/query for the AI agent."
    )
    parser.add_argument(
        "--provider",
        type=str,
        choices=["gemini", "groq", "auto"],
        default="auto",
        help="Select the AI agent backend provider (gemini, groq, or auto)."
    )
    args = parser.parse_args()
    
    gemini_key = os.getenv("GEMINI_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    
    # Auto-resolve provider based on available keys
    provider = args.provider
    if provider == "auto":
        if gemini_key:
            provider = "gemini"
        elif groq_key:
            provider = "groq"
        else:
            print("Error: Neither GEMINI_API_KEY nor GROQ_API_KEY could be found in your environment.")
            print("Please define them in your .env file or export them in your terminal session.")
            sys.exit(1)
            
    print(f"=== Starting Multi-Tool Agent (Provider: {provider.upper()}) ===")
    
    generator = None
    if provider == "gemini":
        if not gemini_key:
            print("Error: Selected Gemini provider, but GEMINI_API_KEY is not set.")
            sys.exit(1)
        generator = run_gemini_agent(args.query, gemini_key)
    elif provider == "groq":
        if not groq_key:
            print("Error: Selected Groq provider, but GROQ_API_KEY is not set.")
            sys.exit(1)
        if not gemini_key:
            print("Warning: Groq agent started, but GEMINI_API_KEY is missing. Transcription tool will fail.")
        generator = run_groq_agent(args.query, groq_key)
        
    if generator:
        for event in generator:
            ev_type = event.get("event")
            if ev_type == "status":
                logger.info(event["text"])
            elif ev_type == "agent_response":
                print(f"\n[Agent Response]: {event['text']}")
            elif ev_type == "tool_call":
                logger.info(f"-> Agent requested tool: {event['name']} with arguments: {event['args']}")
            elif ev_type == "tool_result":
                logger.info(f"-> Tool Output successfully retrieved.")
            elif ev_type == "tool_error":
                logger.error(f"-> Tool execution failed: {event['error']}")
            elif ev_type == "complete":
                logger.info("Agent process completed.")


if __name__ == "__main__":
    main()
