"""Self-contained HTML review surface.

The page is read-only. It has no external assets and no way to submit a
decision. Decisions stay on the command line, where they still do not execute
an external action.
"""
from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Optional

from .queue import ReviewQueue


def render_reviews(queue: ReviewQueue) -> str:
    items = queue.list_items()
    blocks = []
    if not items:
        blocks.append("<p>No review items are queued.</p>")
    for item in items:
        recommendations = "".join(
            "<li><code>{agent}</code> / <code>{stage}</code> — {summary}</li>".format(
                agent=html.escape(rec["agent_id"]),
                stage=html.escape(rec["stage_id"]),
                summary=html.escape(rec["summary"]),
            )
            for rec in item["recommendations"]
        ) or "<li>No agent recommendation was recorded.</li>"
        unknowns = "".join(f"<li>{html.escape(text)}</li>" for text in item["unknowns"]) or "<li>None recorded.</li>"
        risks = "".join(f"<li>{html.escape(text)}</li>" for text in item["risks"]) or "<li>None recorded.</li>"
        decision = item.get("decision") or {}
        decision_text = "pending" if not decision else (
            f"{decision.get('decision')} by {decision.get('decided_by')}; "
            f"executed_external_action={decision.get('executed_external_action')}"
        )
        blocks.append(
            """
            <article class="item" data-review-id="{review_id}">
              <p class="banner">{banner}</p>
              <h2>{objective}</h2>
              <p><strong>{status}</strong> · {division} · {workflow}</p>
              <p>{summary}</p>
              <h3>Recommendations</h3>
              <ul>{recommendations}</ul>
              <h3>Unknowns</h3>
              <ul>{unknowns}</ul>
              <h3>Risks</h3>
              <ul>{risks}</ul>
              <p>Decision: {decision}</p>
              <p>Consequential actions performed: {actions}</p>
            </article>
            """.format(
                review_id=html.escape(item["review_id"]),
                banner=html.escape(item["banner"]),
                objective=html.escape(item["objective"]),
                status=html.escape(item["status"]),
                division=html.escape(item["division"]),
                workflow=html.escape(item["workflow_id"]),
                summary=html.escape(item["summary"]),
                recommendations=recommendations,
                unknowns=unknowns,
                risks=risks,
                decision=html.escape(decision_text),
                actions=html.escape(str(len(item["consequential_actions_performed"]))),
            )
        )
    body = "\n".join(blocks)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>GROKBOT human review</title>
  <style>
    body {{ font-family: Georgia, serif; margin: 2rem; color: #1c1917; background: #faf7f2; }}
    article {{ background: #fff; border: 1px solid #d6d3d1; padding: 1rem 1.25rem; margin-bottom: 1rem; }}
    .banner {{ background: #fef3c7; padding: 0.5rem 0.75rem; }}
    code {{ font-family: ui-monospace, monospace; }}
  </style>
</head>
<body>
  <h1>GROKBOT human review</h1>
  <p class="banner">READ ONLY. This page cannot approve, deny, purchase, publish, contact a supplier, message a customer, place an order, or issue a refund.</p>
  {body}
</body>
</html>
"""


class _ReviewHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        payload = render_reviews(self.server.queue).encode("utf-8")  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _ReviewServer(ThreadingHTTPServer):
    def __init__(self, server_address, queue: ReviewQueue):
        self.queue = queue
        super().__init__(server_address, _ReviewHandler)


def serve_reviews(queue: ReviewQueue, host: str = "127.0.0.1", port: int = 8765) -> _ReviewServer:
    """Serve the review page on localhost. POST is rejected."""
    return _ReviewServer((host, port), queue)
