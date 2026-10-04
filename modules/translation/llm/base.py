from typing import Any
import json
import logging
import re
import threading
import time
from collections import deque
import numpy as np
from abc import abstractmethod
import base64
import imkit as imk

from ..base import LLMTranslation
from ...utils.textblock import TextBlock
from ...utils.translator_utils import get_raw_text, set_texts_from_json, has_translatable_content

logger = logging.getLogger(__name__)

# Sliding-window client-side rate limit shared by all LLM engines.
# Free-tier Gemini allows 15 RPM; pace under it to avoid 429s during batches.
MAX_REQUESTS_PER_MINUTE = 13
_RETRYABLE_STATUS_HINTS = ("429", "500", "502", "503", "resource_exhausted", "overloaded")

# Account-level problems that retrying cannot fix; fail fast instead of
# burning backoff time. Matched case-insensitively against the error text.
_NON_RETRYABLE_HINTS = (
    "insufficient balance", "insufficient_quota", "insufficient quota",
    "insufficient credits", "exceeded your current quota", "billing",
    "account is deactivated", "account has been suspended", "account suspended",
    "欠费", "余额不足", "已被封禁",
    # Zhipu/BigModel business codes: 1113 arrears, 1308/1309/1310 plan limits
    '"code": "1113"', '"code": "1308"', '"code": "1309"', '"code": "1310"',
    '"code":"1113"', '"code":"1308"', '"code":"1309"', '"code":"1310"',
)

# Provider slowness (e.g. an overloaded model queueing the request): one retry
# is worth it, but each attempt costs a full request timeout, so no more.
_TIMEOUT_HINTS = ("timed out", "timeout")

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
        """Throttled _perform_translation with backoff on retryable API failures.

        Retries rate-limit/overload/server errors; request timeouts get a single
        retry; account-level problems (billing, quotas, bans) fail immediately.
        """
        for attempt in range(max_retries + 1):
            _throttle()
            try:
                return self._perform_translation(user_prompt, system_prompt, image)
            except Exception as e:
                message = str(e).lower()
                if any(hint in message for hint in _NON_RETRYABLE_HINTS):
                    logger.warning("LLM request failed with a non-retryable account error: %s",
                                   str(e)[:200])
                    raise
                if any(hint in message for hint in _TIMEOUT_HINTS):
                    retryable = attempt < 1
                else:
                    retryable = (attempt < max_retries
                                 and any(hint in message for hint in _RETRYABLE_STATUS_HINTS))
                if not retryable:
                    raise
                wait = 20 * (2 ** attempt)
                logger.warning("LLM request failed (attempt %d/%d), retrying in %ds: %s",
                               attempt + 1, max_retries + 1, wait, str(e)[:200])
                time.sleep(wait)

    def translate_pages(self, blk_lists: list[list[TextBlock]], extra_context: str = "") -> tuple[set[int], set[int]]:
        """Translate several pages in ONE LLM request.

        Blocks are re-keyed globally (p<page>b<block>) so the JSON response maps
        back unambiguously; a dropped key only leaves that single block
        untranslated instead of shifting the rest. Pages whose keys are not all
        present in the response are reported as failed so the caller can
        re-translate them per page.

        Returns:
            (ok_page_indices, failed_page_indices) — translations are already
            assigned to the blocks of ok pages. Non-translatable blocks get
            translation="" like Translator.translate does.
        """
        page_keys: list[list[tuple[str, TextBlock]]] = []
        flat_texts: dict[str, str] = {}
        for pi, blk_list in enumerate(blk_lists):
            keys: list[tuple[str, TextBlock]] = []
            for bi, blk in enumerate(blk_list):
                key = f"p{pi}b{bi}"
                if has_translatable_content(getattr(blk, "text", "")):
                    keys.append((key, blk))
                    flat_texts[key] = blk.text
                else:
                    blk.translation = ""
            page_keys.append(keys)

        # pages with no translatable blocks are already done (blocks set to "")
        ok_pages: set[int] = set(pi for pi, keys in enumerate(page_keys) if not keys)
        failed_pages: set[int] = set()
        if not flat_texts:
            return ok_pages, failed_pages

        system_prompt = self.get_system_prompt(self.source_lang, self.target_lang) + (
            "\nYou are given MULTIPLE comic pages at once. Every key has the form p<page>b<block> "
            "where <page> is a page number and <block> is a block index on that page. "
            "Use the surrounding pages as context for each other. "
            "Return ONE json object with EXACTLY the same keys as the input and the translated "
            "text as values. DO NOT translate, add, merge or drop any keys."
        )
        user_prompt = (f"{extra_context}\nMake the translation sound as natural as possible.\n"
                       f"Translate this:\n{json.dumps(flat_texts, ensure_ascii=False, indent=4)}")

        old_max_tokens = self.max_tokens
        self.max_tokens = min(16000, max(5000, 400 + 60 * len(flat_texts)))
        try:
            response = self._perform_translation_with_retry(user_prompt, system_prompt, None)
        finally:
            self.max_tokens = old_max_tokens

        response_text = response if isinstance(response, str) else ""
        match = re.search(r"\{[\s\S]*\}", response_text)
        if not match:
            logger.warning("Batch translation: no JSON object in response, %d page(s) need fallback; "
                           "response preview: %r",
                           len(blk_lists), response_text[:200])
            return ok_pages, set(range(len(blk_lists)))
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError as e:
            logger.warning("Batch translation: invalid JSON (%s), %d page(s) need fallback", e, len(blk_lists))
            return ok_pages, set(range(len(blk_lists)))

        for pi, keys in enumerate(page_keys):
            if not keys:
                continue
            missing = [key for key, _ in keys if key not in data]
            if not missing and not any(str(data[key] or "").strip() for key, _ in keys):
                # All keys answered with empty text: treat as a failed page so it
                # is retried per page instead of silently rendering nothing.
                missing = [key for key, _ in keys]
            if missing:
                logger.warning("Batch translation: page %d missing %d/%d keys, needs per-page fallback",
                               pi, len(missing), len(keys))
                failed_pages.add(pi)
                continue
            for key, blk in keys:
                blk.translation = data[key]
            ok_pages.add(pi)
        return ok_pages, failed_pages
    
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
