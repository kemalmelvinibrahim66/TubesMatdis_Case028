import argparse
from pathlib import Path
import random
import statistics
import time
from typing import Dict, List, Tuple

import algorithms  # noqa: F401 - memastikan seluruh algoritma terdaftar di registry
from algorithms.registry import AlgorithmRegistry
from cases.scenario_loader import ScenarioLoader
from config.settings import CASES_DIR
from core.graph_model import SpatialGraphModel
from core.simulation_runner import SimulationRunner

DEFAULT_CASE_28 = CASES_DIR / "case_28_siskamling_portal.yaml"


def _canonical_edge_set(edges: List[Tuple[int, int, float]]):
    return {(min(u, v), max(u, v), float(w)) for u, v, w in edges}


def _run_once(yaml_path: Path, algo_key: str):
    loader = ScenarioLoader(yaml_path)
    metadata = loader.get_metadata()
    plan = loader.get_execution_plan()
    model = loader.build_graph_model()

    solver = AlgorithmRegistry.create(algo_key, model)
    result = SimulationRunner(solver=solver, plan=plan, metadata=metadata).execute()
    return solver, result, metadata


def _measure_repeated(yaml_path: Path, algo_key: str, repeats: int) -> Tuple[float, float]:
    loader = ScenarioLoader(yaml_path)
    plan = loader.get_execution_plan()
    metadata = loader.get_metadata()

    init_samples = []
    event_samples = []
    for _ in range(repeats):
        model = loader.build_graph_model()
        solver = AlgorithmRegistry.create(algo_key, model)
        res = SimulationRunner(solver=solver, plan=plan, metadata=metadata).execute()
        init_samples.append(res.initial_elapsed_ms)
        event_samples.append(sum(r.elapsed_ms for r in res.reroutes))

    return statistics.mean(init_samples), statistics.mean(event_samples)


def _build_grid_benchmark_graph(rows: int, cols: int, seed: int = 42) -> Tuple[SpatialGraphModel, int]:
    rng = random.Random(seed)
    model = SpatialGraphModel()
    total_nodes = rows * cols
    for r in range(rows):
        for c in range(cols):
            nid = r * cols + c
            model.add_spatial_node(nid, label=f"N{nid}", pos=(float(c), float(r)))

    for r in range(rows):
        for c in range(cols):
            u = r * cols + c
            if c + 1 < cols:
                model.add_weighted_edge(u, u + 1, float(rng.randint(50, 300)))
            if r + 1 < rows:
                model.add_weighted_edge(u, u + cols, float(rng.randint(50, 300)))
            if r + 1 < rows and c + 1 < cols:
                model.add_weighted_edge(u, u + cols + 1, float(rng.randint(150, 450)))
    return model, total_nodes


def _clone_model(model: SpatialGraphModel) -> SpatialGraphModel:
    cloned = SpatialGraphModel()
    for n, d in model.nx_graph.nodes(data=True):
        cloned.add_spatial_node(n, label=d.get("label", ""), pos=d.get("pos", (0.0, 0.0)))
    for u, v, d in model.nx_graph.edges(data=True):
        cloned.add_weighted_edge(u, v, float(d.get("weight", 1.0)))
    return cloned


def run_scalability_comparison(event_repeats: int = 10) -> None:
    grid_configs = [(5, 5), (10, 10), (16, 16), (22, 23)]  # ~25, 100, 256, 506 nodes

    print("\n=== UJI SKALABILITAS: PENUTUPAN SISI MST VS NON-MST ===")
    print(
        f" {'Nodes':>6} {'Edges':>6} | {'Kruskal Steps':>13} {'Subtree Steps':>13} | "
        f"{'Kruskal Ev(ms)':>14} {'Subtree Ev(ms)':>14} {'Speedup':>8} | {'MST Sama?':>9}"
    )
    print(" " + "-" * 100)

    for rows, cols in grid_configs:
        base_model, n_nodes = _build_grid_benchmark_graph(rows, cols)
        n_edges = base_model.nx_graph.number_of_edges()

        # Tentukan sample sisi MST & non-MST dari run awal
        probe = AlgorithmRegistry.create("static_kruskal", _clone_model(base_model))
        mst_init, _ = probe.run(0, n_nodes - 1)
        mst_pairs = {(min(u, v), max(u, v)) for u, v, _ in mst_init}
        non_mst = [
            (u, v)
            for u, v in base_model.nx_graph.edges()
            if (min(u, v), max(u, v)) not in mst_pairs
        ]

        # Uji 5 event tutup sisi MST + 5 event tutup sisi non-MST
        test_edges = [(u, v) for u, v, _ in mst_init[:5]] + non_mst[:5]

        k_times = []
        s_times = []
        k_steps = 0
        s_steps = 0
        all_equal = True

        for _ in range(event_repeats):
            mk = _clone_model(base_model)
            ms = _clone_model(base_model)
            sk = AlgorithmRegistry.create("static_kruskal", mk)
            ss = AlgorithmRegistry.create("subtree_repair", ms)
            sk.run(0, n_nodes - 1)
            ss.run(0, n_nodes - 1)

            tk0 = time.perf_counter()
            for u, v in test_edges:
                mk_edges, ck = sk.handle_dynamic_event({"edge": (u, v), "new_weight": float("inf")})
            k_times.append((time.perf_counter() - tk0) * 1000)

            ts0 = time.perf_counter()
            for u, v in test_edges:
                ms_edges, cs = ss.handle_dynamic_event({"edge": (u, v), "new_weight": float("inf")})
            s_times.append((time.perf_counter() - ts0) * 1000)

            k_steps = sk.step_count
            s_steps = ss.step_count
            if abs(ck - cs) > 1e-6 or _canonical_edge_set(mk_edges) != _canonical_edge_set(ms_edges):
                all_equal = False

        mean_k = statistics.mean(k_times)
        mean_s = statistics.mean(s_times)
        speedup = mean_k / mean_s if mean_s > 0 else float("inf")

        print(
            f" {n_nodes:>6} {n_edges:>6} | {k_steps:>13} {s_steps:>13} | "
            f"{mean_k:>14.4f} {mean_s:>14.4f} {speedup:>7.2f}x | {str(all_equal):>9}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="scripts.compare_spanning_tree",
        description="Bandingkan StaticKruskal vs SubtreeRepair pada skenario YAML dan uji skalabilitas.",
    )
    parser.add_argument(
        "scenario",
        nargs="?",
        default=str(DEFAULT_CASE_28),
        help="Path YAML skenario MST (default: case_28_siskamling_portal.yaml).",
    )
    parser.add_argument(
        "--repeats",
        type=int,
        default=300,
        help="Jumlah pengulangan pengukuran waktu untuk rata-rata yang stabil (default: 300).",
    )
    args = parser.parse_args()

    yaml_path = Path(args.scenario)
    solver_k, res_k, meta_k = _run_once(yaml_path, "static_kruskal")
    solver_s, res_s, meta_s = _run_once(yaml_path, "subtree_repair")

    init_k_ms, event_k_ms = _measure_repeated(yaml_path, "static_kruskal", args.repeats)
    init_s_ms, event_s_ms = _measure_repeated(yaml_path, "subtree_repair", args.repeats)

    out_k = solver_k.export_trace_json(
        f"compare_{meta_k['case_id']}_static_kruskal.json",
        metadata={**meta_k, "algorithm": "StaticKruskal"},
    )
    out_s = solver_s.export_trace_json(
        f"compare_{meta_s['case_id']}_subtree_repair.json",
        metadata={**meta_s, "algorithm": "SubtreeRepair"},
    )

    day_k = res_k.initial_cost
    day_s = res_s.initial_cost
    night_k = res_k.reroutes[-1].cost if res_k.reroutes else day_k
    night_s = res_s.reroutes[-1].cost if res_s.reroutes else day_s

    day_set_k = _canonical_edge_set(res_k.initial_path)
    day_set_s = _canonical_edge_set(res_s.initial_path)
    night_set_k = _canonical_edge_set(res_k.reroutes[-1].path if res_k.reroutes else res_k.initial_path)
    night_set_s = _canonical_edge_set(res_s.reroutes[-1].path if res_s.reroutes else res_s.initial_path)

    removed = sorted((day_set_s - night_set_s), key=lambda x: (x[0], x[1]))
    added = sorted((night_set_s - day_set_s), key=lambda x: (x[0], x[1]))

    step_saved = solver_k.step_count - solver_s.step_count
    step_pct = (step_saved / solver_k.step_count * 100.0) if solver_k.step_count else 0.0
    event_speedup = event_k_ms / event_s_ms if event_s_ms > 0 else float("inf")

    print(f"\n=== PERBANDINGAN KASUS: {meta_k['title']} ===")
    print(f"File Skenario : {yaml_path}")
    print(f"Pengulangan   : {args.repeats}x rata-rata\n")
    print(f" {'Metrik':<34} {'StaticKruskal':>16} {'SubtreeRepair':>16}")
    print(" " + "-" * 68)
    print(f" {'MST Awal / Siang (m)':<34} {day_k:>16.1f} {day_s:>16.1f}")
    print(f" {'MST Akhir / Malam (m)':<34} {night_k:>16.1f} {night_s:>16.1f}")
    print(f" {'Selisih Biaya Malam vs Siang (m)':<34} {night_k - day_k:>+16.1f} {night_s - day_s:>+16.1f}")
    print(f" {'Total Trace Steps':<34} {solver_k.step_count:>16} {solver_s.step_count:>16}")
    print(f" {'Mean Init Time (ms)':<34} {init_k_ms:>16.4f} {init_s_ms:>16.4f}")
    print(f" {'Mean Dynamic Event Time (ms)':<34} {event_k_ms:>16.4f} {event_s_ms:>16.4f}")
    print(" " + "-" * 68)
    print(f" Optimalitas MST Siang & Malam Identik : {day_set_k == day_set_s and night_set_k == night_set_s}")
    print(f" Penghematan Trace Steps               : {step_saved} steps ({step_pct:.1f}%)")
    print(f" Speedup Rata-rata Event Dinamis       : {event_speedup:.2f}x")
    print(f" Sisi Terputus (Gate Tutup)            : {removed}")
    print(f" Sisi Pengganti (Subtree Repair)       : {added}")
    print(f"\nTrace JSON StaticKruskal : {out_k}")
    print(f"Trace JSON SubtreeRepair : {out_s}")

    run_scalability_comparison()


if __name__ == "__main__":
    main()
