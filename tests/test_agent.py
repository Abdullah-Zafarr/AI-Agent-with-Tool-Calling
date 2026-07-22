import unittest
from unittest.mock import patch, MagicMock
import os
import sys

# Add root directory to path to resolve src modules correctly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import src.agent as main
import src.tools as tools

class TestAIAgent(unittest.TestCase):
    
    @patch('src.agent.genai.Client')
    @patch('src.agent.tools.video_search_tool')
    @patch('src.agent.tools.transcription_tool')
    def test_gemini_agent_flow(self, mock_transcription, mock_search, mock_genai_client):
        # Setup mocks
        mock_search.return_value = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        mock_transcription.return_value = "This is a mock transcription of the video content."
        
        # Mock Gemini Client and its response
        mock_client_instance = MagicMock()
        mock_genai_client.return_value = mock_client_instance
        
        # We simulate a 3-turn response:
        # Turn 1: model wants to search for video
        mock_response_1 = MagicMock()
        mock_call_1 = MagicMock()
        mock_call_1.name = "video_search_tool"
        mock_call_1.args = {"query": "python decorators tutorial"}
        mock_response_1.function_calls = [mock_call_1]
        mock_response_1.text = None
        mock_response_1.candidates = [MagicMock()]
        mock_response_1.candidates[0].content = MagicMock()
        
        # Turn 2: model wants to transcribe
        mock_response_2 = MagicMock()
        mock_call_2 = MagicMock()
        mock_call_2.name = "transcription_tool"
        mock_call_2.args = {"video_url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"}
        mock_response_2.function_calls = [mock_call_2]
        mock_response_2.text = None
        mock_response_2.candidates = [MagicMock()]
        mock_response_2.candidates[0].content = MagicMock()
        
        # Turn 3: model final response
        mock_response_3 = MagicMock()
        mock_response_3.function_calls = None
        mock_response_3.text = "I have successfully searched and transcribed the video. The transcript is stored at transcripts/dQw4w9WgXcQ.txt."
        
        # Configure generate_content side_effect to return each response sequentially
        mock_client_instance.models.generate_content.side_effect = [
            mock_response_1,
            mock_response_2,
            mock_response_3
        ]
        
        # Run agent and exhaust generator
        list(main.run_gemini_agent("Search a video on python decorators and transcribe it.", "fake-api-key"))
        
        # Verify tools were called
        mock_search.assert_called_once_with(query="python decorators tutorial")
        mock_transcription.assert_called_once_with(video_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        
        # Verify generate_content was called 3 times
        self.assertEqual(mock_client_instance.models.generate_content.call_count, 3)

    def test_sanitize_youtube_url_cleans_model_noise(self):
        noisy_url = "[https://www.youtube.com/watch?v=e9lnsKot_SQ'}](https://www.youtube.com/watch?v=e9lnsKot_SQ%27%7D)"

        clean_url = tools.sanitize_youtube_url(noisy_url)

        self.assertEqual(clean_url, "https://www.youtube.com/watch?v=e9lnsKot_SQ")
        self.assertEqual(tools.extract_video_id(noisy_url), "e9lnsKot_SQ")

    @patch.dict(os.environ, {"SERPAPI_API_KEY": "fake-serpapi-key"})
    @patch('src.tools._can_download_audio')
    @patch('src.tools.requests.get')
    def test_video_search_skips_unavailable_results(self, mock_get, mock_can_download):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "video_results": [
                {
                    "title": "DRM video",
                    "link": "https://www.youtube.com/watch?v=e9lnsKot_SQ",
                },
                {
                    "title": "Downloadable video",
                    "link": "https://www.youtube.com/watch?v=2ReR1YJrNOM",
                },
            ]
        }
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response
        mock_can_download.side_effect = [
            (False, "This video is DRM protected"),
            (True, ""),
        ]

        result = tools.video_search_tool("git commit short explanation")

        self.assertEqual(result, "https://www.youtube.com/watch?v=2ReR1YJrNOM")
        self.assertEqual(mock_can_download.call_count, 2)

if __name__ == '__main__':
    unittest.main()
