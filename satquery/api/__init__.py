"""FastAPI transport for the Step 5 agent pipeline: an upload+SSE endpoint
that streams each `TraceEntry` as its node completes. No pipeline logic
lives here — see `satquery.agent.graph.run_streaming`.
"""
