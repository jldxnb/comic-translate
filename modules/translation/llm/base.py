from typing import Any
import logging
import threading
import time
from collections import deque
import numpy as np
from abc import abstractmethod
import base64
import imkit as imk

from ..base import LLMTranslation
from ...utils.textblock import TextBlock
from ...utils.translator_utils import get_raw_text, set_texts_from_json

logger = logging.getLogger(__name__)

# Sliding-window client-side rate limit shared by all LLM engines.
# Free-tier Gemini allows 15 RPM; pace under it to avoid 429s during batches.
MAX_REQUESTS_PER_MINUTE = 13
_RETRYABLE_STATUS_HINTS = ("429", "500", "502", "503", "resource_exhausted", "overloaded")

_RPM_LOCK = threading.Lock()
_REQUEST_TIMES: deque = deque()


def _throttle() -> None:
    """Block until a request slot is available in the current 60s window."""
    while True:
        with _RPM_LOCK:
            now = time.monotonic()
            while _REQUEST_TIMES and now - _REQUEST_TIMES[0] >= 60.0:
                _REQUEST_TIMES.popleft()
            if len(_REQUEST_TIMES) < MAX_REQUESTS_PER_MINUTE:
                _REQUEST_TIMES.append(time.monotonic())
                return
            wait = 60.0 - (now - _REQUEST_TIMES[0]) + 0.25
        logger.info("Rate limit pacing: waiting %.1fs before next LLM request", wait)
        time.sleep(max(wait, 0.25))


class BaseLLMTranslation(LLMTranslation):
    """Base class for LLM-based translation engines with shared functionality."""
    
    def __init__(self):
        self.source_lang = None
        self.target_lang = None
        self.api_key = None
        self.api_url = None
        self.model = None
        self.img_as_llm_input = False
        self.temperature = None
        self.max_tokens = None
        self.timeout = 30  
    
    def initialize(self, settings: Any, source_lang: str, target_lang: str, **kwargs) -> None:
        """
        Initialize the LLM translation engine.
        
        Args:
            settings: Settings object with credentials
            source_lang: Source language name
            target_lang: Target language name
            **kwargs: Engine-specific initialization parameters
        """
        llm_settings = settings.get_llm_settings()
        self.source_lang = source_lang
        self.target_lang = target_lang
        self.img_as_llm_input = llm_settings.get('image_input_enabled', True)
        self.temperature = 1.0
        self.max_tokens = 5000
        
    def translate(self, blk_list: list[TextBlock], image: np.ndarray, extra_context: str) -> list[TextBlock]:
        """
        Translate text blocks using LLM.
        
        Args:
            blk_list: List of TextBlock objects to translate
            image: Image as numpy array
            extra_context: Additional context information for translation
            
        Returns:
            List of updated TextBlock objects with translations
        """
        entire_raw_text = get_raw_text(blk_list)
        system_prompt = self.get_system_prompt(self.source_lang, self.target_lang)
        user_prompt = f"{extra_context}\nMake the translation sound as natural as possible.\nTranslate this:\n{entire_raw_text}"

        entire_translated_text = self._perform_translation_with_retry(user_prompt, system_prompt, image)
        set_texts_from_json(blk_list, entire_translated_text)

        return blk_list

    def _perform_translation_with_retry(self, user_prompt: str, system_prompt: str, image: np.ndarray,
                                        max_retries: int = 3) -> str:
        """Throttled _perform_translation with backoff on retryable API failures (429/5xx)."""
        for attempt in range(max_retries + 1):
            _throttle()
            try:
                return self._perform_translation(user_prompt, system_prompt, image)
            except Exception as e:
                message = str(e).lower()
                retryable = any(hint in message for hint in _RETRYABLE_STATUS_HINTS)
                if not retryable or attempt >= max_retries:
                    raise
                wait = 20 * (2 ** attempt)
                logger.warning("LLM request failed (attempt %d/%d), retrying in %ds: %s",
                               attempt + 1, max_retries + 1, wait, str(e)[:200])
                time.sleep(wait)
    
    @abstractmethod
    def _perform_translation(self, user_prompt: str, system_prompt: str, image: np.ndarray) -> str:
        """
        Perform translation using specific LLM.
        
        Args:
            user_prompt: User prompt for LLM
            system_prompt: System prompt for LLM
            image: Image as numpy array
            
        Returns:
            Translated JSON text
        """
        pass

    def encode_image(self, image: np.ndarray, ext=".jpg"):
        """
        Encode CV2/numpy image directly to base64 string using cv2.imencode.
        
        Args:
            image: Numpy array representing the image
            ext: Extension/format to encode the image as (".png" by default for higher quality)
                
        Returns:
            Tuple of (Base64 encoded string, mime_type)
        """
        # Direct encoding from numpy/cv2 format to bytes
        buffer = imk.encode_image(image, ext.lstrip('.'))
        
        # Convert to base64
        img_str = base64.b64encode(buffer).decode('utf-8')
        
        # Map extension to mime type
        mime_types = {
            ".jpg": "image/jpeg", 
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp"
        }
        mime_type = mime_types.get(ext.lower(), f"image/{ext[1:].lower()}")
        
        return img_str, mime_type
