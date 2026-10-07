"use client";

import type { GeoJSONSource, Map as MlMap, Marker } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";

import { MAP_STYLE_URL } from "@/lib/config";
import type { Point } from "@/lib/route";

// "waiting": in the route but not approved yet (preview); "pending": waiting and outside the route
export type PinState = "todo" | "next" | "done" | "waiting" | "pending";
export type Pin = { id: string; n: number | null; at: Point; state: PinState; label: string };

const BLUE = "#0c55a4";
const DONE = "#86857f";
const DRAW_MS = 1100;

const line = (coords: number[][]): GeoJSON.Feature => ({
  type: "Feature",
  properties: {},
  geometry: { type: "LineString", coordinates: coords },
});

// The first `share` of a polyline by length, so the route can draw itself.
function partial(coords: number[][], share: number) {
  if (share >= 1 || coords.length < 2) return coords;
  const seg = coords.slice(1).map((c, i) => Math.hypot(c[0] - coords[i][0], c[1] - coords[i][1]));
  let left = seg.reduce((a, b) => a + b, 0) * share;
  const out = [coords[0]];
  for (let i = 0; i < seg.length; i++) {
    if (left >= seg[i]) {
      out.push(coords[i + 1]);
      left -= seg[i];
    } else {
      const k = seg[i] ? left / seg[i] : 0;
      out.push([coords[i][0] + (coords[i + 1][0] - coords[i][0]) * k, coords[i][1] + (coords[i + 1][1] - coords[i][1]) * k]);
      break;
    }
  }
  return out;
}

const HUB_SVG =
  '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M22 8.35V20a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8.35A2 2 0 0 1 3.26 6.5l8-3.2a2 2 0 0 1 1.48 0l8 3.2A2 2 0 0 1 22 8.35Z"/><path d="M6 18h12"/><path d="M6 14h12"/><rect width="12" height="12" x="6" y="10"/></svg>';
const CHECK_SVG =
  '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';

// One HTML marker; MapLibre moves the outer element, the inner button carries the look.
function makePin(
  lib: typeof import("maplibre-gl"),
  m: MlMap,
  o: { html: string; cls: string; at: Point; i: number; title: string; z: number },
) {
  const wrap = document.createElement("div");
  wrap.style.zIndex = String(o.z);
  const el = document.createElement("button");
  el.type = "button";
  el.className = o.cls;
  el.title = o.title;
  el.setAttribute("aria-label", o.title);
  el.style.setProperty("--i", String(o.i));
  el.innerHTML = o.html;
  wrap.appendChild(el);
  const marker = new lib.Marker({ element: wrap }).setLngLat([o.at.lon, o.at.lat]).addTo(m);
  return { marker, el };
}

// One runner's route on the base map: the hub, the stops in order (the next one pulses), the
// legs as straight lines (not roads), and visits still waiting for approval as dashed pins.
export function RouteMap({
  hub,
  hubLabel,
  pins,
  selected,
  onSelect,
  fitKey,
  label,
  onError,
}: {
  hub: Point;
  hubLabel: string;
  pins: Pin[];
  selected: string | null;
  onSelect: (id: string) => void;
  fitKey: string;
  label: string;
  onError: () => void;
}) {
  const box = useRef<HTMLDivElement>(null);
  const map = useRef<MlMap | null>(null);
  const ml = useRef<typeof import("maplibre-gl") | null>(null);
  const markers = useRef(new Map<string, { marker: Marker; el: HTMLButtonElement }>());
  const [ready, setReady] = useState(false);
  const latest = useRef({ onSelect, onError, hub, pins });
  useEffect(() => {
    latest.current = { onSelect, onError, hub, pins };
  });

  useEffect(() => {
    let disposed = false;
    let instance: MlMap | null = null;
    (async () => {
      const lib = await import("maplibre-gl");
      if (disposed || !box.current) return;
      lib.setWorkerUrl(`/maplibre/${lib.getVersion()}/maplibre-gl-worker.mjs`);
      ml.current = lib;
      const { hub: h, pins: ps } = latest.current;
      const bounds = new lib.LngLatBounds([h.lon, h.lat], [h.lon, h.lat]);
      ps.forEach((p) => bounds.extend([p.at.lon, p.at.lat]));
      instance = new lib.Map({
        container: box.current,
        style: MAP_STYLE_URL,
        bounds,
        fitBoundsOptions: { padding: 56, maxZoom: 14 },
        attributionControl: { compact: true },
        dragRotate: false,
        pitchWithRotate: false,
      });
      instance.touchZoomRotate.disableRotation();
      instance.addControl(new lib.NavigationControl({ showCompass: false }), "top-right");
      instance.on("error", (e) => {
        if (!instance?.isStyleLoaded() && (e.error?.message ?? "").length) latest.current.onError();
      });
      instance.on("load", () => {
        if (!instance) return;
        instance.addSource("route", { type: "geojson", data: line([]) });
        instance.addSource("done", { type: "geojson", data: line([]) });
        instance.addSource("return", { type: "geojson", data: line([]) });
        instance.addLayer({
          id: "route-casing",
          type: "line",
          source: "route",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": "#ffffff", "line-width": 7, "line-opacity": 0.9 },
        });
        instance.addLayer({
          id: "route",
          type: "line",
          source: "route",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": BLUE, "line-width": 3.5 },
        });
        instance.addLayer({
          id: "done",
          type: "line",
          source: "done",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": DONE, "line-width": 3.5 },
        });
        instance.addLayer({
          id: "return",
          type: "line",
          source: "return",
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": BLUE, "line-width": 2, "line-dasharray": [1.5, 2], "line-opacity": 0.7 },
        });
        map.current = instance;
        setReady(true);
      });
    })();
    const own = markers.current;
    return () => {
      disposed = true;
      own.forEach(({ marker }) => marker.remove());
      own.clear();
      instance?.remove();
      map.current = null;
    };
  }, []);

  // the hub and the pins: rebuilt when the route changes, each popping in in order
  const signature = `${hub.lat},${hub.lon}|${pins.map((p) => `${p.id}:${p.n}:${p.state}`).join(",")}`;
  useEffect(() => {
    const m = map.current;
    const lib = ml.current;
    if (!ready || !m || !lib) return;
    const own = markers.current;
    own.forEach(({ marker }) => marker.remove());
    own.clear();
    const { hub: h, pins: ps } = latest.current;
    own.set("hub", makePin(lib, m, { html: HUB_SVG, cls: "route-pin route-pin--hub", at: h, i: 0, title: hubLabel, z: 5 }));
    ps.forEach((p, i) => {
      const inner = p.state === "done" ? CHECK_SVG : String(p.n ?? "");
      const pin = makePin(lib, m, {
        html: `<span class="route-pin__halo"></span><span class="route-pin__dot">${inner}</span>`,
        cls: "route-pin",
        at: p.at,
        i,
        title: p.label,
        z: p.state === "next" ? 4 : p.state === "pending" ? 1 : 2,
      });
      pin.el.dataset.state = p.state;
      pin.el.addEventListener("click", (e) => {
        e.stopPropagation();
        latest.current.onSelect(p.id);
      });
      own.set(p.id, pin);
    });
  }, [ready, signature, hubLabel]);

  // the selected pin: an outline, and the map eases to it
  useEffect(() => {
    if (!ready) return;
    markers.current.forEach(({ el }, id) => {
      if (id === selected) el.dataset.selected = "";
      else delete el.dataset.selected;
    });
    const p = latest.current.pins.find((x) => x.id === selected);
    if (p && map.current) {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      map.current.easeTo({ center: [p.at.lon, p.at.lat], zoom: Math.max(map.current.getZoom(), 12.5), duration: reduce ? 0 : 700 });
    }
  }, [ready, selected, signature]);

  // the legs: drawn from the hub when the route changes; legs already done turn grey
  const routeKey = `${fitKey}|${pins.filter((p) => p.n !== null).map((p) => p.id).join(",")}`;
  const doneKey = pins.filter((p) => p.state === "done").map((p) => p.id).join(",");
  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const { hub: h, pins: ps } = latest.current;
    const route = ps.filter((p) => p.n !== null);
    const coords = [[h.lon, h.lat], ...route.map((p) => [p.at.lon, p.at.lat])];
    const back = route.length ? [coords[coords.length - 1], [h.lon, h.lat]] : [];
    const set = (id: string, c: number[][]) => (m.getSource(id) as GeoJSONSource | undefined)?.setData(line(c));
    set("return", []);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const t0 = performance.now();
    let frame = 0;
    const step = (now: number) => {
      const k = reduce ? 1 : Math.min(1, (now - t0) / DRAW_MS);
      const eased = 1 - (1 - k) ** 3;
      set("route", partial(coords, eased));
      if (k < 1) frame = requestAnimationFrame(step);
      else set("return", back);
    };
    frame = requestAnimationFrame(step);
    return () => cancelAnimationFrame(frame);
  }, [ready, routeKey]);

  useEffect(() => {
    const m = map.current;
    if (!ready || !m) return;
    const { hub: h, pins: ps } = latest.current;
    const route = ps.filter((p) => p.n !== null);
    const lastDone = route.map((p) => p.state).lastIndexOf("done");
    const coords = lastDone < 0 ? [] : [[h.lon, h.lat], ...route.slice(0, lastDone + 1).map((p) => [p.at.lon, p.at.lat])];
    (m.getSource("done") as GeoJSONSource | undefined)?.setData(line(coords));
  }, [ready, doneKey, routeKey]);

  // a new runner, day or scope: fit the map to the route
  useEffect(() => {
    const m = map.current;
    const lib = ml.current;
    if (!ready || !m || !lib) return;
    const { hub: h, pins: ps } = latest.current;
    const bounds = new lib.LngLatBounds([h.lon, h.lat], [h.lon, h.lat]);
    ps.forEach((p) => bounds.extend([p.at.lon, p.at.lat]));
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    m.fitBounds(bounds, { padding: 56, maxZoom: 14, duration: reduce ? 0 : 900 });
  }, [ready, fitKey]);

  return (
    <div className="absolute inset-0">
      <div ref={box} className="h-full w-full" role="region" aria-label={label} />
    </div>
  );
}
