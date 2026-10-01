import json
import time
from typing import Dict, Optional, Tuple
import httpx
from config import config
from models.sentiment import SentimentResult
from utils.logger import get_logger

logger = get_logger("llm_sentiment_analyzer")

# Core materiality dictionaries for pre-filtering to save LLM quota
MATERIAL_KEYWORDS = {
    "dividen", "dividend", "laba", "rugi", "pendapatan", "revenue",
    "akuisisi", "acquisition", "merger", "tender offer", "rights issue",
    "right issue", "private placement", "hmetd", "buyback",
    "pembelian kembali", "investasi", "kontrak baru", "kontrak kerja",
    "suspensi", "suspension", "pkpu", "pailit", "kepailitan", "default",
    "gagal bayar", "restrukturisasi", "divestasi", "pengambilalihan",
    "pergantian pengendali", "rupslb", "kinerja keuangan", "laporan keuangan",
    "penjualan aset", "prospektus", "obligasi", "sukuk"
}

ROUTINE_ADMIN_PHRASES = [
    "laporan bulanan registrasi",
    "registrasi pemegang efek",
    "bukti iklan pemberitahuan",
    "pemberitahuan rups tahunan",
    "jadwal public expose tahunan",
    "penyelenggaraan public expose tahunan",
    "perubahan alamat kantor",
    "perubahan alamat korespondensi",
    "libur bursa",
    "perubahan sekretaris perusahaan",
    "jadwal paparan publik tahunan",
]

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
        self.gemini_key = config.llm.gemini_api_key
        self.openrouter_key = config.llm.openrouter_api_key
        self.openai_key = config.llm.openai_api_key
        self.anthropic_key = config.llm.anthropic_api_key
        self._cooldowns: Dict[str, float] = {}
        self._last_call_time: float = 0.0

    @staticmethod
    def is_material_disclosure(text: str) -> Tuple[bool, str]:
        """
        Determines if disclosure text warrants LLM analysis.
        Filters out boilerplate administrative notifications, saving 60-80% of LLM quota.
        """
        if not text or len(text.strip()) < 15:
            return False, "Tidak terdapat pengumuman aksi korporasi material terbaru."

        lower_text = text.lower()

        # Check boilerplate admin phrases
        for phrase in ROUTINE_ADMIN_PHRASES:
            if phrase in lower_text:
                # If it's routine admin, check if it ALSO has major catalyst (e.g. RUPSLB for merger/dividend)
                if not any(k in lower_text for k in ("merger", "akuisisi", "tender offer", "rights issue", "dividen", "laba")):
                    return False, f"Pengumuman administratif rutin ({phrase}), analisis LLM dilewati."

        # Check material keyword existence
        has_material = any(keyword in lower_text for keyword in MATERIAL_KEYWORDS)
        if not has_material:
            return False, "Keterbukaan informasi tanpa katalis harga material, analisis LLM dilewati."

        return True, "Keterbukaan informasi terdeteksi material."

    def _is_provider_in_cooldown(self, provider: str) -> bool:
        until = self._cooldowns.get(provider, 0.0)
        return time.time() < until

    def _set_provider_cooldown(self, provider: str, duration_seconds: float = 1800.0):
        self._cooldowns[provider] = time.time() + duration_seconds
        logger.warning(
            f"Provider '{provider}' placed in cooldown for {int(duration_seconds)}s due to quota/rate limit. "
            f"Secondary providers will be prioritized."
        )

    def _pace_call(self):
        """Enforces minimum delay between calls based on RPM limit."""
        rpm = max(1, config.llm.llm_rpm_limit)
        min_interval = 60.0 / rpm
        elapsed = time.time() - self._last_call_time
        if elapsed < min_interval:
            sleep_time = min_interval - elapsed
            time.sleep(sleep_time)
        self._last_call_time = time.time()

    def _parse_json_content(self, content: str) -> Optional[dict]:
        """Extracts JSON object from LLM response text, handling markdown code blocks and preambles."""
        if not content:
            return None
        cleaned = content.strip()
        if "```json" in cleaned:
            parts = cleaned.split("```json", 1)[1]
            cleaned = parts.split("```", 1)[0].strip()
        elif "```" in cleaned:
            parts = cleaned.split("```", 1)[1]
            cleaned = parts.split("```", 1)[0].strip()

        start_idx = cleaned.find("{")
        end_idx = cleaned.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
            cleaned = cleaned[start_idx : end_idx + 1]
        else:
            return None

        try:
            return json.loads(cleaned)
        except Exception as e:
            logger.warning(f"Failed to parse LLM JSON: {e} | Raw text: {content[:200]}")
            return None

    def _call_gemini(self, ticker: str, text: str) -> Optional[SentimentResult]:
        """Calls Google Gemini API via google-generativeai SDK with defensive part extraction."""
        if not self.gemini_key or self.gemini_key.startswith("your_"):
            logger.info("Gemini API key not configured, using fallback.")
            return None

        try:
            import google.generativeai as genai  # type: ignore
        except ImportError:
            logger.error("google-generativeai not installed. Run: pip install google-generativeai>=0.8.0")
            return None

        try:
            genai.configure(api_key=self.gemini_key)
            model_name = self.model if self.model.startswith("gemini") else "gemini-2.0-flash"
            gemini_model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_PROMPT,
                generation_config=genai.GenerationConfig(
                    response_mime_type="application/json",
                    temperature=0.1,
                    max_output_tokens=300,
                ),
            )

            user_prompt = (
                f"Ticker: {ticker}\n"
                f"Teks Keterbukaan Informasi:\n{text}\n"
                f"Kembalikan HANYA JSON valid."
            )

            response = gemini_model.generate_content(
                user_prompt,
                request_options={"timeout": int(self.timeout)},
            )

            # Defensive extraction: handle candidates finish_reason or blocked parts
            raw_text = None
            if hasattr(response, "candidates") and response.candidates:
                candidate = response.candidates[0]
                # finish_reason != 1 indicates STOP was not reached (e.g. 2 = SAFETY, 3 = RECITATION)
                if hasattr(candidate, "finish_reason") and candidate.finish_reason not in (1, None):
                    logger.warning(
                        f"Gemini generation flagged/stopped for {ticker} (finish_reason: {candidate.finish_reason})"
                    )
                    return None
                if hasattr(candidate, "content") and hasattr(candidate.content, "parts") and candidate.content.parts:
                    raw_text = "".join(
                        getattr(p, "text", "") for p in candidate.content.parts if hasattr(p, "text")
                    )

            if not raw_text:
                try:
                    raw_text = response.text
                except Exception:
                    pass

            if not raw_text:
                logger.warning(f"Gemini returned empty or blocked response parts for {ticker}")
                return None

            parsed = self._parse_json_content(raw_text)
            if parsed:
                return SentimentResult(**parsed)
            else:
                logger.warning(f"Gemini returned unparseable JSON for {ticker}: {raw_text[:200]}")

        except Exception as e:
            err_str = str(e)
            if "quota" in err_str.lower() or "429" in err_str:
                logger.warning(f"Gemini rate limit hit for {ticker}: {e}")
                self._set_provider_cooldown("gemini", duration_seconds=1800.0)
            elif "invalid api key" in err_str.lower() or "403" in err_str:
                logger.error(f"Gemini API key invalid or unauthorized: {e}")
                self._set_provider_cooldown("gemini", duration_seconds=86400.0)
            else:
                logger.error(f"Gemini API error for {ticker}: {e}")

        return None

    def _call_openrouter(self, ticker: str, text: str) -> Optional[SentimentResult]:
        """Calls OpenRouter API (OpenAI-compatible) — kept as fallback provider."""
        if not self.openrouter_key or self.openrouter_key.startswith("your_"):
            logger.info("OpenRouter API key not configured, using fallback.")
            return None

        # If primary model is Gemini, route OpenRouter to configured openrouter_model (e.g. DeepSeek/Qwen)
        model = self.model
        if "gemini" in model.lower() and not model.startswith("google/"):
            model = config.llm.openrouter_model or "deepseek/deepseek-chat"

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.openrouter_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/baraja/idx-stock-radar",
            "X-Title": "IDX Stock Radar",
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Ticker: {ticker}\nTeks Keterbukaan Informasi:\n{text}\nKembalikan HANYA JSON valid.",
                },
            ],
            "temperature": 0.1,
            "max_tokens": 300,
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                choices = data.get("choices", [])
                if choices and len(choices) > 0:
                    raw_text = choices[0].get("message", {}).get("content", "")
                    parsed = self._parse_json_content(raw_text)
                    if parsed:
                        return SentimentResult(**parsed)
                else:
                    logger.warning(f"OpenRouter response missing choices: {data}")
            elif resp.status_code == 404:
                logger.warning(f"OpenRouter model unavailable (404) for {ticker}. Model: {model}")
            elif resp.status_code == 429:
                logger.warning(f"OpenRouter rate limit (429) for {ticker}. Placing in cooldown.")
                self._set_provider_cooldown("openrouter", duration_seconds=600.0)
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
            "model": self.model if not self.model.startswith("gemini") else "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": f"Ticker: {ticker}\nTeks Keterbukaan Informasi:\n{text}",
                },
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
            "max_tokens": 300,
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                raw_json = resp.json()["choices"][0]["message"]["content"]
                parsed = self._parse_json_content(raw_json)
                if parsed:
                    return SentimentResult(**parsed)
            elif resp.status_code == 429:
                logger.warning(f"OpenAI rate limit (429) for {ticker}. Placing in cooldown.")
                self._set_provider_cooldown("openai", duration_seconds=600.0)
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
            "max_tokens": 300,
            "temperature": 0.1,
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200:
                content = resp.json()["content"][0]["text"]
                parsed = self._parse_json_content(content)
                if parsed:
                    return SentimentResult(**parsed)
            elif resp.status_code == 429:
                logger.warning(f"Anthropic rate limit (429) for {ticker}. Placing in cooldown.")
                self._set_provider_cooldown("anthropic", duration_seconds=600.0)
            else:
                logger.error(f"Anthropic API error {resp.status_code}: {resp.text}")
        return None

    def _execute_with_fallback(self, ticker: str, text: str) -> Optional[SentimentResult]:
        """
        Executes sentiment analysis trying primary provider first,
        and gracefully cascading to secondary configured providers if rate limited (HTTP 429).
        """
        preferred_order = [self.provider]
        fallbacks = ["openrouter", "gemini", "openai", "anthropic"]
        for p in fallbacks:
            if p not in preferred_order:
                preferred_order.append(p)

        for p in preferred_order:
            if self._is_provider_in_cooldown(p):
                logger.debug(f"Skipping LLM provider '{p}' (in active cooldown)")
                continue

            # Verify key exists
            if p == "gemini" and (not self.gemini_key or self.gemini_key.startswith("your_")):
                continue
            elif p == "openrouter" and (not self.openrouter_key or self.openrouter_key.startswith("your_")):
                continue
            elif p == "openai" and (not self.openai_key or self.openai_key.startswith("your_")):
                continue
            elif p == "anthropic" and (not self.anthropic_key or self.anthropic_key.startswith("your_")):
                continue

            try:
                self._pace_call()
                logger.info(f"Attempting sentiment analysis via provider '{p}' for {ticker}")
                if p == "gemini":
                    res = self._call_gemini(ticker, text)
                elif p == "openrouter":
                    res = self._call_openrouter(ticker, text)
                elif p == "openai":
                    res = self._call_openai(ticker, text)
                elif p == "anthropic":
                    res = self._call_anthropic(ticker, text)
                else:
                    res = None

                if res is not None:
                    return res
            except Exception as e:
                err_str = str(e).lower()
                if "429" in err_str or "quota" in err_str:
                    logger.warning(f"Quota exceeded on '{p}' for {ticker}: {e}")
                    self._set_provider_cooldown(p, duration_seconds=1800.0)
                else:
                    logger.warning(f"Provider '{p}' error for {ticker}: {e}")

        return None

    def analyze(self, ticker: str, text: Optional[str]) -> SentimentResult:
        """
        Analyzes sentiment of disclosure text.
        Includes materiality pre-filtering, intelligent RPM pacing, and multi-provider fallback.
        """
        clean_ticker = ticker.upper().replace(".JK", "")

        is_mat, reason = self.is_material_disclosure(text or "")
        if not is_mat:
            logger.info(f"[{clean_ticker}] Pre-filter skipped LLM: {reason}")
            return SentimentResult.neutral_fallback(clean_ticker, reason=reason)

        try:
            res = self._execute_with_fallback(clean_ticker, text or "")
            if res is not None:
                return res
        except (httpx.TimeoutException, TimeoutError):
            logger.warning(
                f"LLM API timed out after {self.timeout}s for {clean_ticker}. Activating technical-only fallback."
            )
        except Exception as e:
            logger.error(f"Unexpected error in sentiment evaluation for {clean_ticker}: {e}")

        # Graceful fallback per §6.2
        return SentimentResult.neutral_fallback(
            clean_ticker,
            reason="Analisis sentimen AI dilewati (fallback teknikal murni aktif)."
        )
