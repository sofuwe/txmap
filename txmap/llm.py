"""Optional LLM fallback: names merchants the nearest-neighbour model has no match for.

Used only when exact and similarity matching both fail. The prompt includes the closest
labelled examples, so the LLM follows your naming style. Answers are cached on disk, so
each descriptor is sent to the API once.

Requires the `anthropic` package (`uv sync --extra llm`) and an API key in
ANTHROPIC_API_KEY. Sends the raw descriptor and the nearest labels to the Anthropic API.
"""
import json
import os
import threading

DEFAULT_MODEL = "claude-opus-5-5"
CACHE_PATH = os.path.join(os.path.dirname(__file__), "data/models/llm-cache.json")
PROMPT_VERSION = 1  # bump when the prompt changes so old cached answers are ignored

# Models that support server-side refusal fallbacks (see the Anthropic API docs).
_FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"}

SYSTEM = """\
You turn bank transaction descriptors into clean merchant names for a personal budgeting \
tool. The account holder lives in the Greater Toronto Area, Canada.

Descriptors are noisy: often uppercase, cut off mid-word, with store numbers, city or \
branch names, and payment-processor prefixes (SQ, TST, PAYPAL, GOOGLE *, WP*).

Return the name a person would write for the merchant:
- Finish words that were cut off when you're confident ("FRESH PALACE SUPERMARK" -> \
"Fresh Palace Supermarket", "ISLAMIC SOCIETY OF MAR" -> "Islamic Society Of Markham").
- Use the brand's real spelling and capitalization ("DICKEYS BARBEQU" -> \
"Dickey's Barbecue Pit").
- Drop store numbers, branch names and city suffixes.
- For app-store or processor charges, name the actual service ("GOOGLE *YouTube" -> "YouTube").
- Bank fees and transfers are named after the bank, like the examples show.

The labelled examples are the account holder's own labels. When an example shows how \
they name something, follow it over the rules above. If you can't tell what the merchant \
is, return the descriptor in title case with the noise removed. Don't invent a business."""

SCHEMA = {
    "type": "object",
    "properties": {"merchant": {"type": "string"}},
    "required": ["merchant"],
    "additionalProperties": False,
}


_NO_KEY = ("error: --llm needs an Anthropic API key. Set ANTHROPIC_API_KEY (e.g. in ~/.zshrc, "
           "then open a new terminal or run `source ~/.zshrc`).")


def _exit_if_auth_error(e):
    """Turn the SDK's missing/invalid-credential errors into a one-line exit message."""
    # A missing key fails before any request, as a TypeError from the SDK's header check.
    if isinstance(e, TypeError) and "authentication method" in str(e):
        raise SystemExit(_NO_KEY) from None
    if type(e).__name__ == "AuthenticationError":  # 401: key is set but rejected
        raise SystemExit("error: the Anthropic API rejected your API key (401). "
                         "Check ANTHROPIC_API_KEY.") from None


class LLMNamer:
    def __init__(self, model=DEFAULT_MODEL, cache_path=CACHE_PATH, client=None):
        self.model = model
        self.cache_path = cache_path
        self._client = client
        self._lock = threading.Lock()
        self.calls = 0
        try:
            with open(cache_path) as f:
                self._cache = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            self._cache = {}

    @property
    def client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as e:
                raise SystemExit("error: --llm needs the anthropic package; run `uv sync --extra llm`") from e
            self._client = anthropic.Anthropic()
        return self._client

    def _key(self, bank, raw):
        return f"v{PROMPT_VERSION}|{self.model}|{bank}|{raw.strip()}"

    def name(self, bank, raw, key, examples):
        """examples: [(bank, cleaned_key, merchant)] nearest labels. Returns a name or None."""
        ck = self._key(bank, raw)
        with self._lock:
            if ck in self._cache:
                return self._cache[ck]
        shots = "\n".join(f"{b} | {k} -> {m}" for b, k, m in examples) or "(none)"
        prompt = (f"Closest labelled examples (bank | cleaned descriptor -> merchant):\n{shots}\n\n"
                  f"Name this one.\nBank: {bank}\nRaw descriptor: {raw.strip()}\n"
                  f"Cleaned descriptor: {key}")
        extra = {}
        if self.model in _FALLBACK_MODELS:
            extra = {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
        try:
            resp = self.client.beta.messages.create(
                model=self.model,
                max_tokens=1024,
                system=SYSTEM,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
                **extra,
            )
        except Exception as e:
            _exit_if_auth_error(e)
            raise
        self.calls += 1
        if resp.stop_reason != "end_turn":
            return None  # refusal or truncation: let the caller use its own fallback
        text = next((b.text for b in resp.content if b.type == "text"), "")
        merchant = json.loads(text)["merchant"].strip() or None
        with self._lock:
            self._cache[ck] = merchant
        return merchant

    def save(self):
        os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
        with self._lock, open(self.cache_path, "w") as f:
            json.dump(self._cache, f, indent=1, sort_keys=True)
