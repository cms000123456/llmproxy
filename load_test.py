#!/usr/bin/env python3
"""Load testing tool for LLM Proxy.

Tests the proxy under various load conditions to measure:
- Throughput (requests/sec)
- Latency (p50, p95, p99)
- Error rates
- Cache effectiveness
- Concurrent request handling

Usage:
    python load_test.py http://localhost:8080
    python load_test.py http://localhost:8080 --duration 60 --concurrency 50
    python load_test.py http://localhost:8080 --test-cache --test-streaming
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx


@dataclass
class LoadTestResult:
    """Results from a load test run."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    latencies: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    start_time: float = 0.0
    end_time: float = 0.0

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def throughput(self) -> float:
        if self.duration == 0:
            return 0.0
        return self.total_requests / self.duration

    @property
    def success_rate(self) -> float:
        if self.total_requests == 0:
            return 0.0
        return self.successful_requests / self.total_requests * 100

    @property
    def cache_hit_rate(self) -> float:
        total = self.cache_hits + self.cache_misses
        if total == 0:
            return 0.0
        return self.cache_hits / total * 100

    @property
    def p50_latency(self) -> float:
        if not self.latencies:
            return 0.0
        return statistics.median(self.latencies)

    @property
    def p95_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.95)
        return sorted_latencies[idx]

    @property
    def p99_latency(self) -> float:
        if not self.latencies:
            return 0.0
        sorted_latencies = sorted(self.latencies)
        idx = int(len(sorted_latencies) * 0.99)
        return sorted_latencies[idx]

    def print_summary(self):
        """Print test results summary."""
        print("\n" + "=" * 60)
        print("LOAD TEST RESULTS")
        print("=" * 60)
        print(f"Duration:          {self.duration:.2f}s")
        print(f"Total Requests:    {self.total_requests}")
        print(f"Successful:        {self.successful_requests} ({self.success_rate:.1f}%)")
        print(f"Failed:            {self.failed_requests}")
        print(f"Throughput:        {self.throughput:.2f} req/s")
        print()
        print("LATENCY (ms)")
        print(f"  P50:             {self.p50_latency:.2f}")
        print(f"  P95:             {self.p95_latency:.2f}")
        print(f"  P99:             {self.p99_latency:.2f}")
        print()
        print("CACHE PERFORMANCE")
        print(f"  Hits:            {self.cache_hits}")
        print(f"  Misses:          {self.cache_misses}")
        print(f"  Hit Rate:        {self.cache_hit_rate:.1f}%")
        print("=" * 60)

        if self.errors:
            print("\nERRORS (first 5):")
            for i, error in enumerate(self.errors[:5], 1):
                print(f"  {i}. {error}")


class LoadTester:
    """Load testing orchestrator."""

    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        concurrent: int = 10,
        duration: int = 30,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.concurrent = concurrent
        self.duration = duration
        self.result = LoadTestResult()
        self._stop_event = asyncio.Event()
        self._lock = asyncio.Lock()

    def _get_headers(self) -> dict[str, str]:
        """Get request headers."""
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def _get_payload(self, test_type: str = "default") -> dict[str, Any]:
        """Generate test payload."""
        payloads = {
            "default": {
                "model": "moonshot-v1-8k",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Say 'hello' and nothing else."},
                ],
                "max_tokens": 10,
            },
            "cache_test": {
                "model": "moonshot-v1-8k",
                "messages": [
                    {"role": "user", "content": "What is 2+2? Reply with just the number."},
                ],
                "max_tokens": 5,
            },
            "long_context": {
                "model": "moonshot-v1-128k",
                "messages": [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Summarize this: " + "Lorem ipsum. " * 500},
                ],
                "max_tokens": 100,
            },
            "streaming": {
                "model": "moonshot-v1-8k",
                "messages": [
                    {"role": "user", "content": "Count from 1 to 5."},
                ],
                "max_tokens": 50,
                "stream": True,
            },
        }
        return payloads.get(test_type, payloads["default"])

    async def _make_request(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        test_cache: bool = False,
    ) -> dict[str, Any]:
        """Make a single request and measure."""
        start_time = time.time()
        cache_hit = False

        try:
            response = await client.post(
                f"{self.base_url}/v1/chat/completions",
                headers=self._get_headers(),
                json=payload,
                timeout=60.0,
            )
            latency = (time.time() - start_time) * 1000  # ms

            if response.status_code == 200:
                data = response.json()
                # Check for cache header (if proxy adds it)
                cache_status = response.headers.get("X-Cache-Status", "")
                cache_hit = cache_status == "HIT"
                return {
                    "success": True,
                    "latency": latency,
                    "cache_hit": cache_hit,
                    "tokens": data.get("usage", {}).get("total_tokens", 0),
                }
            else:
                return {
                    "success": False,
                    "latency": latency,
                    "error": f"HTTP {response.status_code}: {response.text[:100]}",
                }

        except httpx.TimeoutException:
            return {
                "success": False,
                "latency": (time.time() - start_time) * 1000,
                "error": "Timeout",
            }
        except Exception as e:
            return {
                "success": False,
                "latency": (time.time() - start_time) * 1000,
                "error": str(e)[:100],
            }

    async def _worker(
        self,
        client: httpx.AsyncClient,
        payload: dict[str, Any],
        test_cache: bool,
    ):
        """Worker that continuously makes requests until stopped."""
        while not self._stop_event.is_set():
            result = await self._make_request(client, payload, test_cache)

            async with self._lock:
                self.result.total_requests += 1
                self.result.latencies.append(result["latency"])

                if result["success"]:
                    self.result.successful_requests += 1
                    if result.get("cache_hit"):
                        self.result.cache_hits += 1
                    else:
                        self.result.cache_misses += 1
                else:
                    self.result.failed_requests += 1
                    if len(self.result.errors) < 100:  # Limit stored errors
                        self.result.errors.append(result.get("error", "Unknown"))

            # Small delay to prevent overwhelming
            await asyncio.sleep(0.01)

    async def run_load_test(
        self,
        test_type: str = "default",
        test_cache: bool = False,
    ) -> LoadTestResult:
        """Run the load test."""
        print(f"\n🚀 Starting Load Test")
        print(f"   Target: {self.base_url}")
        print(f"   Concurrent: {self.concurrent}")
        print(f"   Duration: {self.duration}s")
        print(f"   Test Type: {test_type}")
        if test_cache:
            print(f"   Cache Test: Enabled")
        print()

        payload = self._get_payload(test_type)
        self.result.start_time = time.time()
        self._stop_event.clear()

        limits = httpx.Limits(
            max_connections=self.concurrent * 2,
            max_keepalive_connections=self.concurrent,
        )

        async with httpx.AsyncClient(limits=limits) as client:
            # Pre-warm cache if testing cache
            if test_cache:
                print("🔄 Pre-warming cache...")
                for _ in range(5):
                    await self._make_request(client, payload, test_cache)
                print("✅ Cache warmed\n")

            # Start workers
            print(f"🔄 Starting {self.concurrent} workers...")
            workers = [
                asyncio.create_task(self._worker(client, payload, test_cache))
                for _ in range(self.concurrent)
            ]

            # Run for duration
            await asyncio.sleep(self.duration)
            self._stop_event.set()

            # Wait for workers to finish
            await asyncio.gather(*workers, return_exceptions=True)

        self.result.end_time = time.time()
        return self.result

    async def run_cache_test(self) -> LoadTestResult:
        """Run cache effectiveness test."""
        print("\n📦 Cache Effectiveness Test")
        print(f"   Making 100 identical requests...")

        payload = self._get_payload("cache_test")
        self.result.start_time = time.time()

        limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)

        async with httpx.AsyncClient(limits=limits) as client:
            # First request (cache miss)
            await self._make_request(client, payload, True)

            # 99 more identical requests
            tasks = [
                self._make_request(client, payload, True)
                for _ in range(99)
            ]
            results = await asyncio.gather(*tasks)

            for result in results:
                self.result.total_requests += 1
                self.result.latencies.append(result["latency"])

                if result["success"]:
                    self.result.successful_requests += 1
                    if result.get("cache_hit"):
                        self.result.cache_hits += 1
                    else:
                        self.result.cache_misses += 1
                else:
                    self.result.failed_requests += 1

        self.result.end_time = time.time()
        return self.result

    async def run_stress_test(self) -> LoadTestResult:
        """Run stress test with increasing load."""
        print("\n🔥 Stress Test (Ramp-up)")

        payload = self._get_payload("default")
        self.result.start_time = time.time()

        limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)

        async with httpx.AsyncClient(limits=limits) as client:
            for concurrency in [10, 25, 50, 100]:
                print(f"\n  Testing with {concurrency} concurrent connections...")
                self._stop_event.clear()

                workers = [
                    asyncio.create_task(self._worker(client, payload, False))
                    for _ in range(concurrency)
                ]

                await asyncio.sleep(15)  # 15 seconds per level
                self._stop_event.set()
                await asyncio.gather(*workers, return_exceptions=True)

                print(f"    Total requests so far: {self.result.total_requests}")

        self.result.end_time = time.time()
        return self.result


def main():
    parser = argparse.ArgumentParser(
        description="Load testing tool for LLM Proxy",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s http://localhost:8080
  %(prog)s http://localhost:8080 -d 60 -c 50
  %(prog)s http://localhost:8080 --test-cache
  %(prog)s http://localhost:8080 --stress-test
        """,
    )
    parser.add_argument("url", help="LLM Proxy base URL")
    parser.add_argument(
        "-k", "--api-key", help="API key for authentication"
    )
    parser.add_argument(
        "-d", "--duration", type=int, default=30,
        help="Test duration in seconds (default: 30)"
    )
    parser.add_argument(
        "-c", "--concurrent", type=int, default=10,
        help="Number of concurrent connections (default: 10)"
    )
    parser.add_argument(
        "-t", "--test-type", default="default",
        choices=["default", "long_context", "streaming"],
        help="Type of test payload"
    )
    parser.add_argument(
        "--test-cache", action="store_true",
        help="Test cache effectiveness"
    )
    parser.add_argument(
        "--stress-test", action="store_true",
        help="Run ramp-up stress test"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output results as JSON"
    )

    args = parser.parse_args()

    tester = LoadTester(
        base_url=args.url,
        api_key=args.api_key,
        concurrent=args.concurrent,
        duration=args.duration,
    )

    async def run():
        if args.stress_test:
            result = await tester.run_stress_test()
        elif args.test_cache:
            result = await tester.run_cache_test()
        else:
            result = await tester.run_load_test(
                test_type=args.test_type,
                test_cache=args.test_cache,
            )
        return result

    try:
        result = asyncio.run(run())

        if args.json:
            output = {
                "duration": result.duration,
                "total_requests": result.total_requests,
                "successful": result.successful_requests,
                "failed": result.failed_requests,
                "success_rate": result.success_rate,
                "throughput": result.throughput,
                "latency_ms": {
                    "p50": result.p50_latency,
                    "p95": result.p95_latency,
                    "p99": result.p99_latency,
                },
                "cache": {
                    "hits": result.cache_hits,
                    "misses": result.cache_misses,
                    "hit_rate": result.cache_hit_rate,
                },
            }
            print(json.dumps(output, indent=2))
        else:
            result.print_summary()

        # Exit with error code if success rate is too low
        if result.success_rate < 95:
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⚠️ Test interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
