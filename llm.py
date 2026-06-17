"""LLM client with support for text chat and VLM (vision) chat."""
import logging
import time
import json
import re
import base64
from openai import OpenAI, AsyncOpenAI
from config import Settings
import event_log

log = logging.getLogger(__name__)

_JSON_SUFFIX = '\n\nYou MUST respond with valid JSON only. No markdown, no explanation, just JSON.'

class LLMClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        kwargs = dict(
            base_url=settings.llm_base_url,
            api_key=settings.llm_api_key,
            timeout=1200.0,
            max_retries=0,
        )
        self.client = AsyncOpenAI(**kwargs)

    async def achat(self, system: str, user: str, model: str | None = None,
                    temperature: float | None = None, max_tokens: int | None = None) -> str:
        """Standard text chat completion."""
        m = model or self.settings.llm_model
        t = temperature if temperature is not None else self.settings.temperature
        mt = max_tokens or self.settings.max_tokens

        start = time.time()
        err = None
        try:
            resp = await self.client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=t,
                max_tokens=mt,
            )
            text = resp.choices[0].message.content or ""
            return text
        except Exception as e:
            err = e
            log.error("LLM call failed (%s): %s", m, e, exc_info=True)
            raise
        finally:
            event_log.log_event("llm_call", {
                "model": m, "elapsed_ms": int((time.time()-start)*1000),
                "error": str(err) if err else None,
            })

    async def achat_json(self, system: str, user: str, retries: int = 1,
                         model: str | None = None, **kwargs) -> dict:
        """Chat with JSON parsing and retry on failure."""
        sys_text = system + _JSON_SUFFIX
        for attempt in range(retries + 1):
            raw = await self.achat(sys_text, user, model=model, **kwargs)
            parsed = _try_parse_json(raw)
            if parsed is not None:
                return parsed
            log.warning("JSON parse failed (attempt %d/%d): %s...",
                        attempt+1, retries+1, raw[:200])
            user = "Your previous response was not valid JSON. Respond with ONLY a JSON object.\n\n" + user
        log.error("JSON parse failed after %d retries", retries+1)
        return {"error": "LLM did not return valid JSON", "raw": raw[:500]}

    async def avision(self, system: str, image_url: str, user_text: str,
                      model: str | None = None) -> str:
        """Vision/chat with an image URL and text prompt."""
        m = model or self.settings.vlm_model
        start = time.time()
        err = None
        try:
            resp = await self.client.chat.completions.create(
                model=m,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ]},
                ],
                max_tokens=2048,
            )
            return resp.choices[0].message.content or ""
        except Exception as e:
            err = e
            log.error("VLM call failed (%s): %s", m, e, exc_info=True)
            raise
        finally:
            event_log.log_event("vlm_call", {
                "model": m, "image_url": image_url[:120],
                "elapsed_ms": int((time.time()-start)*1000),
                "error": str(err) if err else None,
            })

    async def avision_json(self, system: str, image_url: str, user_text: str,
                           retries: int = 1, model: str | None = None) -> dict:
        """Vision chat with JSON parsing and retry on failure."""
        sys_text = system + _JSON_SUFFIX
        for attempt in range(retries + 1):
            raw = await self.avision(sys_text, image_url, user_text, model=model)
            parsed = _try_parse_json(raw)
            if parsed is not None:
                return parsed
            log.warning("VLM JSON parse failed (attempt %d/%d): %s...",
                        attempt+1, retries+1, raw[:200])
            user_text = "Your previous response was not valid JSON. Respond with ONLY a JSON object.\n\n" + user_text
        log.error("VLM JSON parse failed after %d retries", retries+1)
        return {"error": "VLM did not return valid JSON", "raw": raw[:500]}


def _try_parse_json(text: str) -> dict | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass
    return None
