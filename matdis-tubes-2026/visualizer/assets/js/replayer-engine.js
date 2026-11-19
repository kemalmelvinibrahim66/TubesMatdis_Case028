const DATA_URL = "samples/sample_case28_siskamling_portal.json";
const EDGE_KEY = (from, to) => `${Math.min(from, to)}-${Math.max(from, to)}`;

const groupColors = {
  command: "#e89000",
  gate: "#e53939",
  north: "#0aa875",
  west: "#0785c8",
  boulevard: "#d97800",
  banycipta: "#0c8b80",
  tatar: "#8b2bd1"
};

const nodeGroups = {
  0: "command",
  1: "north",
  2: "north",
  3: "west",
  4: "gate",
  5: "west",
  6: "gate",
  7: "west",
  8: "gate",
  9: "boulevard",
  10: "boulevard",
  11: "banycipta",
  12: "boulevard",
  13: "banycipta",
  14: "banycipta",
  15: "boulevard",
  16: "gate",
  17: "tatar",
  18: "tatar",
  19: "tatar",
  20: "tatar",
  21: "tatar",
  22: "tatar",
  23: "tatar",
  24: "tatar",
  25: "tatar"
};

const elements = {
  edges: document.getElementById("edges-layer"),
  labels: document.getElementById("labels-layer"),
  nodes: document.getElementById("nodes-layer"),
  error: document.getElementById("load-error")
};

let graphData;
let currentMode = "day";
let replayIndex = 0;
let selectedNodeId = null;
let showAllWeights = false;
const componentColors = ["#1873c4", "#d97706", "#8b2bd1"];

function svgElement(name, attributes) {
  const element = document.createElementNS("http://www.w3.org/2000/svg", name);
  Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
  return element;
}

function pointFor(node) {
  return { x: node.pos[0], y: 660 - node.pos[1] };
}

function addLine(layer, from, to, className) {
  const start = pointFor(graphData.nodes[from]);
  const end = pointFor(graphData.nodes[to]);
  const line = svgElement("line", {
    x1: start.x,
    y1: start.y,
    x2: end.x,
    y2: end.y,
    class: className
  });
  layer.append(line);
  return { start, end };
}

function findLabelPosition(start, end, width, placedLabels, nodePoints) {
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const length = Math.hypot(dx, dy) || 1;
  const normal = { x: -dy / length, y: dx / length };
  const offsets = [18, 28, 40, 54, 70, 88, 108, 132];
  const fractions = [0.5, 0.34, 0.66, 0.2, 0.8];
  let best;
  let bestScore = Infinity;

  for (const fraction of fractions) {
    for (const offset of offsets) {
      for (const side of [1, -1]) {
        const x = start.x + dx * fraction + normal.x * offset * side;
        const y = start.y + dy * fraction + normal.y * offset * side;
        const rect = {
          left: x - width / 2,
          right: x + width / 2,
          top: y - 9,
          bottom: y + 9
        };
        let score = offset + Math.abs(fraction - 0.5) * 20;

        if (rect.left < 8 || rect.right > 892 || rect.top < 8 || rect.bottom > 652) {
          score += 100000;
        }

        for (const placed of placedLabels) {
          const overlapX = Math.max(0, Math.min(rect.right + 4, placed.right) - Math.max(rect.left - 4, placed.left));
          const overlapY = Math.max(0, Math.min(rect.bottom + 3, placed.bottom) - Math.max(rect.top - 3, placed.top));
          if (overlapX > 0 && overlapY > 0) score += 10000 + overlapX * overlapY;
        }

        for (const point of nodePoints) {
          const nearestX = Math.max(rect.left, Math.min(point.x, rect.right));
          const nearestY = Math.max(rect.top, Math.min(point.y, rect.bottom));
          if (Math.hypot(point.x - nearestX, point.y - nearestY) < 16) score += 5000;
        }

        if (score < bestScore) {
          best = { x, y, rect };
          bestScore = score;
        }
        if (score < 200) return best;
      }
    }
  }

  return best;
}

function addEdgeLabel(edge, start, end, className, placedLabels, nodePoints) {
  const label = String(Math.round(edge.weight));
  const text = `${label}m`;
  const width = text.length * 7 + 12;
  const position = findLabelPosition(start, end, width, placedLabels, nodePoints);
  if (!position) return;

  const group = svgElement("g", { class: `edge-label ${className}` });
  group.append(svgElement("rect", {
    x: position.x - width / 2,
    y: position.y - 9,
    width,
    height: 18
  }));
  const textElement = svgElement("text", { x: position.x, y: position.y });
  textElement.textContent = text;
  group.append(textElement);
  elements.labels.append(group);
  placedLabels.push(position.rect);
}

function activeMstEdges() {
  const edges = new Set(graphData.mst.day);
  if (currentMode === "replay" || currentMode === "impact") {
    const phase = currentMode === "impact" ? graphData.impactSnapshot : graphData.replay[replayIndex];
    phase.removed.forEach((key) => edges.delete(key));
    phase.added.forEach((key) => edges.add(key));
  } else if (currentMode === "night") {
    graphData.mst.nightRemoved.forEach((key) => edges.delete(key));
    graphData.mst.nightAdded.forEach((key) => edges.add(key));
  }
  return edges;
}

function drawGraph() {
  const mstEdges = activeMstEdges();
  const phase = currentMode === "replay"
    ? graphData.replay[replayIndex]
    : (currentMode === "impact" ? graphData.impactSnapshot : null);
  elements.edges.replaceChildren();
  elements.labels.replaceChildren();
  elements.nodes.replaceChildren();
  const nodePoints = graphData.nodes.map(pointFor);
  const placedLabels = [];
  const pendingLabels = [];

  graphData.edges.forEach((edge) => {
    const key = EDGE_KEY(edge.from, edge.to);
    const isMst = mstEdges.has(key);
    const isClosedGate = phase
      ? phase.removed.includes(key)
      : currentMode === "night" && graphData.mst.nightRemoved.includes(key);
    const isActiveGate = currentMode === "day" && graphData.gates.includes(key);
    const isRepair = phase
      ? phase.added.includes(key)
      : currentMode === "night" && graphData.mst.nightAdded.includes(key);
    const { start, end } = addLine(elements.edges, edge.from, edge.to, "road-edge");

    if (isMst) addLine(elements.edges, edge.from, edge.to, "mst-edge");
    if (isClosedGate) {
      addLine(elements.edges, edge.from, edge.to, "gate-edge");
      const x = (start.x + end.x) / 2;
      const y = (start.y + end.y) / 2;
      elements.edges.append(svgElement("line", {
        x1: x - 6, y1: y - 6, x2: x + 6, y2: y + 6, class: "gate-cross"
      }));
      elements.edges.append(svgElement("line", {
        x1: x + 6, y1: y - 6, x2: x - 6, y2: y + 6, class: "gate-cross"
      }));
    } else if (isActiveGate) {
      addLine(elements.edges, edge.from, edge.to, "gate-edge is-open");
    } else if (isRepair) {
      addLine(elements.edges, edge.from, edge.to, "repair-edge");
    }

    const showLabel = showAllWeights || isMst || isClosedGate || isActiveGate || isRepair;
    if (showLabel) {
      const labelClass = isRepair ? "is-repair" : (isClosedGate || isActiveGate ? "is-gate" : (isMst ? "is-mst" : ""));
      const priority = isRepair || isClosedGate || isActiveGate ? 0 : (isMst ? 1 : 2);
      pendingLabels.push({ edge, start, end, labelClass, priority });
    }
  });

  pendingLabels.sort((a, b) => a.priority - b.priority);
  pendingLabels.forEach(({ edge, start, end, labelClass }) => {
    addEdgeLabel(edge, start, end, labelClass, placedLabels, nodePoints);
  });

  graphData.nodes.forEach((node) => {
    const point = pointFor(node);
    const componentIndex = phase
      ? phase.components.findIndex((component) => component.includes(node.id))
      : -1;
    const nodeColor = componentIndex >= 0 && phase.components.length > 1
      ? componentColors[componentIndex % componentColors.length]
      : groupColors[nodeGroups[node.id]];
    const group = svgElement("g", {
      class: `node${selectedNodeId === node.id ? " is-selected" : ""}`,
      tabindex: "0",
      role: "button",
      "aria-label": `Node ${node.id}: ${node.label}`,
      "data-node-id": node.id
    });
    group.append(svgElement("circle", {
      cx: point.x,
      cy: point.y,
      r: 12,
      fill: nodeColor
    }));
    const text = svgElement("text", { x: point.x, y: point.y + 0.5 });
    text.textContent = node.id;
    group.append(text);
    group.addEventListener("click", () => selectNode(node.id));
    group.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectNode(node.id);
      }
    });
    elements.nodes.append(group);
  });
}

function selectNode(nodeId) {
  selectedNodeId = nodeId;
  const node = graphData.nodes.find((item) => item.id === nodeId);
  const adjacent = graphData.edges.filter((edge) => edge.from === nodeId || edge.to === nodeId);
  const mst = activeMstEdges();
  const mstDegree = adjacent.filter((edge) => mst.has(EDGE_KEY(edge.from, edge.to))).length;
  document.getElementById("selected-node-title").textContent = `N${String(node.id).padStart(2, "0")}`;
  document.getElementById("selected-node-label").textContent = node.label;
  document.getElementById("selected-node-degree").textContent = adjacent.length;
  document.getElementById("selected-node-mst-degree").textContent = mstDegree;
  drawGraph();
}

function edgeWeight(edgeKey) {
  const edge = graphData.edges.find((item) => EDGE_KEY(item.from, item.to) === edgeKey);
  return edge ? edge.weight : 0;
}

function renderComponents(components) {
  const summary = document.getElementById("component-summary");
  summary.replaceChildren();
  components.forEach((component, index) => {
    const chip = document.createElement("span");
    chip.className = `component-chip${components.length > 1 ? " is-split" : ""}`;
    chip.style.setProperty("--component-color", componentColors[index % componentColors.length]);
    chip.textContent = components.length > 1
      ? `Komponen ${index + 1}: ${component.length} node`
      : `Terhubung: ${component.length} node`;
    summary.append(chip);
  });
}

function updateTimelineControls() {
  const slider = document.getElementById("timeline-slider");
  const impactButton = document.getElementById("impact-view");
  const isImpact = currentMode === "impact";
  const phase = isImpact ? graphData.impactSnapshot : graphData.replay[replayIndex];
  slider.max = graphData.replay.length - 1;
  slider.value = replayIndex;
  slider.disabled = isImpact;
  document.getElementById("timeline-count").textContent = isImpact
    ? "Snapshot dampak"
    : `Langkah ${replayIndex + 1} dari ${graphData.replay.length}`;
  document.getElementById("step-label").textContent = phase.title;
  document.getElementById("step-description").textContent = phase.description;
  document.getElementById("previous-step").disabled = isImpact || replayIndex === 0;
  document.getElementById("next-step").disabled = isImpact || replayIndex === graphData.replay.length - 1;
  impactButton.textContent = isImpact ? "Kembali ke urutan trace" : "Lihat dampak dua gate ditutup bersamaan";
  impactButton.setAttribute("aria-pressed", String(isImpact));
}

function updateModeButtons() {
  document.querySelectorAll(".mode-button").forEach((button) => {
    const active = button.dataset.mode === currentMode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function updateDetails() {
  const isReplay = currentMode === "replay" || currentMode === "impact";
  const isNight = currentMode === "night";
  const phase = currentMode === "impact"
    ? graphData.impactSnapshot
    : (currentMode === "replay" ? graphData.replay[replayIndex] : null);
  const cost = phase
    ? phase.forestCost
    : (isNight ? graphData.mst.nightCost : graphData.mst.dayCost);
  const componentCount = phase ? phase.components.length : 1;
  const edgeCount = phase ? phase.edgeCount : 25;

  if (phase) {
    document.getElementById("map-title").textContent = phase.title;
    document.getElementById("map-description").textContent = phase.description;
    document.getElementById("status-pill").textContent = phase.removed.length
      ? `${componentCount} KOMPONEN`
      : "TERHUBUNG";
    document.getElementById("status-pill").classList.toggle("is-night", phase.removed.length > 0);
    document.getElementById("condition-title").textContent = phase.title;
    document.getElementById("condition-dot").classList.toggle("is-night", phase.removed.length > 0);
    document.getElementById("condition-details").innerHTML = `
      <p><strong>Forest saat ini:</strong> ${edgeCount} sisi / ${componentCount} komponen</p>
      <p><strong>Bobot forest:</strong> ${cost.toLocaleString("id-ID")} m</p>
      ${phase.removed.map((key) => `<p class="danger"><strong>Gate ditutup:</strong> N${key.split("-")[0].padStart(2, "0")}-N${key.split("-")[1].padStart(2, "0")} (${edgeWeight(key)} m)</p>`).join("")}
      ${phase.added.map((key) => `<p class="repair"><strong>Sisi repair:</strong> N${key.split("-")[0].padStart(2, "0")}-N${key.split("-")[1].padStart(2, "0")} (${edgeWeight(key)} m)</p>`).join("")}
      <p class="good"><strong>${componentCount > 1 ? "Selisih bobot forest (belum terhubung)" : "Perubahan dari MST siang"}:</strong> ${cost - graphData.mst.dayCost > 0 ? "+" : ""}${(cost - graphData.mst.dayCost).toLocaleString("id-ID")} m</p>
    `;
    renderComponents(phase.components);
  } else {
    document.getElementById("map-title").textContent = isNight ? "Kondisi malam (23.00-05.00)" : "Kondisi siang";
    document.getElementById("map-description").textContent = isNight
      ? "Dua gate ditutup; dua sisi alternatif memperbaiki konektivitas MST."
      : "Gate 1 dan Gate 2 terbuka, keduanya termasuk sisi MST.";
    document.getElementById("status-pill").textContent = isNight ? "2 GATE TUTUP" : "GATE BUKA";
    document.getElementById("status-pill").classList.toggle("is-night", isNight);
    document.getElementById("condition-title").textContent = isNight ? "Malam (gate tutup)" : "Siang (gate buka)";
    document.getElementById("condition-dot").classList.toggle("is-night", isNight);
    if (isNight) {
      document.getElementById("condition-details").innerHTML = `
        <p class="danger"><strong>Gate 1 tutup:</strong> N04-N06 (${graphData.gateWeights[0]} m)</p>
        <p class="danger"><strong>Gate 2 tutup:</strong> N08-N16 (${graphData.gateWeights[1]} m)</p>
        <p class="repair"><strong>Perbaikan 1:</strong> N05-N06 (${edgeWeight("5-6")} m)</p>
        <p class="repair"><strong>Perbaikan 2:</strong> N08-N10 (${edgeWeight("8-10")} m)</p>
        <p class="good"><strong>Total MST malam:</strong> ${graphData.mst.nightCost.toLocaleString("id-ID")} m</p>
        <p><strong>Delta bobot:</strong> +${graphData.mst.nightCost - graphData.mst.dayCost} m</p>
      `;
    } else {
      document.getElementById("condition-details").innerHTML = `
        <p class="good"><strong>Total MST siang:</strong> ${graphData.mst.dayCost.toLocaleString("id-ID")} m</p>
        <p><strong>Gate 1 aktif:</strong> N04-N06 (${graphData.gateWeights[0]} m)</p>
        <p><strong>Gate 2 aktif:</strong> N08-N16 (${graphData.gateWeights[1]} m)</p>
        <p><strong>Skala visual:</strong> jarak dalam meter</p>
        <p><strong>Node terhubung:</strong> ${graphData.nodes.length}</p>
      `;
    }
    renderComponents([graphData.nodes.map((node) => node.id)]);
  }

  document.getElementById("mst-cost").textContent = `${cost.toLocaleString("id-ID")} m`;
  document.getElementById("mst-detail").textContent = `${edgeCount} sisi / ${componentCount} komponen`;
  document.getElementById("night-delta").textContent = `+${graphData.mst.nightCost - graphData.mst.dayCost} m`;
}

function setMode(mode) {
  currentMode = mode;
  replayIndex = mode === "night" ? graphData.replay.length - 1 : 0;
  updateModeButtons();
  updateTimelineControls();
  updateDetails();
  drawGraph();
  if (selectedNodeId !== null) selectNode(selectedNodeId);
}

function setReplayStep(index) {
  replayIndex = Math.max(0, Math.min(graphData.replay.length - 1, index));
  currentMode = "replay";
  updateModeButtons();
  updateTimelineControls();
  updateDetails();
  drawGraph();
  if (selectedNodeId !== null) selectNode(selectedNodeId);
}

function setImpactView() {
  currentMode = currentMode === "impact" ? "replay" : "impact";
  updateModeButtons();
  updateTimelineControls();
  updateDetails();
  drawGraph();
  if (selectedNodeId !== null) selectNode(selectedNodeId);
}

function validateData(data) {
  if (!Array.isArray(data.nodes) || data.nodes.length !== 26) {
    throw new Error("Data visualisasi harus berisi 26 node.");
  }
  if (!Array.isArray(data.edges) || data.edges.length !== 36) {
    throw new Error("Data visualisasi harus berisi 36 sisi.");
  }
  if (new Set(data.mst.day).size !== 25 || new Set(data.mst.nightRemoved).size !== 2 || new Set(data.mst.nightAdded).size !== 2) {
    throw new Error("Data MST siang/malam tidak lengkap.");
  }
  if (!Array.isArray(data.replay) || data.replay.length !== 5 || data.replay.some((step) => !Array.isArray(step.components))) {
    throw new Error("Data replay Dynamic MST tidak lengkap.");
  }
  if (!data.impactSnapshot || data.impactSnapshot.components.length !== 3) {
    throw new Error("Snapshot dampak dua gate tidak lengkap.");
  }
  if (!data.algorithmComparison || data.algorithmComparison.subtreeRepairSteps <= 0 || data.algorithmComparison.staticKruskalSteps <= 0) {
    throw new Error("Data perbandingan algoritma tidak lengkap.");
  }
}

async function initialize() {
  try {
    const response = await fetch(DATA_URL);
    if (!response.ok) throw new Error(`Gagal memuat data graf (${response.status}).`);
    graphData = await response.json();
    validateData(graphData);

    document.getElementById("node-count").textContent = graphData.nodes.length;
    document.getElementById("edge-count").textContent = graphData.edges.length;
    document.getElementById("night-delta").textContent = `+${graphData.mst.nightCost - graphData.mst.dayCost} m`;
    const subtreeSteps = graphData.algorithmComparison.subtreeRepairSteps;
    const kruskalSteps = graphData.algorithmComparison.staticKruskalSteps;
    const savedSteps = kruskalSteps - subtreeSteps;
    document.getElementById("subtree-steps").textContent = subtreeSteps;
    document.getElementById("kruskal-steps").textContent = kruskalSteps;
    document.getElementById("step-savings").textContent = `${savedSteps} lebih sedikit`;
    document.getElementById("step-savings-note").textContent = `${Math.round((savedSteps / kruskalSteps) * 100)}% lebih sedikit daripada Kruskal`;
    document.querySelectorAll(".mode-button").forEach((button) => {
      button.addEventListener("click", () => setMode(button.dataset.mode));
    });
    document.getElementById("timeline-slider").addEventListener("input", (event) => {
      setReplayStep(Number(event.target.value));
    });
    document.getElementById("previous-step").addEventListener("click", () => {
      setReplayStep(replayIndex - 1);
    });
    document.getElementById("next-step").addEventListener("click", () => {
      setReplayStep(replayIndex + 1);
    });
    document.getElementById("impact-view").addEventListener("click", setImpactView);
    document.getElementById("show-all-weights").checked = showAllWeights;
    document.getElementById("show-all-weights").addEventListener("change", (event) => {
      showAllWeights = event.target.checked;
      drawGraph();
    });
    updateModeButtons();
    updateTimelineControls();
    updateDetails();
    drawGraph();
  } catch (error) {
    elements.error.hidden = false;
    elements.error.textContent = `${error.message} Jalankan visualizer melalui server lokal, misalnya: python -m http.server 8000 dari folder matdis-tubes-2026.`;
  }
}

initialize();