"use client";

import { animate, useReducedMotion } from "motion/react";
import { useEffect, useRef, useState, type ReactNode } from "react";

const EASE = [0.2, 0.7, 0.2, 1] as const;

// A number that glides to its new value (D-039): the format runs on every frame, so taka, Bangla
// digits and lakh grouping stay right mid-way. `from` counts up on first show. The final value is
// the text from the start for screen readers and with reduced motion.
export function Tween({
  value,
  format,
  from,
  className,
}: {
  value: number;
  format: (v: number) => string;
  from?: number;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement>(null);
  const shown = useRef<number | null>(null);
  const fmt = useRef(format);
  useEffect(() => {
    fmt.current = format;
  });
  const reduce = useReducedMotion();
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const start = shown.current ?? from ?? value;
    if (reduce || start === value) {
      shown.current = value;
      el.textContent = fmt.current(value);
      return;
    }
    const controls = animate(start, value, {
      duration: 0.9,
      ease: EASE,
      onUpdate: (v) => {
        shown.current = v;
        el.textContent = fmt.current(v);
      },
      onComplete: () => {
        shown.current = value;
      },
    });
    return () => controls.stop();
  }, [value, from, reduce]);
  return (
    <span ref={ref} className={className ? `num ${className}` : "num"}>
      {format(value)}
    </span>
  );
}

// Reveal on scroll: the block rises in when it first comes into view, and the CSS animations
// inside it (bars growing, lines drawing) wait until then, so charts below the fold still play.
export function useReveal<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const el = ref.current;
    if (!el || shown) return;
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setShown(true);
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -6% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [shown]);
  return { ref, "data-reveal": "", "data-shown": shown ? "" : undefined };
}

export function Reveal({ children, className }: { children: ReactNode; className?: string }) {
  const props = useReveal<HTMLDivElement>();
  return (
    <div {...props} className={className}>
      {children}
    </div>
  );
}
