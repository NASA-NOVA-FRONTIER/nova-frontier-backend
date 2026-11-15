import json
import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from nisar_hazard_watch.api.dependencies import AssistantRateLimit, AssistantServiceDep
from nisar_hazard_watch.constants.assistant import ASSISTANT_FAILED_DETAIL, AssistantEventName
from nisar_hazard_watch.constants.errors import ReasonCode
from nisar_hazard_watch.exceptions.app_error import AppError
from nisar_hazard_watch.models.assistant import AssistantRequest
from nisar_hazard_watch.ports.assistant_model import AnswerDelta
from nisar_hazard_watch.services.assistant_service import AssistantService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["assistant"])

EVENT_STREAM = "text/event-stream"
# Proxies must pass each event on at once instead of buffering the answer.
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
REFUSAL = "refusal"


def sse(event: AssistantEventName, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def answer_events(service: AssistantService, request: AssistantRequest) -> AsyncIterator[str]:
    """The answer as server-sent events; a failure after the stream opens is an error event."""
    try:
        async for event in service.answer(request=request):
            if isinstance(event, AnswerDelta):
                yield sse(AssistantEventName.DELTA, {"text": event.text})
            elif event.stop_reason == REFUSAL:
                # The model declined (after any fallback): the chat discards the partial answer.
                yield sse(AssistantEventName.ERROR, {"reasonCode": ReasonCode.ASSISTANT_DECLINED})
            else:
                yield sse(
                    AssistantEventName.DONE, {"stopReason": event.stop_reason, "model": event.model}
                )
    except AppError as exc:
        yield sse(AssistantEventName.ERROR, {"reasonCode": exc.reason_code})
    except Exception:
        logger.exception("assistant stream failed")
        yield sse(
            AssistantEventName.ERROR,
            {"reasonCode": ReasonCode.INTERNAL_ERROR, "detail": ASSISTANT_FAILED_DETAIL},
        )


@router.post("", response_class=StreamingResponse, dependencies=[AssistantRateLimit])
async def ask_assistant(body: AssistantRequest, service: AssistantServiceDep) -> StreamingResponse:
    # Unavailable or over budget is said before the stream starts, as a problem response.
    service.ensure_available()
    return StreamingResponse(
        answer_events(service=service, request=body),
        media_type=EVENT_STREAM,
        headers=STREAM_HEADERS,
    )
