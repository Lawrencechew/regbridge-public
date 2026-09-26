from __future__ import annotations

from collections import Counter
from threading import Lock


def route_group(path: str) -> str:
    if path.startswith("/auth/"):
        return "/auth"
    for prefix in ("/api/v1/regflow", "/api/v1/imports", "/api/v1/outputs", "/api/v1/mapping-profiles", "/api/v1/organisations", "/api/v1/regpacks"):
        if path.startswith(prefix):
            return prefix
    if path in {"/api/v1/health", "/api/v1/ready", "/api/v1/metrics"}:
        return path
    return "/other"


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self.requests: Counter[tuple[str, str, str]] = Counter()
        self.request_duration_sum: Counter[str] = Counter()
        self.request_duration_count: Counter[str] = Counter()
        self.auth: Counter[str] = Counter()
        self.regflow: Counter[str] = Counter()
        self.db_ready = 0

    def observe_request(self, method: str, path: str, status: int, seconds: float) -> None:
        group = route_group(path)
        status_class = f"{status // 100}xx"
        with self._lock:
            self.requests[(method, group, status_class)] += 1
            self.request_duration_sum[group] += seconds
            self.request_duration_count[group] += 1
            if path.startswith("/auth/callback"):
                self.auth["success" if status < 400 else "failure"] += 1
            if path.startswith("/api/v1/outputs/") and method == "POST":
                self.regflow["completed" if status < 400 else "failed"] += 1

    def set_db_ready(self, ready: bool) -> None:
        with self._lock:
            self.db_ready = int(ready)

    def render(self) -> str:
        lines = ["# HELP regbridge_http_requests_total HTTP requests by bounded route group.", "# TYPE regbridge_http_requests_total counter"]
        with self._lock:
            for (method, route, status_class), value in sorted(self.requests.items()):
                lines.append(f'regbridge_http_requests_total{{method="{method}",route="{route}",status="{status_class}"}} {value}')
            lines.extend(("# HELP regbridge_http_request_duration_seconds_sum Total HTTP request duration.", "# TYPE regbridge_http_request_duration_seconds_sum counter"))
            for route, value in sorted(self.request_duration_sum.items()):
                lines.append(f'regbridge_http_request_duration_seconds_sum{{route="{route}"}} {value:.6f}')
                lines.append(f'regbridge_http_request_duration_seconds_count{{route="{route}"}} {self.request_duration_count[route]}')
            lines.extend(("# HELP regbridge_authentication_total Authentication callback outcomes.", "# TYPE regbridge_authentication_total counter"))
            for result in ("success", "failure"):
                lines.append(f'regbridge_authentication_total{{result="{result}"}} {self.auth[result]}')
            lines.extend(("# HELP regbridge_regflow_generation_total RegFlow generation outcomes.", "# TYPE regbridge_regflow_generation_total counter"))
            for result in ("completed", "failed"):
                lines.append(f'regbridge_regflow_generation_total{{result="{result}"}} {self.regflow[result]}')
            lines.extend(("# HELP regbridge_database_ready Database readiness state.", "# TYPE regbridge_database_ready gauge", f"regbridge_database_ready {self.db_ready}"))
        return "\n".join(lines) + "\n"
