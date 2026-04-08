"""
Loads .sentinel.yml from the current working directory into a SentinelConfig
dataclass. Missing keys fall back to sensible defaults.
"""
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AgentsConfig:
    readability: bool = True
    dead_code: bool = True
    blast_radius: bool = True


@dataclass
class SeverityConfig:
    readability: str = "warning"   # warning = print but allow commit
    dead_code: str = "error"       # error   = block commit
    blast_radius: str = "warning"


@dataclass
class IgnoreConfig:
    paths: list[str] = field(default_factory=list)
    functions: list[str] = field(default_factory=list)


@dataclass
class BlastRadiusConfig:
    max_depth: int = 5   # maximum hops to traverse up the call graph


@dataclass
class SentinelConfig:
    agents: AgentsConfig = field(default_factory=AgentsConfig)
    severity: SeverityConfig = field(default_factory=SeverityConfig)
    ignore: IgnoreConfig = field(default_factory=IgnoreConfig)
    blast_radius: BlastRadiusConfig = field(default_factory=BlastRadiusConfig)


def load_config(cwd: Path = Path(".")) -> SentinelConfig:
    """
    Read .sentinel.yml from *cwd*. Returns defaults if the file is absent.
    Partial configs are merged with defaults — only the keys present in the
    file override the defaults.
    """
    config_path = cwd / ".sentinel.yml"
    if not config_path.exists():
        return SentinelConfig()

    raw = yaml.safe_load(config_path.read_text()) or {}

    agents_raw = raw.get("agents", {})
    severity_raw = raw.get("severity", {})
    ignore_raw = raw.get("ignore", {})

    agents = AgentsConfig(
        readability=agents_raw.get("readability", True),
        dead_code=agents_raw.get("dead_code", True),
        blast_radius=agents_raw.get("blast_radius", True),
    )
    severity = SeverityConfig(
        readability=severity_raw.get("readability", "warning"),
        dead_code=severity_raw.get("dead_code", "error"),
        blast_radius=severity_raw.get("blast_radius", "warning"),
    )
    ignore = IgnoreConfig(
        paths=ignore_raw.get("paths", []),
        functions=ignore_raw.get("functions", []),
    )

    blast_radius_raw: dict = raw.get("blast_radius", {})
    blast_radius = BlastRadiusConfig(
        max_depth=blast_radius_raw.get("max_depth", 5),
    )

    return SentinelConfig(agents=agents, severity=severity, ignore=ignore, blast_radius=blast_radius)
