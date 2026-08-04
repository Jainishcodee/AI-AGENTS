"""Environment base: a seeded, deterministic, tool-callable state machine.

Every domain is a mock service with its own database. Nothing here touches a
real network endpoint -- that is deliberate. Hitting live IRCTC/UPI/DigiLocker
would make the benchmark unreproducible, unrunnable by other researchers, and
legally radioactive. Mock services with honest state machines are what
tau-bench-style agent evaluation actually requires.

Tools return an `{"error": ...}` dict rather than raising, because that is how
real tool APIs behave: the agent gets to see the failure and decide what to do.
An agent that plows on after an error is exhibiting exactly the state-tracking
failure we want to measure, not crashing the harness.
"""
from copy import deepcopy


class ToolError(Exception):
    """Raised inside a tool to signal a clean, agent-visible failure."""


class Env:
    """A domain instance bound to one seeded database.

    Subclasses declare:
      domain  -- short name, matches the tasks file
      TOOLS   -- list of JSON-schema tool specs handed to the model
      WRITES  -- names of tools that mutate state (used by verifiers)
    and implement one `t_<name>` method per tool.
    """

    domain = "base"
    TOOLS = []
    WRITES = frozenset()

    def __init__(self, db):
        # deepcopy so one seeded db can spawn many independent task instances
        # without leaking state between trajectories.
        self.db = deepcopy(db)
        self.actions = []

    # -- introspection -----------------------------------------------------

    def tools(self):
        return deepcopy(self.TOOLS)

    def tool_names(self):
        return [t["name"] for t in self.TOOLS]

    # -- dispatch ----------------------------------------------------------

    def call(self, name, args):
        """Run one tool call, log it, and return a JSON-serialisable result.

        The log entry is the raw material for both scoring and the H2 analysis
        (right tool + wrong entity => slot corruption), so it records the
        arguments exactly as the model supplied them.
        """
        args = args or {}
        fn = getattr(self, f"t_{name}", None)

        if fn is None or name not in self.tool_names():
            result, ok = {"error": f"unknown tool: {name}"}, False
        else:
            try:
                result, ok = fn(**args), True
            except ToolError as e:
                result, ok = {"error": str(e)}, False
            except TypeError as e:
                # wrong/missing arguments -- a slot error, not a harness bug
                result, ok = {"error": f"bad arguments for {name}: {e}"}, False

        self.actions.append({
            "tool": name,
            "args": args,
            "ok": ok,
            "write": name in self.WRITES,
            "result": result,
        })
        return result

    # -- helpers for verifiers --------------------------------------------

    def writes(self):
        """Successful state-mutating calls, in order."""
        return [a for a in self.actions if a["write"] and a["ok"]]

    def called(self, tool):
        return [a for a in self.actions if a["tool"] == tool and a["ok"]]
