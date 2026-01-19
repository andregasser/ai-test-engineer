from langchain_google_genai import ChatGoogleGenerativeAI
from google.genai import errors as google_errors
import httpx

# Standard model instance for all agents
_base_model = ChatGoogleGenerativeAI(model="gemini-3-flash-preview")

GEMINI_FLASH_3_PREVIEW_MODEL = _base_model.with_retry(
    retry_if_exception_type=(
        google_errors.ServerError,
        google_errors.APIError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    ),
    wait_exponential_jitter=True,
    stop_after_attempt=10
)