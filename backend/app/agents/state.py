"""Shared state passed between agents in the LangGraph workflow."""
import operator
from typing import Annotated, TypedDict

EVENTS = ("ONBOARD", "SUBMIT_CODE", "ASSESSMENT_FAILED", "ASSESSMENT_PASSED", "PIVOT_GOAL", "STALLED")

AGENTS = (
    "skill_detective",
    "career_architect",
    "learning_strategist",
    "resource_scout",
    "skill_validator",
    "ai_mentor",
)

# Initial plan per event: ordered (agent, task) pairs. The orchestrator may re-plan
# after any agent reports back (e.g. SUBMIT_CODE branches on the validator's verdict).
PLANS: dict[str, list[tuple[str, str]]] = {
    "ONBOARD": [
        ("skill_detective", "profile_scan"),
        ("career_architect", "gap_analysis"),
        ("learning_strategist", "generate_roadmap"),
        ("resource_scout", "attach_resources"),
        ("ai_mentor", "brief"),
    ],
    "SUBMIT_CODE": [("skill_validator", "validate")],
    "ASSESSMENT_PASSED": [
        ("skill_detective", "record_evidence"),
        ("career_architect", "gap_analysis"),
        ("learning_strategist", "update_progress"),
        ("ai_mentor", "debrief"),
    ],
    "ASSESSMENT_FAILED": [
        ("ai_mentor", "remediate"),
        ("resource_scout", "find_remediation"),
        ("learning_strategist", "add_remediation"),
    ],
    "PIVOT_GOAL": [
        ("skill_detective", "transferable_skills"),
        ("career_architect", "gap_analysis"),
        ("learning_strategist", "generate_roadmap"),
        ("resource_scout", "attach_resources"),
        ("ai_mentor", "brief"),
    ],
    "STALLED": [
        ("skill_detective", "activity_check"),
        ("learning_strategist", "rebalance"),
        ("resource_scout", "attach_resources"),
        ("ai_mentor", "nudge"),
    ],
}


class AgentState(TypedDict, total=False):
    run_id: str
    profile_id: str
    event: str  # the event currently being handled (may change when the orchestrator derives one)
    event_chain: list[str]  # every event handled in this run, in order
    payload: dict
    plan: list[list[str]]  # remaining [agent, task] pairs
    current: list[str]  # [agent, task] being executed
    outputs: dict  # agent name -> its latest structured JSON output (the shared blackboard)
    trace: Annotated[list, operator.add]  # append-only execution log
    seq: int
    error: str
