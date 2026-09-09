import json
from typing import Optional
import httpx
from config import config
from models.sentiment import SentimentResult
from utils.logger import get_logger

logger = get_logger("llm_sentiment_analyzer")

SYSTEM_PROMPT = """Anda adalah analis riset kuantitatif pasar modal Bursa Efek Indonesia (BEI).
Tugas Anda adalah mengevaluasi teks keterbukaan informasi emiten dan menentukan sentimen dampaknya terhadap harga saham dalam jangka pendek/menengah (swing trading).

Output WAJIB berupa JSON valid dengan skema berikut:
{
  "ticker": "KODE_EMITEN",
  "sentiment_score": 0.85,
  "sentiment_label": "POSITIVE",
  "catalyst_event": "DIVIDEND_ANNOUNCEMENT",
  "summary": "Ringkasan ringkas dalam 1 kalimat Bahasa Indonesia.",
  "risk_flags": []
}

Ketentuan Skor:
- sentiment_score: float dari -1.0 (sangat negatif/risiko tinggi) sampai +1.0 (sangat positif).
- sentiment_label: "POSITIVE" (skor >= 0.2), "NEUTRAL" (-0.2 < skor < 0.2), "NEGATIVE" (skor <= -0.2).
- catalyst_event: Salah satu dari ["FINANCIAL_REPORT", "DIVIDEND_ANNOUNCEMENT", "CORPORATE_ACTION", "LEGAL_RISK", "MATERIAL_DISCLOSURE", "NONE"].
- risk_flags: List string berisi risiko hukum/PKPU/suspensi jika ditemukan.
"""


class LLMSentimentAnalyzer:
    def __init__(self):
        self.provider = config.llm.provider
        self.model = config.llm.model
        self.timeout = float(config.llm.timeout_seconds)
        self.openrouter_key = config.llm.openrouter_api_key
        self.openai_key = config.llm.openai_api_key
        self.anthropic_key = config.llm.anthropic_api_key

    def _parse_json_content(self, content: str) -> Optional[dict]:
        """Extracts JSON object from LLM response text, handling possible markdown code blocks."""
        cleaned = content.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
        elif "```" in cleaned:
            cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]

        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"Failed to parse LLM JSON: {e} | Raw text: {content[:200]}")
            return None

    def _call_openrouter(self, ticker: str, text: str) -> Optional[SentimentResult]:
        """Calls OpenRouter API (OpenAI-compatible) with free tier models."""
        if not self.openrouter_key or self.openrouter_key.startswith("your_"):
            logger.info("OpenRouter API key not configured, using fallback.")
            return None

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/baraja/idx-stock-radar",
            "X-Title": "IDX Stock Radar",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Ticker: {ticker}\nTeks Keterbukaan Informasi:\n{text}\nKembalikan HANYA JSON valid.",
                },
            ],
            "temperature": 0.1,
            "max_tokens": 150,
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                raw_text = resp.json()["choices"][0]["message"]["content"]
                parsed = self._parse_json_content(raw_text)
                if parsed:
                    return SentimentResult(**parsed)
            else:
                logger.error(f"OpenRouter API error {resp.status_code}: {resp.text}")
        return None

    def _call_openai(self, ticker: str, text: str) -> Optional[SentimentResult]:
        """Calls OpenAI Chat Completion API with JSON response format."""
        if not self.openai_key or self.openai_key.startswith("your_"):
            logger.info("OpenAI API key not configured, using fallback.")
            return None

        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Ticker: {ticker}\nTeks Keterbukaan Informasi:\n{text}",
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 150,  # Enforced per  6.2
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                raw_json = resp.json()["choices"][0]["message"]["content"]
                parsed = self._parse_json_content(raw_json)
                if parsed:
                    return SentimentResult(**parsed)
            else:
                logger.error(f"OpenAI API error {resp.status_code}: {resp.text}")
        return None

    def _call_anthropic(self, ticker: str, text: str) -> Optional[SentimentResult]:
        """Calls Anthropic Messages API."""
        if not self.anthropic_key or self.anthropic_key.startswith("your_"):
            logger.info("Anthropic API key not configured, using fallback.")
            return None

        url = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key": self.anthropic_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        prompt = f"Ticker: {ticker}\nTeks Keterbukaan Informasi:\n{text}\nKembalikan HANYA JSON."
        payload = {
            "model": self.model if "claude" in self.model else "claude-3-5-haiku-20241022",
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 150,
            "temperature": 0.1,
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["content"][0]["text"]
                parsed = self._parse_json_content(content)
                if parsed:
                    return SentimentResult(**parsed)
            else:
                logger.error(f"Anthropic API error {resp.status_code}: {resp.text}")
        return None

    def analyze(self, ticker: str, text: Optional[str]) -> SentimentResult:
        """
        Analyzes sentiment of text.
        If text is missing or LLM call fails/times out, returns a neutral fallback.
        """
        clean_ticker = ticker.upper().replace(".JK", "")

        if not text or len(text.strip()) < 10:
            return SentimentResult.neutral_fallback(
                clean_ticker,
                reason="Tidak terdapat pengumuman aksi korporasi material terbaru."
            )

        try:
            if self.provider == "anthropic":
                res = self._call_anthropic(clean_ticker, text)
            elif self.provider == "openrouter":
                res = self._call_openrouter(clean_ticker, text)
            else:
                res = self._call_openai(clean_ticker, text)

            if res is not None:
                return res
        except (httpx.TimeoutException, TimeoutError):
            logger.warning(
                f"LLM API timed out after {self.timeout}s for {clean_ticker}. Activating technical-only fallback ( 6.2)."
            )
        except Exception as e:
            logger.error(f"Unexpected error in sentiment evaluation for {clean_ticker}: {e}")

        # Graceful fallback per  6.2
        return SentimentResult.neutral_fallback(
            clean_ticker,
            reason="Analisis sentimen AI dilewati (fallback teknikal murni aktif)."
        )
