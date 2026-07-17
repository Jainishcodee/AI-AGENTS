"""Tiny registry of agents — name -> instance, with fuzzy `find()`."""
from typing import Dict, List, Optional

from agents.base import Agent


class AgentRegistry:
    def __init__(self):
        self.agents: Dict[str, Agent] = {}

    def register(self, agent: Agent) -> None:
        self.agents[agent.name.lower()] = agent

    def list(self) -> List[Agent]:
        return list(self.agents.values())

    def find(self, name_fragment: str) -> Optional[Agent]:
        if not name_fragment:
            return None
        n = name_fragment.lower().strip()
        if n in self.agents:
            return self.agents[n]
        for k, a in self.agents.items():
            if n in k or k in n:
                return a
        return None
