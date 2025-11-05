"""LangGraph-like workflow scaffolding for the AOP MCP."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Dict, List

from src.tools.semantic import SemanticTools
from src.tools.write import WriteTools
from src.services.publish import MediaWikiPublishPlanner, OWLPublishPlanner
from src.services.jobs import JobService


@dataclass
class ToolBinding:
    name: str
    handler: Callable[..., dict]


@dataclass
class WorkflowStep:
    name: str
    tool: str
    description: str


@dataclass
class AgentWorkflow:
    name: str
    steps: List[WorkflowStep]
    tool_map: Dict[str, ToolBinding]

    def run(self, **kwargs) -> dict:
        state = {}
        for step in self.steps:
            binding = self.tool_map[step.tool]
            result = binding.handler(**kwargs)
            state[step.name] = result
        return state


class WorkflowFactory:
    def __init__(
        self,
        *,
        semantic_tools: SemanticTools,
        write_tools: WriteTools,
        job_service: JobService,
    ) -> None:
        self._semantic = semantic_tools
        self._write = write_tools
        self._jobs = job_service
        self._mw_planner = MediaWikiPublishPlanner()
        self._owl_planner = OWLPublishPlanner()

    def build_publish_workflow(self) -> AgentWorkflow:
        tool_map = {
            "create_plan": ToolBinding(
                name="create_plan",
                handler=lambda **ctx: {
                    "mediawiki": self._mw_planner.build_plan(ctx["draft"], ctx["version"]).to_dict(),
                    "owl": self._owl_planner.build_delta(ctx["draft"], ctx["version"]).to_dict(),
                },
            ),
            "enqueue_plan": ToolBinding(
                name="enqueue_plan",
                handler=lambda **ctx: self._jobs.submit(ctx["job"]).job_id,
            ),
        }
        steps = [
            WorkflowStep(name="plan", tool="create_plan", description="Generate dry-run publish artifacts"),
            WorkflowStep(name="enqueue", tool="enqueue_plan", description="Queue follow-up job for execution"),
        ]
        return AgentWorkflow(name="publish_workflow", steps=steps, tool_map=tool_map)
