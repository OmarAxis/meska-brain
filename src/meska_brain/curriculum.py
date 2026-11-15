"""Curriculum map: concepts and "needs this first" links, loaded from packs/<pack_id>/pack.yaml.

We graph the school's curriculum; we never change it."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

import networkx as nx
import yaml

from .config import get_settings

SKILL_KINDS = ("thinking", "disposition")  # a disposition describes character, never a struggle finding
_CACHE: dict[tuple[str, Path], Pack] = {}


@dataclass(frozen=True)
class Concept:
    id: str
    label: dict[str, str]
    strand: str
    grade: int
    requires: tuple[str, ...]
    skills: tuple[str, ...]


@dataclass
class Pack:
    id: str
    name: str
    subject: str
    grades: tuple[int, int]
    strands: dict[str, dict[str, str]]
    skills: dict[str, dict[str, str]]
    approaches: dict[str, dict[str, str]]
    concepts: dict[str, Concept]
    graph: nx.DiGraph  # edge prerequisite -> concept
    skill_kinds: dict[str, str] = field(default_factory=dict)  # skill id -> "thinking" | "disposition"
    subjects: dict[str, dict[str, str]] = field(default_factory=dict)  # subject id -> labels
    strand_subject: dict[str, str] = field(default_factory=dict)       # strand id -> subject id

    def label(self, any_id: str, lang: str = "en") -> str:
        """Label of a concept, strand, skill or approach; falls back to English, then the id."""
        if any_id in self.concepts:
            labels = self.concepts[any_id].label
        else:
            labels = (self.strands.get(any_id) or self.skills.get(any_id) or self.approaches.get(any_id)
                      or self.subjects.get(any_id) or {})
        return labels.get(lang) or labels.get("en") or any_id

    def prerequisites(self, concept_id: str) -> list[str]:
        """Concepts this one directly needs first."""
        return sorted(self.graph.predecessors(concept_id))

    def ancestors(self, concept_id: str) -> list[str]:
        """Every concept needed before this one, nearest first (breadth-first)."""
        seen: list[str] = []
        queue = deque(self.prerequisites(concept_id))
        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.append(current)
            queue.extend(self.prerequisites(current))
        return seen

    def dependents(self, concept_id: str) -> list[str]:
        """Concepts that directly need this one first."""
        return sorted(self.graph.successors(concept_id))


def load_pack(pack_id: str | None = None, packs_dir: Path | None = None) -> Pack:
    """Load and validate a pack. Cached per (pack id, folder)."""
    settings = get_settings()
    pack_id = pack_id or settings.default_pack
    folder = Path(packs_dir or settings.packs_dir).resolve()
    key = (pack_id, folder)
    if key not in _CACHE:
        _CACHE[key] = _read_pack(folder / pack_id / "pack.yaml")
    return _CACHE[key]


def read_pack_data(path: Path) -> dict:
    """Read pack.yaml as plain data. A pack may `include` other packs (one per subject) and add
    cross-subject `links`; the result is one merged pack with every strand tagged with its subject."""
    if not path.exists():
        raise ValueError(f"Curriculum pack not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    own_subject = {"id": data["subject"], "label": data.get("subject_label") or {"en": str(data["subject"]).title()}}
    for strand in data.get("strands") or []:
        strand.setdefault("subject", own_subject["id"])
    data["subjects"] = [own_subject] if data.get("strands") else []
    for key in ("strands", "skills", "approaches", "concepts"):
        data[key] = list(data.get(key) or [])
    for included in data.get("includes") or []:
        part = read_pack_data(path.parent.parent / included / "pack.yaml")
        data["subjects"] += [s for s in part["subjects"] if s["id"] not in {x["id"] for x in data["subjects"]}]
        for key in ("strands", "skills", "approaches"):
            have = {item["id"] for item in data[key]}
            data[key] += [item for item in part[key] if item["id"] not in have]
        clash = {c["id"] for c in data["concepts"]} & {c["id"] for c in part["concepts"]}
        if clash:
            raise ValueError(f"Pack '{data['id']}': concept ids appear in more than one included pack: {sorted(clash)}")
        data["concepts"] += part["concepts"]
    by_id = {c["id"]: c for c in data["concepts"]}
    for link in data.get("links") or []:
        if link["concept"] not in by_id:
            raise ValueError(f"Pack '{data['id']}': link names unknown concept '{link['concept']}'")
        target = by_id[link["concept"]]
        target["requires"] = list(dict.fromkeys(list(target.get("requires") or []) + list(link["requires"])))
    return data


def _read_pack(path: Path) -> Pack:
    """Parse pack.yaml into a Pack, then check it."""
    data = read_pack_data(path)
    concepts = {c["id"]: _concept(c) for c in data.get("concepts", [])}
    pack = Pack(
        id=data["id"],
        name=data["name"],
        subject=data["subject"],
        grades=tuple(data["grades"]),
        strands=_labels(data.get("strands", [])),
        skills=_labels(data.get("skills", [])),
        approaches=_labels(data.get("approaches", [])),
        concepts=concepts,
        graph=_build_graph(concepts),
        skill_kinds={s["id"]: s.get("kind", "thinking") for s in data.get("skills", [])},
        subjects={s["id"]: dict(s["label"]) for s in data["subjects"]},
        strand_subject={s["id"]: s["subject"] for s in data.get("strands", [])},
    )
    _validate(pack)
    return pack


def _concept(raw: dict) -> Concept:
    return Concept(
        id=raw["id"],
        label=dict(raw["label"]),
        strand=raw["strand"],
        grade=int(raw["grade"]),
        requires=tuple(raw.get("requires") or ()),
        skills=tuple(raw.get("skills") or ()),
    )


def _labels(items: list[dict]) -> dict[str, dict[str, str]]:
    """Turn [{id, label}] into {id: label dict}."""
    return {item["id"]: dict(item["label"]) for item in items}


def _build_graph(concepts: dict[str, Concept]) -> nx.DiGraph:
    graph = nx.DiGraph()
    graph.add_nodes_from(concepts)
    for concept in concepts.values():
        for prerequisite in concept.requires:
            graph.add_edge(prerequisite, concept.id)
    return graph


def _validate(pack: Pack) -> None:
    """Every reference must exist, every label needs English, and `requires` must be a DAG."""
    problems = []
    for group in (pack.strands, pack.skills, pack.approaches):
        problems += [f"'{item_id}' has no 'en' label" for item_id, label in group.items() if "en" not in label]
    problems += [f"skill '{sid}' has unknown kind '{kind}'" for sid, kind in pack.skill_kinds.items()
                 if kind not in SKILL_KINDS]
    for concept in pack.concepts.values():
        if "en" not in concept.label:
            problems.append(f"concept '{concept.id}' has no 'en' label")
        if concept.strand not in pack.strands:
            problems.append(f"concept '{concept.id}' uses unknown strand '{concept.strand}'")
        problems += [f"concept '{concept.id}' requires unknown concept '{r}'"
                     for r in concept.requires if r not in pack.concepts]
        problems += [f"concept '{concept.id}' uses unknown skill '{s}'"
                     for s in concept.skills if s not in pack.skills]
    if not problems and not nx.is_directed_acyclic_graph(pack.graph):
        problems.append("concept prerequisites contain a cycle")
    if problems:
        raise ValueError(f"Invalid pack '{pack.id}': " + "; ".join(problems))
