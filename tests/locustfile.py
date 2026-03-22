"""Locust load testing for ArtGuard API.

Simulates realistic user traffic against a running ArtGuard instance.
Covers all major endpoints including authenticated and unauthenticated
requests, inference uploads, and error paths.

Usage (against deployed API):
    locust -f tests/locustfile.py --host https://api.artguard.example.com

Usage (local):
    locust -f tests/locustfile.py --host http://localhost:8000

Usage (headless, 50 users for 60 seconds):
    locust -f tests/locustfile.py --host http://localhost:8000 \
           --users 50 --spawn-rate 10 --run-time 60s --headless
"""

import io
import uuid

from locust import HttpUser, between, tag, task


def _make_test_jpeg(width: int = 600, height: int = 600) -> bytes:
    """Generate a minimal JPEG image for upload tests."""
    try:
        from PIL import Image
        img = Image.new("RGB", (width, height), color="red")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        return buf.getvalue()
    except ImportError:
        # Minimal valid JPEG if Pillow is not installed on the load-test runner
        return (
            b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
            b"\x00\x01\x00\x00\xff\xd9"
        )


class ArtGuardReadUser(HttpUser):
    """Simulates a logged-in user performing read-only operations.

    This is the most common user type — browsing inference history,
    checking stats, and viewing their profile.
    """

    weight = 3  # 3x more likely than write users
    wait_time = between(1, 3)

    def on_start(self):
        """Sign up with a unique email to get a JWT token."""
        email = f"read-{uuid.uuid4().hex[:8]}@loadtest.com"
        resp = self.client.post("/auth/signup", json={
            "username": "read_user",
            "email": email,
            "password": "loadtest123",
        })
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
        else:
            self.token = ""
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(10)
    @tag("health")
    def health_check(self):
        """High-frequency health check (simulates ALB probes)."""
        self.client.get("/health")

    @task(5)
    @tag("auth", "read")
    def get_profile(self):
        """Fetch own profile."""
        self.client.get("/auth/me", headers=self.headers)

    @task(5)
    @tag("inferences", "read")
    def list_inferences(self):
        """List inference history (paginated)."""
        self.client.get("/inferences?limit=10", headers=self.headers)

    @task(3)
    @tag("inferences", "read")
    def inference_stats(self):
        """Fetch inference count."""
        self.client.get("/inferences/stats", headers=self.headers)

    @task(1)
    @tag("read")
    def root_endpoint(self):
        """Fetch API info."""
        self.client.get("/")


class ArtGuardWriteUser(HttpUser):
    """Simulates a user performing write operations.

    Includes signup, login, profile updates, and password changes.
    """

    weight = 1
    wait_time = between(2, 5)

    def on_start(self):
        """Sign up and store credentials."""
        self.email = f"write-{uuid.uuid4().hex[:8]}@loadtest.com"
        self.password = "loadtest123"
        resp = self.client.post("/auth/signup", json={
            "username": "write_user",
            "email": self.email,
            "password": self.password,
        })
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
        else:
            self.token = ""
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    @tag("auth", "write")
    def login(self):
        """Re-login with existing credentials."""
        resp = self.client.post("/auth/login", json={
            "email": self.email,
            "password": self.password,
        })
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
            self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(2)
    @tag("auth", "write")
    def update_profile(self):
        """Update username."""
        new_name = f"user_{uuid.uuid4().hex[:6]}"
        self.client.put("/auth/profile", json={
            "username": new_name,
            "email": self.email,
        }, headers=self.headers)

    @task(1)
    @tag("auth", "write")
    def change_password(self):
        """Change password (back to the same one for simplicity)."""
        self.client.post("/auth/change-password", json={
            "currentPassword": self.password,
            "newPassword": self.password,  # Same password to keep tests working
        }, headers=self.headers)

    @task(2)
    @tag("inferences", "read")
    def list_inferences(self):
        """List inference history."""
        self.client.get("/inferences", headers=self.headers)


class ArtGuardInferenceUser(HttpUser):
    """Simulates a user uploading images for analysis.

    This is the heaviest workload — involves file upload, image processing,
    and (when deployed) Modal inference + Bedrock RAG calls.
    """

    weight = 1
    wait_time = between(5, 15)  # Slower — inference is expensive

    def on_start(self):
        """Sign up and prepare a test image."""
        email = f"infer-{uuid.uuid4().hex[:8]}@loadtest.com"
        resp = self.client.post("/auth/signup", json={
            "username": "inference_user",
            "email": email,
            "password": "loadtest123",
        })
        if resp.status_code == 200:
            self.token = resp.json()["access_token"]
        else:
            self.token = ""
        self.headers = {"Authorization": f"Bearer {self.token}"}
        self.test_image = _make_test_jpeg()

    @task(1)
    @tag("inference", "write")
    def submit_inference(self):
        """Upload an image for forgery detection analysis."""
        self.client.post(
            "/inference",
            data={
                "artist_name": "Claude Monet",
                "artwork_name": f"Test Painting {uuid.uuid4().hex[:6]}",
            },
            files={"file": ("painting.jpg", self.test_image, "image/jpeg")},
            headers=self.headers,
        )

    @task(3)
    @tag("inferences", "read")
    def list_inferences(self):
        """Check inference history after submitting."""
        self.client.get("/inferences", headers=self.headers)

    @task(2)
    @tag("inferences", "read")
    def inference_stats(self):
        """Check total inference count."""
        self.client.get("/inferences/stats", headers=self.headers)


class ArtGuardUnauthenticatedUser(HttpUser):
    """Simulates unauthenticated requests (bots, crawlers, bad actors).

    Verifies the API correctly rejects unauthorized access under load
    without crashing or leaking information.
    """

    weight = 1
    wait_time = between(1, 2)

    @task(5)
    @tag("health")
    def health_check(self):
        """Health check (public)."""
        self.client.get("/health")

    @task(3)
    @tag("error")
    def unauthorized_inferences(self):
        """Try to access /inferences without auth (should get 401)."""
        with self.client.get(
            "/inferences", catch_response=True
        ) as resp:
            if resp.status_code == 401:
                resp.success()
            else:
                resp.failure(f"Expected 401, got {resp.status_code}")

    @task(2)
    @tag("error")
    def unauthorized_inference(self):
        """Try to POST /inference without auth (should get 401)."""
        with self.client.post(
            "/inference",
            data={"artist_name": "Test", "artwork_name": "Test"},
            files={"file": ("test.jpg", b"fake", "image/jpeg")},
            catch_response=True,
        ) as resp:
            if resp.status_code in (401, 422):
                resp.success()
            else:
                resp.failure(f"Expected 401/422, got {resp.status_code}")

    @task(2)
    @tag("error")
    def bad_login(self):
        """Brute-force style bad login attempt (should get 401)."""
        with self.client.post(
            "/auth/login",
            json={"email": "nobody@example.com", "password": "wrong"},
            catch_response=True,
        ) as resp:
            if resp.status_code == 401:
                resp.success()
            else:
                resp.failure(f"Expected 401, got {resp.status_code}")

    @task(1)
    @tag("read")
    def root(self):
        """Root endpoint (public)."""
        self.client.get("/")
