import { useEffect, useMemo, useReducer, useState } from "react";
import { fetchProviders, serverHealth } from "./api";
import { isolatedMembers, operationsReducer, type OperationsState, type Provider } from "./domain";
import "./styles.css";

const panels = ["Operations", "Tactical Map", "Objectives", "Logistics", "Security", "Cameras", "Friends", "Integrations", "Settings"];
const initial: OperationsState = {
  connection: "connecting",
  activePanel: "Operations",
  members: [
    { id: "1", name: "Taylor", online: true, alive: true, grid: "H12", distanceFromLeader: 0 },
    { id: "2", name: "Storm", online: true, alive: true, grid: "J14", distanceFromLeader: 420 },
    { id: "3", name: "BigNutJoe", online: false, alive: true, distanceFromLeader: 0 }
  ],
  objectives: [
    { id: "cargo", title: "Cargo response", grid: "M4", status: "open", priority: 4 },
    { id: "sulfur", title: "Collect sulfur purchase", grid: "F18", status: "claimed", priority: 2, assignedTo: "Storm" }
  ]
};

export default function App() {
  const [state, dispatch] = useReducer(operationsReducer, initial);
  const [providers, setProviders] = useState<Provider[]>([]);
  useEffect(() => { serverHealth().then((online) => dispatch({ type: "connection", value: online ? "online" : "offline" })); fetchProviders().then(setProviders).catch(() => setProviders([])); }, []);
  const isolated = useMemo(() => isolatedMembers(state.members), [state.members]);
  return <div className="shell">
    <aside><div className="brand">RUST<br/><span>COMPANION+</span><small>2.0 TEAM OPERATIONS</small></div>{panels.map((panel) => <button key={panel} className={state.activePanel === panel ? "active" : ""} onClick={() => dispatch({ type: "panel", value: panel })}>{panel}</button>)}<div className={`status ${state.connection}`}>● {state.connection}</div></aside>
    <main><header><div><p className="eyebrow">SHARED TEAM ROOM</p><h1>{state.activePanel}</h1></div><div className="header-actions"><button>Raid readiness</button><button className="accent">New rally point</button></div></header>
      <section className="metrics"><article><span>ONLINE</span><strong>{state.members.filter(m => m.online).length}</strong><small>of {state.members.length} linked teammates</small></article><article><span>OPEN OBJECTIVES</span><strong>{state.objectives.filter(o => o.status !== "completed").length}</strong><small>claim or assign work</small></article><article><span>SEPARATED</span><strong>{isolated.length}</strong><small>over 300 m from leader</small></article><article><span>INTEGRATIONS</span><strong>{providers.length || 16}</strong><small>credential-gated providers</small></article></section>
      <section className="grid"><div className="panel map"><div className="panel-title"><h2>Tactical room</h2><span>cached map + live events</span></div><div className="map-placeholder"><div className="rally">RALLY<br/>H12</div><div className="danger">DANGER</div><div className="team-dot one">T</div><div className="team-dot two">S</div><p>Interactive Rust map renderer connects here through the local Rust+ sidecar.</p></div></div>
      <div className="panel"><div className="panel-title"><h2>Current objectives</h2><span>shared assignments</span></div>{state.objectives.map(o => <div className="row" key={o.id}><div><strong>{o.title}</strong><small>{o.grid ?? "No grid"} · priority {o.priority}</small></div><span className={`pill ${o.status}`}>{o.status.replace("_", " ")}</span></div>)}</div>
      <div className="panel"><div className="panel-title"><h2>Team status</h2><span>presence and isolation</span></div>{state.members.map(m => <div className="row" key={m.id}><div><strong>{m.name}</strong><small>{m.grid ?? "Offline"} · {m.alive ? "alive" : "dead"}</small></div><span className={`pill ${m.online ? "online" : "offline"}`}>{m.online ? `${m.distanceFromLeader ?? 0} m` : "offline"}</span></div>)}</div>
      <div className="panel"><div className="panel-title"><h2>Security timeline</h2><span>acknowledged events</span></div><div className="event"><b>05:42</b><p>North alarm returned to normal. No acknowledgement required.</p></div><div className="event"><b>05:35</b><p>Storage threshold: charcoal below team target.</p></div><div className="event"><b>05:21</b><p>Storm claimed Cargo response.</p></div></div></section>
    </main>
  </div>;
}
