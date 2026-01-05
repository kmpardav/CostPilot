import asyncio
import random
import time


class HttpRetryPolicy:
    def __init__(self, max_retries=8, base_delay=1.0, max_delay=60.0):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    def wait(self, attempt, retry_after=None):
        if retry_after:
            time.sleep(float(retry_after))
            return
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        delay += random.uniform(0, delay * 0.2)
        time.sleep(delay)

    async def wait_async(self, attempt, retry_after=None):
        if retry_after:
            await asyncio.sleep(float(retry_after))
            return
        delay = min(self.max_delay, self.base_delay * (2 ** attempt))
        delay += random.uniform(0, delay * 0.2)
        await asyncio.sleep(delay)
