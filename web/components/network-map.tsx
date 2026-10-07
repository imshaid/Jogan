"use client";

import type { GeoJSONSource, Map as MlMap, Popup } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import type { NetworkAgent } from "@/lib/api";
import { MAP_STYLE_URL } from "@/lib/config";
import { RISK_BANDS, riskLevel, type RiskLevel } from "@/lib/format";

export type RiskSide = "max" | "cash" | "efloat";
export type ShowFilter = "all" | "visits" | "high";

const SOURCE = "agents";
const COLORS = {
  high: "#b5121b",
  medium: "#e0a400",
  low: "#7d8796",
  ink: "#050608",
  ring: "#ffffff",
  visit: "#0c55a4",
  selected: "#050608",
};

export function sideP(a: NetworkAgent, side: RiskSide) {
  if (side === "cash") return a.p_stockout_cash;
  if (side === "efloat") return a.p_stockout_efloat;
  return Math.max(a.p_stockout_cash, a.p_stockout_efloat);
}

// Shapes repeat the risk level, so it never rests on colour alone (D-022).
function drawMarker(level: RiskLevel, ratio: number): ImageData {
  const size = 20 * ratio;
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const ctx = canvas.getContext("2d")!;
  ctx.scale(ratio, ratio);
  ctx.lineJoin = "round";
  ctx.beginPath();
  if (level === "high") {
    ctx.moveTo(10, 2.5);
    ctx.lineTo(18, 16.5);
    ctx.lineTo(2, 16.5);
  } else if (level === "medium") {
    ctx.moveTo(10, 2.5);
    ctx.lineTo(17, 10);
    ctx.lineTo(10, 17.5);
    ctx.lineTo(3, 10);
  } else {
    ctx.arc(10, 10, 5, 0, Math.PI * 2);
  }
  ctx.closePath();
  ctx.lineWidth = 3;
  ctx.strokeStyle = COLORS.ring;
  ctx.stroke();
  ctx.fillStyle = COLORS[level];
  ctx.fill();
  if (level === "medium") {
    // amber needs an ink edge to stand out on a light map
    ctx.lineWidth = 1;
    ctx.strokeStyle = COLORS.ink;
    ctx.stroke();
  }
  return ctx.getImageData(0, 0, size, size);
}

function toGeoJSON(agents: NetworkAgent[], side: RiskSide): GeoJSON.FeatureCollection {
  return {
    type: "FeatureCollection",
    features: agents.map((a) => {
      const p = sideP(a, side);
      return {
        type: "Feature",
        id: a.agent_id,
        geometry: { type: "Point", coordinates: [a.lon, a.lat] },
        properties: { id: a.agent_id, p, level: riskLevel(p), visit: a.runner_id !== null },
      };
    }),
  };
}

function filterFor(show: ShowFilter) {
  if (show === "visits") return ["==", ["get", "visit"], true];
  if (show === "high") return [">=", ["get", "p"], RISK_BANDS.high];
  return null;
}

export function NetworkMap({
  agents,
  side,
  show,
  selected,
  onSelect,
  label,
  onError,
  pulse = [],
  hoverText,
}: {
  agents: NetworkAgent[];
  side: RiskSide;
  show: ShowFilter;
  selected: string | null;
  onSelect: (id: string | null) => void;
  label: string;
  onError: () => void;
  // the most urgent agents, marked with a slow pulse (the "highest risk" list beside the map)
  pulse?: string[];
  // the hover card's text for one agent
  hoverText?: (a: NetworkAgent) => string;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const [ready, setReady] = useState(false);
  const latest = useRef({ agents, side, onSelect, onError, hoverText });
  useEffect(() => {
    latest.current = { agents, side, onSelect, onError, hoverText };
  });

  // create the map once; MapLibre touches window, so it loads in the browser only
  useEffect(() => {
    let disposed = false;
    let instance: MlMap | null = null;
    (async () => {
      const ml = await import("maplibre-gl");
      if (disposed || !box.current) return;
      ml.setWorkerUrl(`/maplibre/${ml.getVersion()}/maplibre-gl-worker.mjs`);
      const { agents: initial } = latest.current;
      const bounds = new ml.LngLatBounds();
      initial.forEach((a) => bounds.extend([a.lon, a.lat]));
      instance = new ml.Map({
        container: box.current,
        style: MAP_STYLE_URL,
        bounds: initial.length ? bounds : undefined,
        fitBoundsOptions: { padding: 48 },
        center: initial.length ? undefined : [90.4, 23.8],
        zoom: initial.length ? undefined : 6,
        attributionControl: { compact: true },
        cooperativeGestures: false,
        dragRotate: false,
        pitchWithRotate: false,
      });
      instance.touchZoomRotate.disableRotation();
      instance.addControl(new ml.NavigationControl({ showCompass: false }), "top-right");
      instance.on("error", (e) => {
        // tile hiccups are routine; only a style that never loads is worth telling the user
        if (!instance?.isStyleLoaded() && (e.error?.message ?? "").length) latest.current.onError();
      });
      instance.on("load", () => {
        if (!instance) return;
        const ratio = Math.max(2, Math.ceil(window.devicePixelRatio || 1));
        for (const level of ["high", "medium", "low"] as const) {
          instance.addImage(`risk-${level}`, drawMarker(level, ratio), { pixelRatio: ratio });
        }
        instance.addSource(SOURCE, { type: "geojson", data: toGeoJSON(latest.current.agents, latest.current.side) });
        instance.addLayer({
          id: "visit-ring",
          type: "circle",
          source: SOURCE,
          filter: ["==", ["get", "visit"], true],
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 5.5, 9, 8, 12, 11],
            "circle-color": "rgba(12,85,164,0.08)",
            "circle-stroke-color": COLORS.visit,
            "circle-stroke-width": 1.75,
          },
        });
        instance.addLayer({
          id: "pulse",
          type: "circle",
          source: SOURCE,
          filter: ["in", ["get", "id"], ["literal", []]],
          paint: {
            "circle-radius": 10,
            "circle-color": COLORS.high,
            "circle-opacity": 0.25,
            "circle-stroke-width": 0,
            "circle-radius-transition": { duration: 0 },
            "circle-opacity-transition": { duration: 0 },
          },
        });
        instance.addLayer({
          id: "agents",
          type: "symbol",
          source: SOURCE,
          layout: {
            "icon-image": ["concat", "risk-", ["get", "level"]],
            "icon-size": ["interpolate", ["linear"], ["zoom"], 6, 0.5, 9, 0.75, 12, 1],
            "icon-allow-overlap": true,
            "icon-ignore-placement": true,
            "symbol-sort-key": ["get", "p"],
          },
        });
        instance.addLayer({
          id: "selected",
          type: "circle",
          source: SOURCE,
          filter: ["==", ["get", "id"], ""],
          paint: {
            "circle-radius": ["interpolate", ["linear"], ["zoom"], 6, 9, 12, 15],
            "circle-color": "rgba(0,0,0,0)",
            "circle-stroke-color": COLORS.selected,
            "circle-stroke-width": 2.5,
          },
        });
        instance.on("click", "agents", (e) => {
          const id = e.features?.[0]?.properties?.id;
          if (typeof id === "string") latest.current.onSelect(id);
        });
        instance.on("click", (e) => {
          const hit = instance?.queryRenderedFeatures(e.point, { layers: ["agents"] }) ?? [];
          if (!hit.length) latest.current.onSelect(null);
        });
        // a small hover card with the agent and its stock-out chance
        const tip: Popup = new ml.Popup({ closeButton: false, closeOnClick: false, offset: 12, className: "map-tip" });
        instance.on("mousemove", "agents", (e) => {
          if (!instance) return;
          instance.getCanvas().style.cursor = "pointer";
          const id = e.features?.[0]?.properties?.id;
          const a = latest.current.agents.find((x) => x.agent_id === id);
          const text = a && latest.current.hoverText?.(a);
          if (!a || !text) return;
          tip.setLngLat([a.lon, a.lat]).setText(text).addTo(instance);
        });
        instance.on("mouseleave", "agents", () => {
          if (!instance) return;
          instance.getCanvas().style.cursor = "";
          tip.remove();
        });
        map.current = instance;
        setReady(true);
      });
    })();
    return () => {
      disposed = true;
      instance?.remove();
      map.current = null;
    };
  }, []);

  useEffect(() => {
    if (!ready || !map.current) return;
    (map.current.getSource(SOURCE) as GeoJSONSource | undefined)?.setData(toGeoJSON(agents, side));
  }, [ready, agents, side]);

  useEffect(() => {
    if (!ready || !map.current) return;
    const f = filterFor(show);
    map.current.setFilter("agents", f as never);
    const visitFilter = show === "high" ? ["all", ["==", ["get", "visit"], true], f] : ["==", ["get", "visit"], true];
    map.current.setFilter("visit-ring", visitFilter as never);
  }, [ready, show]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    m.setFilter("selected", ["==", ["get", "id"], selected ?? ""]);
    const a = latest.current.agents.find((x) => x.agent_id === selected);
    if (!a) return;
    // bring a chosen agent into view (from the map or the list beside it)
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    m.easeTo({ center: [a.lon, a.lat], zoom: Math.max(m.getZoom(), 9), duration: reduce ? 0 : 800 });
  }, [ready, selected]);

  // the pulse: radius and opacity breathe on a 1.8 s cycle; still with reduced motion
  const pulseKey = pulse.join(",");
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    m.setFilter("pulse", ["in", ["get", "id"], ["literal", pulseKey ? pulseKey.split(",") : []]]);
    if (!pulseKey || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let frame = 0;
    const t0 = performance.now();
    const step = (now: number) => {
      const k = ((now - t0) % 1800) / 1800;
      const zoom = m.getZoom();
      const base = zoom < 8 ? 7 : zoom < 11 ? 10 : 13;
      m.setPaintProperty("pulse", "circle-radius", base + k * base * 1.6);
      m.setPaintProperty("pulse", "circle-opacity", 0.35 * (1 - k));
      frame = requestAnimationFrame(step);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [ready, pulseKey]);

  // MapLibre makes its container position: relative, so the sizing box wraps it
  return (
    <div className="absolute inset-0">
      <div ref={box} className="h-full w-full" role="region" aria-label={label} />
    </div>
  );
}
