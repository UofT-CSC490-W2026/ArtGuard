"""Load and stress tests for ArtGuard API.

Two categories:
  1. **Concurrency tests** (run in CI via pytest) — verify the API handles
     many simultaneous requests without errors or status-code regressions.
  2. **Latency budget tests** — verify that endpoints respond within
     acceptable time bounds under concurrent load.

Run with:  pytest tests/test_load.py -m load -v
"""

import asyncio
import time
from io import BytesIO

import pytest
from PIL import Image

pytestmark = pytest.mark.load

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_jpeg(width: int = 600, height: int = 600) -> bytes:
    """Create a minimal JPEG in memory for upload tests."""
    img = Image.new("RGB", (width, height), color="blue")
    buf = BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Health / Root — high-concurrency smoke tests
# ---------------------------------------------------------------------------

class TestHealthEndpointLoad:
    """Verify /health survives high concurrency."""

    @pytest.mark.asyncio
    async def test_100_concurrent_health_checks(self, client):
        """100 concurrent GETs should all return 200."""
        async def hit():
            return (await client.get("/health")).status_code

        results = await asyncio.gather(*(hit() for _ in range(100)))
        assert all(c == 200 for c in results)
        assert len(results) == 100

    @pytest.mark.asyncio
    async def test_health_latency_under_50ms(self, client):
        """Each /health call should respond in < 50 ms (in-process)."""
        latencies = []
        for _ in range(20):
            t0 = time.perf_counter()
            resp = await client.get("/health")
            latencies.append((time.perf_counter() - t0) * 1000)
            assert resp.status_code == 200

        avg = sum(latencies) / len(latencies)
        p99 = sorted(latencies)[int(len(latencies) * 0.99)]
        assert avg < 50, f"Average latency {avg:.1f}ms exceeds 50ms"
        assert p99 < 100, f"p99 latency {p99:.1f}ms exceeds 100ms"


class TestRootEndpointLoad:
    """Verify / survives high concurrency."""

    @pytest.mark.asyncio
    async def test_50_concurrent_root(self, client):
        async def hit():
            return (await client.get("/")).status_code

        results = await asyncio.gather(*(hit() for _ in range(50)))
        assert all(c == 200 for c in results)


# ---------------------------------------------------------------------------
# Auth — write-path stress tests
# ---------------------------------------------------------------------------

class TestAuthLoad:
    """Load test auth endpoints (signup, login, profile reads)."""

    @pytest.mark.asyncio
    async def test_30_concurrent_signups(self, client):
        """30 simultaneous signups with unique emails should all succeed."""
        async def signup(i):
            return (await client.post("/auth/signup", json={
                "username": f"loaduser{i}",
                "email": f"load{i}@example.com",
                "password": "password123",
            })).status_code

        results = await asyncio.gather(*(signup(i) for i in range(30)))
        assert all(c == 200 for c in results)

    @pytest.mark.asyncio
    async def test_50_concurrent_profile_reads(self, client, create_test_user, auth_headers):
        """50 concurrent GET /auth/me with valid JWT."""
        create_test_user()

        async def fetch():
            return (await client.get("/auth/me", headers=auth_headers)).status_code

        results = await asyncio.gather(*(fetch() for _ in range(50)))
        assert all(c == 200 for c in results)

    @pytest.mark.asyncio
    async def test_login_then_profile_sequence(self, client, create_test_user):
        """Simulate 10 users each logging in then fetching their profile."""
        # Create 10 users
        for i in range(10):
            create_test_user(
                user_id=f"seq-user-{i}",
                email=f"seq{i}@example.com",
                username=f"sequser{i}",
            )

        async def login_and_profile(i):
            login_resp = await client.post("/auth/login", json={
                "email": f"seq{i}@example.com",
                "password": "password123",
            })
            if login_resp.status_code != 200:
                return login_resp.status_code
            token = login_resp.json()["access_token"]
            me_resp = await client.get(
                "/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            return me_resp.status_code

        results = await asyncio.gather(*(login_and_profile(i) for i in range(10)))
        assert all(c == 200 for c in results)

    @pytest.mark.asyncio
    async def test_invalid_login_burst(self, client):
        """50 concurrent invalid logins should all return 401 (not crash)."""
        async def bad_login():
            return (await client.post("/auth/login", json={
                "email": "nobody@example.com",
                "password": "wrong",
            })).status_code

        results = await asyncio.gather(*(bad_login() for _ in range(50)))
        assert all(c == 401 for c in results)


# ---------------------------------------------------------------------------
# Inferences history — read-path stress tests
# ---------------------------------------------------------------------------

class TestInferencesLoad:
    """Load test inference history endpoints."""

    @pytest.mark.asyncio
    async def test_50_concurrent_stats(self, client, auth_headers):
        """50 concurrent stats requests."""
        async def fetch():
            return (await client.get("/inferences/stats", headers=auth_headers)).status_code

        results = await asyncio.gather(*(fetch() for _ in range(50)))
        assert all(c == 200 for c in results)

    @pytest.mark.asyncio
    async def test_30_concurrent_list(self, client, auth_headers):
        """30 concurrent list requests."""
        async def fetch():
            return (await client.get("/inferences", headers=auth_headers)).status_code

        results = await asyncio.gather(*(fetch() for _ in range(30)))
        assert all(c == 200 for c in results)

    @pytest.mark.asyncio
    async def test_unauthenticated_burst(self, client):
        """50 unauthenticated requests should all get 401, not 500."""
        async def fetch():
            return (await client.get("/inferences/stats")).status_code

        results = await asyncio.gather(*(fetch() for _ in range(50)))
        assert all(c == 401 for c in results)


# ---------------------------------------------------------------------------
# Inference endpoint — upload stress test
# ---------------------------------------------------------------------------

class TestInferenceUploadLoad:
    """Load test the POST /inference upload endpoint."""

    @pytest.mark.asyncio
    async def test_concurrent_upload_validation(self, client, auth_headers):
        """10 concurrent uploads of invalid files should all return 400."""
        async def upload_bad():
            return (await client.post(
                "/inference",
                data={"artist_name": "Test", "artwork_name": "Test"},
                files={"file": ("bad.jpg", b"not-an-image", "image/jpeg")},
                headers=auth_headers,
            )).status_code

        results = await asyncio.gather(*(upload_bad() for _ in range(10)))
        assert all(c == 400 for c in results)

    @pytest.mark.asyncio
    async def test_concurrent_empty_uploads(self, client, auth_headers):
        """10 concurrent empty file uploads should all return 400."""
        async def upload_empty():
            return (await client.post(
                "/inference",
                data={"artist_name": "Test", "artwork_name": "Test"},
                files={"file": ("empty.jpg", b"", "image/jpeg")},
                headers=auth_headers,
            )).status_code

        results = await asyncio.gather(*(upload_empty() for _ in range(10)))
        assert all(c == 400 for c in results)


# ---------------------------------------------------------------------------
# Mixed workload — simulates real traffic patterns
# ---------------------------------------------------------------------------

class TestMixedWorkload:
    """Simulate a realistic mix of read and write traffic."""

    @pytest.mark.asyncio
    async def test_mixed_traffic(self, client, create_test_user, auth_headers):
        """Run 50 mixed requests: health checks, profile reads, stats, list."""
        create_test_user()

        async def health():
            return ("health", (await client.get("/health")).status_code)

        async def profile():
            return ("profile", (await client.get("/auth/me", headers=auth_headers)).status_code)

        async def stats():
            return ("stats", (await client.get("/inferences/stats", headers=auth_headers)).status_code)

        async def list_inf():
            return ("list", (await client.get("/inferences", headers=auth_headers)).status_code)

        # Build a mix: 20 health, 10 profile, 10 stats, 10 list = 50 total
        tasks = (
            [health() for _ in range(20)]
            + [profile() for _ in range(10)]
            + [stats() for _ in range(10)]
            + [list_inf() for _ in range(10)]
        )

        results = await asyncio.gather(*tasks)
        failures = [(name, code) for name, code in results if code != 200]
        assert not failures, f"Failed requests: {failures}"


# ---------------------------------------------------------------------------
# Throughput test
# ---------------------------------------------------------------------------

class TestThroughput:
    """Verify the API can sustain a minimum request rate."""

    @pytest.mark.asyncio
    async def test_sustained_throughput(self, client):
        """Send 200 requests and verify > 100 req/s throughput (in-process)."""
        n = 200
        t0 = time.perf_counter()

        async def hit():
            return (await client.get("/health")).status_code

        results = await asyncio.gather(*(hit() for _ in range(n)))
        elapsed = time.perf_counter() - t0
        rps = n / elapsed

        assert all(c == 200 for c in results)
        assert rps > 100, f"Throughput {rps:.0f} req/s is below 100 req/s target"
