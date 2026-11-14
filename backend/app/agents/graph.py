"""LangGraph orchestration: a hub-and-spoke StateGraph.

    START -> orchestrator -> <agent> -> orchestrator -> ... -> END

The orchestrator owns routing and shared state. It seeds a plan from the incoming event and
re-plans from agents' structured outputs (e.g. the Skill Validator's verdict turns SUBMIT_CODE
into a derived ASSESSMENT_PASSED or ASSESSMENT_FAILED event). Every agent step is persisted to
`agent_executions` and streamed to the learner over WebSocket.
"""
import asyncio
import logging
import time

from langgraph.graph import END, START, StateGraph

from ..db import session_scope
from ..events import publish
from ..models import AgentExecution, WorkflowRun, utcnow
from .nodes import HANDLERS
from .state import AGENTS, EVENTS, PLANS, AgentState

log = logging.getLogger("skillforge.agents")


def _plan_for(event: str) -> list[list[str]]:
    return [list(p) for p in PLANS[event]]


def _replan(state: AgentState) -> dict:
    """Orchestrator decision logic after an agent reports back."""
    agent, task = state.get("current", ["", ""])
    out = state.get("outputs", {}).get(agent, {})
    plan = list(state.get("plan", []))
    update: dict = {}
    if agent == "skill_validator" and task == "validate":
        verdict = out.get("verdict")
        if verdict == "passed":
            derived = "ASSESSMENT_PASSED"
            plan = _plan_for(derived)
            if out.get("mission_kind") == "applied":
                plan[-1] = ["ai_mentor", "start_viva"]  # Tier 3 stays locked until the viva
        elif verdict in ("tests_failed", "audit_failed"):
            derived = "ASSESSMENT_FAILED"
            plan = _plan_for(derived)
        else:
            return {"plan": [], "error": "Code execution engine unavailable"}
        update = {
            "event": derived,
            "event_chain": [*state.get("event_chain", []), derived],
            "payload": {**state.get("payload", {}), "kind": "submission"},
        }
    elif agent == "skill_detective" and task == "activity_check" and not out.get("stalled"):
        plan = []  # learner is active: nothing to do
    elif out.get("status") == "error":
        plan = []
        update["error"] = out.get("error", "agent failed")
    return {**update, "plan": plan}


async def orchestrator(state: AgentState) -> dict:
    update: dict = {}
    if "plan" not in state:
        if state["event"] not in EVENTS:
            return {"plan": [], "current": [], "error": f"Unsupported event {state['event']}"}
        update = {"plan": _plan_for(state["event"]), "event_chain": [state["event"]], "outputs": {}, "seq": 0}
    else:
        update = _replan(state)
    plan = update.get("plan", state.get("plan", []))
    if plan:
        update["current"], update["plan"] = plan[0], plan[1:]
    else:
        update["current"] = []
    return update


def route(state: AgentState) -> str:
    cur = state.get("current") or []
    return cur[0] if cur else END


def _agent_node(name: str):
    async def node(state: AgentState) -> dict:
        task = state["current"][1]
        seq = state.get("seq", 0) + 1
        started = time.perf_counter()
        await publish(state["profile_id"], {"type": "agent_started", "run_id": state["run_id"], "seq": seq,
                                            "agent": name, "task": task, "event": state["event"]})
        try:
            output = await HANDLERS[name](state, task)
            status = "ok"
        except Exception as exc:  # an agent failure ends the run cleanly instead of crashing it
            log.exception("agent %s failed", name)
            output = {"task": task, "status": "error", "error": f"{type(exc).__name__}: {exc}"[:300]}
            status = "error"
        ms = int((time.perf_counter() - started) * 1000)
        with session_scope() as db:
            db.add(AgentExecution(run_id=state["run_id"], seq=seq, agent=name, task=task, status=status,
                                  output=output, duration_ms=ms))
        entry = {"seq": seq, "agent": name, "task": task, "event": state["event"], "status": status,
                 "duration_ms": ms, "output": output}
        await publish(state["profile_id"], {"type": "agent_finished", "run_id": state["run_id"], **entry})
        return {"outputs": {**state.get("outputs", {}), name: output}, "trace": [entry], "seq": seq}

    return node


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("orchestrator", orchestrator)
    for name in AGENTS:
        g.add_node(name, _agent_node(name))
        g.add_edge(name, "orchestrator")
    g.add_edge(START, "orchestrator")
    g.add_conditional_edges("orchestrator", route, {**{a: a for a in AGENTS}, END: END})
    return g.compile()


GRAPH = build_graph()


async def run_workflow(run_id: str) -> dict:
    """Execute a queued WorkflowRun through the agent graph and persist its result."""
    with session_scope() as db:
        run = db.get(WorkflowRun, run_id)
        if not run:
            raise ValueError("Unknown workflow run")
        run.status = "running"
        init: AgentState = {"run_id": run.id, "profile_id": run.profile_id, "event": run.event,
                            "payload": dict(run.payload), "trace": []}
    await publish(init["profile_id"], {"type": "run_started", "run_id": run_id, "event": init["event"]})
    try:
        final = await GRAPH.ainvoke(init, config={"recursion_limit": 40})
        status = "failed" if final.get("error") else "completed"
        result = {
            "event_chain": final.get("event_chain", []),
            "outputs": final.get("outputs", {}),
            "trace": [{k: t[k] for k in ("seq", "agent", "task", "event", "status", "duration_ms")} for t in final.get("trace", [])],
            "error": final.get("error"),
        }
    except Exception as exc:
        log.exception("workflow %s crashed", run_id)
        status, result = "failed", {"error": f"{type(exc).__name__}: {exc}"[:300], "trace": [], "outputs": {}, "event_chain": []}
    with session_scope() as db:
        run = db.get(WorkflowRun, run_id)
        run.status, run.result, run.finished_at = status, result, utcnow()
    summary = {"run_id": run_id, "event": init["event"], "status": status, **result}
    await publish(init["profile_id"], {"type": "run_finished", "run_id": run_id, "status": status,
                                       "event_chain": result.get("event_chain"), "error": result.get("error")})
    return summary


def run_workflow_job(run_id: str) -> dict:
    """RQ worker entrypoint."""
    return asyncio.run(run_workflow(run_id))
