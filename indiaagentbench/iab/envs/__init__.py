from .base import Env, ToolError
from .rail import RailEnv
from .schemes import SchemeEnv

REGISTRY = {
    RailEnv.domain: RailEnv,
    SchemeEnv.domain: SchemeEnv,
}


def make(domain, db):
    return REGISTRY[domain](db)


__all__ = ["Env", "ToolError", "RailEnv", "SchemeEnv", "REGISTRY", "make"]
