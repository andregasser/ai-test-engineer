from langchain_google_genai import ChatGoogleGenerativeAI
from google.genai import errors as google_errors
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential_jitter, retry_if_exception_type

# Define the retry configuration outside the class to avoid Python treating it
# as an instance method when accessed via self.
_resilient_retry = retry(
    retry=retry_if_exception_type((
        google_errors.ServerError,
        google_errors.APIError,
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadTimeout,
        httpx.WriteTimeout,
        httpx.NetworkError,
        httpx.RemoteProtocolError,
    )),
    wait=wait_exponential_jitter(initial=1, max=60, jitter=1),
    stop=stop_after_attempt(10),
    reraise=True
)

class ResilientChatGoogleGenerativeAI(ChatGoogleGenerativeAI):
    """
    A subclass of ChatGoogleGenerativeAI that adds resilience via tenacity retries.
    This preserves the .profile attribute and other metadata required by deepagents,
    which are lost when using LCEL's .with_retry() wrapper.
    """
    
    def invoke(self, *args, **kwargs):
        # Apply the retry decorator to the super().invoke method dynamically
        return _resilient_retry(super().invoke)(*args, **kwargs)

    async def ainvoke(self, *args, **kwargs):
        # Apply the retry decorator to the super().ainvoke method dynamically
        return await _resilient_retry(super().ainvoke)(*args, **kwargs)

# Standard model instance for all agents
GEMINI_FLASH_3_PREVIEW_MODEL = ResilientChatGoogleGenerativeAI(model="gemini-3-flash-preview")