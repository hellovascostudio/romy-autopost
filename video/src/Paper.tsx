import { AbsoluteFill } from "remotion";

// Cream paper with a fine, static grain and a soft vignette.
const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='320' height='320'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='3' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 0.35  0 0 0 0 0.3  0 0 0 0 0.22  0 0 0 .55 0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")";

export const Paper: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: "radial-gradient(ellipse at 50% 42%, #F4EEE2 0%, #EAE1D0 62%, #D8CBB3 100%)" }}>
    <AbsoluteFill style={{ backgroundImage: GRAIN, opacity: 0.32, mixBlendMode: "multiply" }} />
    <AbsoluteFill
      style={{ background: "radial-gradient(ellipse at 50% 50%, rgba(0,0,0,0) 55%, rgba(60,45,25,0.22) 100%)" }}
    />
    {children}
  </AbsoluteFill>
);
