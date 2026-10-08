"""Load test for /ask.   locust -f loadtest/locustfile.py --host http://localhost:8080 --headless -u 50 -r 10 -t 2m"""

import json
import random
from pathlib import Path

from locust import HttpUser, between, task

QUESTIONS = [q["question"] for q in json.loads(Path(__file__).parents[1].joinpath("data/eval/questions.json").read_text(encoding="utf-8"))]


class AskUser(HttpUser):
    wait_time = between(0.5, 2.0)  # a person reads the answer before asking again

    @task(10)
    def ask(self):
        with self.client.post("/ask", json={"question": random.choice(QUESTIONS)}, name="/ask", catch_response=True) as r:
            if r.status_code != 200 or not r.json().get("answer"):
                r.failure(f"bad response {r.status_code}")

    @task(2)
    def ask_stream(self):
        with self.client.post("/ask/stream", json={"question": random.choice(QUESTIONS)}, name="/ask/stream", stream=True, catch_response=True) as r:
            body = "".join(r.iter_content(chunk_size=None, decode_unicode=True))
            if "event: done" not in body:
                r.failure("stream did not finish")

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
