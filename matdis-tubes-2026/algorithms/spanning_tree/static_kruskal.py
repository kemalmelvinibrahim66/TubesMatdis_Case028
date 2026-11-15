import math
from typing import Any, Dict, List, Optional, Tuple

from algorithms.registry import AlgorithmRegistry
from core.base_algorithm import BaseGraphAlgorithm
from core.graph_model import SpatialGraphModel


class StaticKruskal(BaseGraphAlgorithm):
    """Algoritma Baseline Minimum Spanning Tree (Static Kruskal + Union-Find)."""

    SUPPORTED_EVENT_TYPES = frozenset({"DYNAMIC_EDGE_WEIGHT"})

    def __init__(self, model: SpatialGraphModel):
        super().__init__(model)
        self.parent: Dict[int, int] = {}
        self.rank: Dict[int, int] = {}
        self.mst_edges: List[Tuple[int, int, float]] = []
        self.total_cost: float = 0.0

    def _find(self, i: int) -> int:
        if self.parent[i] == i:
            return i
        self.parent[i] = self._find(self.parent[i])
        return self.parent[i]

    def _union(self, i: int, j: int) -> bool:
        root_i = self._find(i)
        root_j = self._find(j)
        if root_i == root_j:
            return False

        if self.rank[root_i] < self.rank[root_j]:
            self.parent[root_i] = root_j
        elif self.rank[root_i] > self.rank[root_j]:
            self.parent[root_j] = root_i
        else:
            self.parent[root_j] = root_i
            self.rank[root_i] += 1
        return True

    @staticmethod
    def _canonical_edge(u: int, v: int) -> Tuple[int, int]:
        return (u, v) if u <= v else (v, u)

    def _extract_undirected_edges(self) -> List[Tuple[float, int, int]]:
        """Mengambil seluruh sisi tak berarah aktif (weight terhingga) secara deterministik."""
        edge_map: Dict[Tuple[int, int], float] = {}
        for u, v, data in self.graph.edges(data=True):
            if u == v:
                continue
            weight = float(data.get("weight", 1.0))
            if math.isinf(weight):
                continue
            key = self._canonical_edge(u, v)
            if key not in edge_map or weight < edge_map[key]:
                edge_map[key] = weight

        edges = [(weight, u, v) for (u, v), weight in edge_map.items()]
        edges.sort(key=lambda item: (item[0], item[1], item[2]))
        return edges

    def _update_undirected_weight(self, u: int, v: int, new_weight: float) -> float:
        """Memperbarui bobot edge pada DiGraph secara simetris bila dua arah ada."""
        has_uv = self.graph.has_edge(u, v)
        has_vu = self.graph.has_edge(v, u)
        if not has_uv and not has_vu:
            raise KeyError(f"Edge ({u}, {v}) tidak ditemukan dalam graf.")

        old_weight = float(
            self.graph[u][v].get("weight", 1.0)
            if has_uv
            else self.graph[v][u].get("weight", 1.0)
        )
        if has_uv:
            self.graph[u][v]["weight"] = new_weight
        if has_vu:
            self.graph[v][u]["weight"] = new_weight
        return old_weight

    def run(
        self, start_node: Optional[int] = None, goal_node: Optional[int] = None
    ) -> Tuple[List[Tuple[int, int, float]], float]:
        self.mst_edges = []
        self.total_cost = 0.0
        self.parent = {node: node for node in self.graph.nodes()}
        self.rank = {node: 0 for node in self.graph.nodes()}

        edges = self._extract_undirected_edges()

        self.log_step(
            event_type="INITIALIZATION",
            state_mutations={
                "total_nodes": len(self.parent),
                "total_edges": len(edges),
                "sorted_edges": [[u, v, w] for w, u, v in edges],
            },
        )

        for weight, u, v in edges:
            if self._union(u, v):
                self.mst_edges.append((u, v, weight))
                self.total_cost += weight

                self.log_step(
                    event_type="EDGE_ADDED",
                    state_mutations={
                        "added_edge": [u, v],
                        "weight": weight,
                        "current_mst_count": len(self.mst_edges),
                        "total_cost": self.total_cost,
                    },
                )

        components = len({self._find(node) for node in self.parent}) if self.parent else 0
        self.log_step(
            event_type="MST_COMPLETE",
            state_mutations={
                "mst_edge_count": len(self.mst_edges),
                "total_cost": self.total_cost,
                "components": components,
                "is_connected": components <= 1,
            },
        )

        return list(self.mst_edges), self.total_cost

    def handle_dynamic_event(
        self, event_data: Dict[str, Any]
    ) -> Tuple[List[Tuple[int, int, float]], float]:
        edge = tuple(event_data["edge"])
        new_weight = float(event_data["new_weight"])
        old_weight = self._update_undirected_weight(edge[0], edge[1], new_weight)

        self.log_step(
            event_type="UPDATE_WEIGHT_EVENT",
            state_mutations={
                "target_edge": [edge[0], edge[1]],
                "old_weight": old_weight,
                "new_weight": new_weight,
            },
        )

        return self.run(event_data.get("start"), event_data.get("goal"))


AlgorithmRegistry.register("static_kruskal", StaticKruskal)
AlgorithmRegistry.register_alias("spanning_tree", "static_kruskal")
