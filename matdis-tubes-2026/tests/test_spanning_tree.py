import pytest

import algorithms  # noqa: F401 - triggers registry population
from algorithms.registry import AlgorithmRegistry
from algorithms.spanning_tree import StaticKruskal, SubtreeRepair
from cases.scenario_loader import ScenarioLoader
from config.settings import CASES_DIR
from core.graph_model import SpatialGraphModel
from core.simulation_runner import SimulationRunner

KBP_26_EDGES = [
    (0, 1, 465.0),
    (1, 2, 210.0),
    (0, 8, 555.0),
    (1, 7, 530.0),
    (2, 3, 305.0),
    (3, 5, 200.0),
    (3, 4, 260.0),
    (4, 6, 115.0),
    (5, 6, 355.0),
    (7, 6, 140.0),
    (7, 9, 95.0),
    (8, 10, 265.0),
    (8, 16, 240.0),
    (9, 10, 210.0),
    (10, 12, 245.0),
    (12, 15, 235.0),
    (9, 11, 210.0),
    (10, 11, 145.0),
    (11, 13, 355.0),
    (12, 13, 265.0),
    (9, 14, 505.0),
    (10, 16, 190.0),
    (16, 17, 130.0),
    (17, 18, 225.0),
    (18, 19, 125.0),
    (19, 20, 80.0),
    (16, 21, 310.0),
    (17, 22, 310.0),
    (18, 23, 310.0),
    (19, 24, 315.0),
    (20, 25, 390.0),
    (15, 21, 170.0),
    (21, 22, 125.0),
    (22, 23, 220.0),
    (23, 24, 130.0),
    (24, 25, 145.0),
]


def _build_kbp_26_model() -> SpatialGraphModel:
    model = SpatialGraphModel()
    for node_id in range(26):
        model.add_spatial_node(node_id, label=f"N{node_id:02d}", pos=(float(node_id), 0.0))
    for u, v, w in KBP_26_EDGES:
        model.add_weighted_edge(u, v, w)
    return model


def _canonical_edge_set(edges):
    return {(min(u, v), max(u, v), float(w)) for u, v, w in edges}


def test_spanning_tree_registry_registration():
    assert AlgorithmRegistry.resolve("static_kruskal") == "static_kruskal"
    assert AlgorithmRegistry.resolve("spanning_tree") == "static_kruskal"
    assert AlgorithmRegistry.resolve("subtree_repair") == "subtree_repair"

    model = _build_kbp_26_model()
    assert isinstance(AlgorithmRegistry.create("spanning_tree", model), StaticKruskal)
    assert isinstance(AlgorithmRegistry.create("subtree_repair", model), SubtreeRepair)


@pytest.mark.parametrize("algo_key", ["static_kruskal", "subtree_repair"])
def test_spanning_tree_on_case_28_yaml(algo_key: str):
    yaml_path = CASES_DIR / "case_28_siskamling_portal.yaml"
    loader = ScenarioLoader(yaml_path)
    model = loader.build_graph_model()
    plan = loader.get_execution_plan()
    metadata = loader.get_metadata()

    solver = AlgorithmRegistry.create(algo_key, model)
    result = SimulationRunner(solver=solver, plan=plan, metadata=metadata).execute()

    # Kondisi Siang (26 node, 36 sisi): 25 sisi MST = 5175.0 m
    assert result.initial_cost == pytest.approx(5175.0)
    assert len(result.initial_path) == 25
    # Event 1: Gate 1 (4,6=115m) tutup -> diganti (5,6=355m) => 5415.0 m
    # Event 2: Gate 2 (8,16=240m) tutup -> diganti (8,10=265m) => 5440.0 m
    assert len(result.reroutes) == 2
    assert result.reroutes[0].cost == pytest.approx(5415.0)
    assert result.reroutes[1].cost == pytest.approx(5440.0)
    assert solver.step_count == len(solver.delta_logs) > 0


def test_kbp_26node_kruskal_vs_subtree_repair_equivalence_and_steps():
    kruskal = StaticKruskal(_build_kbp_26_model())
    repair = SubtreeRepair(_build_kbp_26_model())

    mst_k_day, cost_k_day = kruskal.run(0, 25)
    mst_r_day, cost_r_day = repair.run(0, 25)

    assert cost_k_day == pytest.approx(5175.0)
    assert cost_r_day == pytest.approx(5175.0)
    assert len(mst_k_day) == 25
    assert _canonical_edge_set(mst_k_day) == _canonical_edge_set(mst_r_day)

    events = [
        {"edge": (4, 6), "new_weight": float("inf"), "start": 0, "goal": 25},
        {"edge": (16, 8), "new_weight": float("inf"), "start": 0, "goal": 25},  # reversed endpoint order
    ]
    for ev in events:
        mst_k_night, cost_k_night = kruskal.handle_dynamic_event(ev)
        mst_r_night, cost_r_night = repair.handle_dynamic_event(ev)

    assert cost_k_night == pytest.approx(5440.0)
    assert cost_r_night == pytest.approx(5440.0)
    assert len(mst_r_night) == 25
    assert _canonical_edge_set(mst_k_night) == _canonical_edge_set(mst_r_night)

    edge_pairs = {(u, v) for u, v, _ in mst_r_night}
    assert (4, 6) not in edge_pairs
    assert (8, 16) not in edge_pairs
    assert (5, 6) in edge_pairs
    assert (8, 10) in edge_pairs

    # SubtreeRepair avoids full recomputation steps on dynamic events
    assert repair.step_count < kruskal.step_count


def test_subtree_repair_non_mst_reopen_and_bridge_cases():
    # 1) Closing a non-MST edge should require no repair
    kruskal = StaticKruskal(_build_kbp_26_model())
    repair = SubtreeRepair(_build_kbp_26_model())
    kruskal.run()
    repair.run()

    mst_k, cost_k = kruskal.handle_dynamic_event({"edge": (0, 8), "new_weight": float("inf")})
    mst_r, cost_r = repair.handle_dynamic_event({"edge": (0, 8), "new_weight": float("inf")})
    assert cost_r == pytest.approx(5175.0)
    assert cost_k == pytest.approx(cost_r)
    assert repair.delta_logs[-1]["event_type"] == "NO_REPAIR_NEEDED"
    assert _canonical_edge_set(mst_k) == _canonical_edge_set(mst_r)

    # 2) Close Gate 1 & Gate 2, then reopen Gate 1 -> cycle swap restores daytime cost for Gate 1
    kruskal.handle_dynamic_event({"edge": (4, 6), "new_weight": float("inf")})
    repair.handle_dynamic_event({"edge": (4, 6), "new_weight": float("inf")})
    mst_k, cost_k = kruskal.handle_dynamic_event({"edge": (4, 6), "new_weight": 115.0})
    mst_r, cost_r = repair.handle_dynamic_event({"edge": (4, 6), "new_weight": 115.0})
    assert cost_r == pytest.approx(5175.0)
    assert cost_k == pytest.approx(cost_r)
    assert repair.delta_logs[-1]["event_type"] == "CYCLE_SWAP_REPAIRED"
    assert _canonical_edge_set(mst_k) == _canonical_edge_set(mst_r)

    # 3) Closing bridge (9, 14) isolates N14 (cul-de-sac) cleanly without crashing
    mst_k, cost_k = kruskal.handle_dynamic_event({"edge": (9, 14), "new_weight": float("inf")})
    mst_r, cost_r = repair.handle_dynamic_event({"edge": (9, 14), "new_weight": float("inf")})
    assert len(mst_r) == 24
    assert cost_r == pytest.approx(5175.0 - 505.0)
    assert cost_k == pytest.approx(cost_r)
    assert repair.delta_logs[-1]["event_type"] == "SUBTREE_DISCONNECTED"
    assert _canonical_edge_set(mst_k) == _canonical_edge_set(mst_r)
