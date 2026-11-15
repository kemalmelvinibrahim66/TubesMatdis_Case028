from collections import deque
import math
from typing import Any, Dict, List, Optional, Set, Tuple

from algorithms.registry import AlgorithmRegistry
from algorithms.spanning_tree.static_kruskal import StaticKruskal
from core.graph_model import SpatialGraphModel


class SubtreeRepair(StaticKruskal):
    """Dynamic MST menggunakan Incremental Cut/Cycle-Property Subtree Repair."""

    def __init__(self, model: SpatialGraphModel):
        super().__init__(model)
        self.tree_adj: Dict[int, Dict[int, float]] = {}
        self._initialized: bool = False

    def _sync_tree_adj(self) -> None:
        self.tree_adj = {node: {} for node in self.graph.nodes()}
        for u, v, weight in self.mst_edges:
            self.tree_adj.setdefault(u, {})[v] = weight
            self.tree_adj.setdefault(v, {})[u] = weight

    def _add_tree_edge(self, u: int, v: int, weight: float) -> None:
        a, b = self._canonical_edge(u, v)
        self.tree_adj.setdefault(a, {})[b] = weight
        self.tree_adj.setdefault(b, {})[a] = weight
        self.mst_edges.append((a, b, weight))
        self.mst_edges.sort(key=lambda item: (item[2], item[0], item[1]))
        self.total_cost += weight

    def _remove_tree_edge(self, u: int, v: int) -> float:
        a, b = self._canonical_edge(u, v)
        removed_weight = self.tree_adj[a].pop(b)
        self.tree_adj[b].pop(a)
        self.mst_edges = [
            (eu, ev, ew) for eu, ev, ew in self.mst_edges if not (eu == a and ev == b)
        ]
        self.total_cost -= removed_weight
        return removed_weight

    def _collect_subtree(self, root: int) -> Set[int]:
        visited: Set[int] = {root}
        queue: deque[int] = deque([root])
        while queue:
            curr = queue.popleft()
            for nbr in self.tree_adj.get(curr, {}):
                if nbr not in visited:
                    visited.add(nbr)
                    queue.append(nbr)
        return visited

    def _find_best_crossing_edge(
        self, subtree_a: Set[int], subtree_b: Set[int]
    ) -> Optional[Tuple[int, int, float]]:
        best: Optional[Tuple[float, int, int]] = None
        for u, v, data in self.graph.edges(data=True):
            if u == v:
                continue
            weight = float(data.get("weight", 1.0))
            if math.isinf(weight):
                continue
            crosses = (u in subtree_a and v in subtree_b) or (
                u in subtree_b and v in subtree_a
            )
            if not crosses:
                continue
            a, b = self._canonical_edge(u, v)
            candidate = (weight, a, b)
            if best is None or candidate < best:
                best = candidate

        if best is None:
            return None
        return best[1], best[2], best[0]

    def _find_tree_path(self, start: int, target: int) -> Optional[List[Tuple[int, int, float]]]:
        """Mencari jalur unik antara dua simpul di MST saat ini (BFS)."""
        parent: Dict[int, Optional[Tuple[int, float]]] = {start: None}
        queue: deque[int] = deque([start])

        while queue:
            curr = queue.popleft()
            if curr == target:
                break
            for nbr, w in self.tree_adj.get(curr, {}).items():
                if nbr not in parent:
                    parent[nbr] = (curr, w)
                    queue.append(nbr)

        if target not in parent:
            return None

        path_edges: List[Tuple[int, int, float]] = []
        node = target
        while parent[node] is not None:
            prev, w = parent[node]  # type: ignore[misc]
            a, b = self._canonical_edge(prev, node)
            path_edges.append((a, b, w))
            node = prev
        return path_edges

    def run(
        self, start_node: Optional[int] = None, goal_node: Optional[int] = None
    ) -> Tuple[List[Tuple[int, int, float]], float]:
        mst_edges, total_cost = super().run(start_node, goal_node)
        self._sync_tree_adj()
        self._initialized = True
        return mst_edges, total_cost

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

        if not self._initialized:
            return self.run(event_data.get("start"), event_data.get("goal"))

        a, b = self._canonical_edge(edge[0], edge[1])
        in_mst = b in self.tree_adj.get(a, {})

        if new_weight >= old_weight:
            return self._handle_weight_increase_or_removal(a, b, old_weight, in_mst)
        return self._handle_weight_decrease(a, b, old_weight, new_weight, in_mst)

    def _handle_weight_increase_or_removal(
        self, a: int, b: int, old_weight: float, in_mst: bool
    ) -> Tuple[List[Tuple[int, int, float]], float]:
        if not in_mst:
            self.log_step(
                event_type="NO_REPAIR_NEEDED",
                state_mutations={
                    "reason": "target_edge_not_in_mst",
                    "target_edge": [a, b],
                    "current_mst_count": len(self.mst_edges),
                    "total_cost": self.total_cost,
                },
            )
            return list(self.mst_edges), self.total_cost

        self._remove_tree_edge(a, b)
        subtree_a = self._collect_subtree(a)
        subtree_b = self._collect_subtree(b)

        self.log_step(
            event_type="SUBTREE_SPLIT",
            state_mutations={
                "removed_edge": [a, b],
                "old_weight": old_weight,
                "subtree_a_size": len(subtree_a),
                "subtree_b_size": len(subtree_b),
                "subtree_a_nodes": sorted(subtree_a),
                "subtree_b_nodes": sorted(subtree_b),
            },
        )

        replacement = self._find_best_crossing_edge(subtree_a, subtree_b)
        if replacement is not None:
            rep_u, rep_v, rep_w = replacement
            self._add_tree_edge(rep_u, rep_v, rep_w)
            self.log_step(
                event_type="SUBTREE_REPAIRED",
                state_mutations={
                    "replacement_edge": [rep_u, rep_v],
                    "replacement_weight": rep_w,
                    "delta_cost": rep_w - old_weight,
                    "current_mst_count": len(self.mst_edges),
                    "total_cost": self.total_cost,
                },
            )
        else:
            self.log_step(
                event_type="SUBTREE_DISCONNECTED",
                state_mutations={
                    "removed_edge": [a, b],
                    "current_mst_count": len(self.mst_edges),
                    "total_cost": self.total_cost,
                },
            )

        return list(self.mst_edges), self.total_cost

    def _handle_weight_decrease(
        self,
        a: int,
        b: int,
        old_weight: float,
        new_weight: float,
        in_mst: bool,
    ) -> Tuple[List[Tuple[int, int, float]], float]:
        if in_mst:
            self.tree_adj[a][b] = new_weight
            self.tree_adj[b][a] = new_weight
            self.mst_edges = [
                (eu, ev, new_weight if (eu == a and ev == b) else ew)
                for eu, ev, ew in self.mst_edges
            ]
            self.mst_edges.sort(key=lambda item: (item[2], item[0], item[1]))
            self.total_cost += new_weight - old_weight
            self.log_step(
                event_type="EDGE_WEIGHT_REDUCED_IN_MST",
                state_mutations={
                    "target_edge": [a, b],
                    "delta_cost": new_weight - old_weight,
                    "total_cost": self.total_cost,
                },
            )
            return list(self.mst_edges), self.total_cost

        if math.isinf(new_weight):
            self.log_step(
                event_type="NO_REPAIR_NEEDED",
                state_mutations={
                    "reason": "edge_still_infinite",
                    "target_edge": [a, b],
                    "total_cost": self.total_cost,
                },
            )
            return list(self.mst_edges), self.total_cost

        path_edges = self._find_tree_path(a, b)
        if path_edges is None:
            self._add_tree_edge(a, b, new_weight)
            self.log_step(
                event_type="SUBTREE_MERGED",
                state_mutations={
                    "added_edge": [a, b],
                    "weight": new_weight,
                    "current_mst_count": len(self.mst_edges),
                    "total_cost": self.total_cost,
                },
            )
            return list(self.mst_edges), self.total_cost

        max_u, max_v, max_w = max(path_edges, key=lambda item: (item[2], item[0], item[1]))
        if (new_weight, a, b) < (max_w, max_u, max_v):
            self._remove_tree_edge(max_u, max_v)
            self._add_tree_edge(a, b, new_weight)
            self.log_step(
                event_type="CYCLE_SWAP_REPAIRED",
                state_mutations={
                    "removed_edge": [max_u, max_v],
                    "removed_weight": max_w,
                    "added_edge": [a, b],
                    "added_weight": new_weight,
                    "delta_cost": new_weight - max_w,
                    "total_cost": self.total_cost,
                },
            )
        else:
            self.log_step(
                event_type="NO_REPAIR_NEEDED",
                state_mutations={
                    "reason": "edge_not_cheaper_than_cycle_max",
                    "target_edge": [a, b],
                    "total_cost": self.total_cost,
                },
            )

        return list(self.mst_edges), self.total_cost


AlgorithmRegistry.register("subtree_repair", SubtreeRepair)
