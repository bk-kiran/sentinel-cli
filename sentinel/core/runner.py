"""
LangGraph supervisor that dispatches the three sentinel agents in parallel
and collects their results.
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END

from sentinel.agents.readability import run_readability_agent
from sentinel.agents.dead_code import run_dead_code_agent
from sentinel.agents.blast_radius import run_blast_radius_agent

_ALL_AGENTS = {"readability", "dead_code", "blast_radius"}


class SentinelState(TypedDict):
    diff: str
    call_graph: dict
    edited_functions: list[str]
    readability: list[str]
    dead_code: list[str]
    blast_radius: list[str]
    enabled_agents: set


def _readability_node(state: SentinelState) -> SentinelState:
    if "readability" not in state["enabled_agents"]:
        return state
    return {**state, "readability": run_readability_agent(state["diff"])}


def _dead_code_node(state: SentinelState) -> SentinelState:
    if "dead_code" not in state["enabled_agents"]:
        return state
    return {**state, "dead_code": run_dead_code_agent(state["diff"])}


def _blast_radius_node(state: SentinelState) -> SentinelState:
    if "blast_radius" not in state["enabled_agents"]:
        return state
    return {**state, "blast_radius": run_blast_radius_agent(
        edited_functions=state["edited_functions"],
        call_graph=state["call_graph"],
    )}


def _build_graph():
    graph = StateGraph(SentinelState)

    graph.add_node("readability", _readability_node)
    graph.add_node("dead_code", _dead_code_node)
    graph.add_node("blast_radius", _blast_radius_node)

    # Note: for true parallelism in v2, use Send() API.
    # For MVP: sequential is fine, output is identical.
    # TODO v2: fan out with Send() for concurrent execution
    graph.set_entry_point("readability")
    graph.add_edge("readability", "dead_code")
    graph.add_edge("dead_code", "blast_radius")
    graph.add_edge("blast_radius", END)

    return graph.compile()


_graph = _build_graph()


def run_agents(
    diff: str,
    call_graph: dict,
    edited_functions: list[str],
    enabled_agents: set | None = None,
) -> dict:
    """Run enabled agents and return their results."""
    initial_state: SentinelState = {
        "diff": diff,
        "call_graph": call_graph,
        "edited_functions": edited_functions,
        "readability": [],
        "dead_code": [],
        "blast_radius": [],
        "enabled_agents": enabled_agents if enabled_agents is not None else _ALL_AGENTS,
    }
    final_state = _graph.invoke(initial_state)
    return {
        "readability": final_state["readability"],
        "dead_code": final_state["dead_code"],
        "blast_radius": final_state["blast_radius"],
    }
