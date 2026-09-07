from tenacity import retry, stop_after_attempt, wait_exponential

default_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
)
