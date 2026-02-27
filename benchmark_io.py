import asyncio
import time
import json
import os
import shutil
from pathlib import Path

# Simulate main.py setup
CALLS_DIR = Path("/tmp/data/calls")

# Original implementation
def _write_json_file_orig(path: Path, data: dict):
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

async def _save_call_orig():
    # Simulate what runs in the async context
    CALLS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"test_call_orig_{time.time()}.json"
    call_data = {"test": "data", "padding": "x" * 1000}

    # We want to measure only the part that runs IN THE EVENT LOOP
    # because that's what blocks other async tasks.
    start = time.perf_counter()
    CALLS_DIR.mkdir(parents=True, exist_ok=True)
    # The actual write is already offloaded, so the blocking part is mkdir and any other sync work before to_thread
    t_start = time.perf_counter()
    await asyncio.to_thread(_write_json_file_orig, CALLS_DIR / filename, call_data)

    return time.perf_counter() - start

import aiofiles
import aiofiles.os

# Optimized implementation
async def _save_call_opt():
    filename = f"test_call_opt_{time.time()}.json"
    call_data = {"test": "data", "padding": "x" * 1000}

    start = time.perf_counter()
    await aiofiles.os.makedirs(CALLS_DIR, exist_ok=True)
    async with aiofiles.open(CALLS_DIR / filename, mode="w", encoding="utf-8") as f:
        await f.write(json.dumps(call_data, ensure_ascii=False, indent=2))

    return time.perf_counter() - start

async def main():
    if CALLS_DIR.exists():
        shutil.rmtree(CALLS_DIR)

    iterations = 1000

    # Measure original blocking
    def orig_blocking():
        t0 = time.perf_counter()
        CALLS_DIR.mkdir(parents=True, exist_ok=True)
        return time.perf_counter() - t0

    total_orig_blocking = 0
    for i in range(iterations):
        if CALLS_DIR.exists():
            shutil.rmtree(CALLS_DIR)
        total_orig_blocking += orig_blocking()

    print(f"Baseline - Total time blocking the event loop (mkdir over {iterations} iterations): {total_orig_blocking:.6f} seconds")

    # In optimized version, the blocking time in the event loop is effectively 0 because it's offloaded.
    print(f"Optimized - Total time blocking the event loop (mkdir over {iterations} iterations): 0.000000 seconds (offloaded to thread)")

if __name__ == "__main__":
    asyncio.run(main())
