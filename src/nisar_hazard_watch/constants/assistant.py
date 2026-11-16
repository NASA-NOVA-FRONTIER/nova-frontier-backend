from enum import StrEnum

# The Claude model behind Nova; ASSISTANT_MODEL overrides it without a deploy.
DEFAULT_ASSISTANT_MODEL = "claude-opus-5-5"
# A chat answer: short, so a low effort and a small output cap keep it fast and cheap.
ASSISTANT_EFFORT = "low"
ASSISTANT_MAX_OUTPUT_TOKENS = 2048
ASSISTANT_TIMEOUT_SECONDS = 60.0
ASSISTANT_MAX_RETRIES = 1
DEFAULT_ASSISTANT_RATE_LIMIT_PER_MINUTE = 6
# A ceiling on spend: every token a day counts, in and out, across all clients of this process.
DEFAULT_ASSISTANT_DAILY_TOKEN_LIMIT = 1_000_000

# Server-side fallback re-runs a declined answer on Anthropic's recommended model; only these
# models accept the parameter, so any other ASSISTANT_MODEL runs without it.
FALLBACK_BETA = "server-side-fallback-2026-07-01"
FALLBACK_MODELS = frozenset(
    {
        "claude-opus-5-5",
        "claude-opus-5",
        "claude-sonnet-5-5",
        "claude-fable-5-2",
        "claude-fable-5-1",
    }
)

# Size caps on what the browser may send; the frontend trims to them before sending.
MAX_MESSAGE_CHARS = 800
MAX_TURN_CHARS = 800
MAX_HISTORY_TURNS = 10
MAX_SHORT_TEXT = 160
MAX_LONG_TEXT = 400
MAX_FACTS = 16
MAX_LIMITATIONS = 8
MAX_SOURCES = 8

ASSISTANT_UNAVAILABLE_DETAIL = "the assistant is not configured on this server"
ASSISTANT_BUDGET_DETAIL = "the assistant has used today's budget; it resets at 00:00 UTC"
ASSISTANT_FAILED_DETAIL = "the assistant could not answer"


class AssistantEventName(StrEnum):
    """Server-sent events of one answer: text as it is written, then done or error."""

    DELTA = "delta"
    DONE = "done"
    ERROR = "error"
