"""
LangGraph supervisor that dispatches the three sentinel agents in parallel
and collects their results.
"""
from typing import TypedDict
from langgraph.graph import StateGraph, END

from sentinel.agents.readability import run_readability_agent
from sentinel.agents.dead_code import run_dead_code_agent
from sentinel.agents.blast_radius import run_blast_radius_agent


class SentinelState(TypedDict):
    diff: str
    call_graph: dict
    edited_functions: list[str]
    readability: list[str]
    dead_code: list[str]
    blast_radius: list[str]


def _readability_node(state: SentinelState) -> SentinelState:
    results = run_readability_agent(state["diff"])
    return {**state, "readability": results}


def _dead_code_node(state: SentinelState) -> SentinelState:
    results = run_dead_code_agent(state["diff"])
    return {**state, "dead_code": results}


def _blast_radius_node(state: SentinelState) -> SentinelState:
    results = run_blast_radius_agent(
        edited_functions=state["edited_functions"],
        call_graph=state["call_graph"],
    )
    return {**state, "blast_radius": results}


def _build_graph():
    graph = StateGraph(SentinelState)

    graph.add_node("readability", _readability_node)
    graph.add_node("dead_code", _dead_code_node)
    graph.add_node("blast_radius", _blast_radius_node)

    # All three run from START in parallel (LangGraph fans out from __start__)
    graph.set_entry_point("readability")
    graph.add_edge("readability", END)

    # Note: for true parallelism in v2, use Send() API.
    # For MVP: sequential is fine, output is identical.
    # TODO v2: fan out with Send() for concurrent execution
    graph.set_entry_point("readability")
    graph.add_edge("readability", "dead_code")
    graph.add_edge("dead_code", "blast_radius")
    graph.add_edge("blast_radius", END)

    return graph.compile()


_graph = _build_graph()


def run_agents(diff: str, call_graph: dict, edited_functions: list[str]) -> dict:
    """Run all three agents and return their results."""
    initial_state: SentinelState = {
        "diff": diff,
        "call_graph": call_graph,
        "edited_functions": edited_functions,
        "readability": [],
        "dead_code": [],
        "blast_radius": [],
    }
    final_state = _graph.invoke(initial_state)
    return {
        "readability": final_state["readability"],
        "dead_code": final_state["dead_code"],
        "blast_radius": final_state["blast_radius"],
    }
