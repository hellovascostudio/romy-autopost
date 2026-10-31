import { AbsoluteFill, Easing, Img, interpolate, staticFile, useCurrentFrame, useVideoConfig } from "remotion";
import { Paper } from "./Paper";
import type { Line, PageProps } from "./types";
import "./fonts";

const INK = "29,27,26";
const RED = "#A8782A";
const MUTED = "#8a7f6e";
const PAD = 110;
const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
const soft = Easing.bezier(0.16, 1, 0.3, 1);

const Header: React.FC<{ book: string; author: string }> = ({ book, author }) => (
  <div
    style={{
      position: "absolute", top: 210, left: 0, right: 0, textAlign: "center",
      font: "600 22px Inter", letterSpacing: "0.32em", color: MUTED,
    }}
  >
    {book.toUpperCase()} · {author.toUpperCase()}
  </div>
);

const Footer: React.FC<{ handle: string }> = ({ handle }) => (
  <div
    style={{
      position: "absolute", bottom: 150, left: 0, right: 0, textAlign: "center",
      font: "500 22px Inter", letterSpacing: "0.3em", color: MUTED, opacity: 0.8,
    }}
  >
    {handle.toUpperCase()}
  </div>
);

const Paragraph: React.FC<{ line: Line; t: number }> = ({ line, t }) => {
  const tokens = line.text.split(" ");
  const past = interpolate(t, [line.end + 0.25, line.end + 0.9], [1, 0.42], clamp);
  const underline = interpolate(t, [line.end - 0.1, line.end + 0.7], [0, 1], { ...clamp, easing: soft });
  return (
    <p
      style={{
        margin: "0 0 40px", font: `${line.key ? "italic 600" : "500"} 66px/1.42 Corm`,
        textDecorationLine: line.key ? "underline" : "none", textDecorationStyle: "wavy",
        textDecorationColor: `rgba(168,120,42,${underline})`, textDecorationThickness: 3,
        textUnderlineOffset: 14, textDecorationSkipInk: "none",
      }}
    >
      {tokens.map((tok, i) => {
        const wt = line.words[i] ?? line.start + ((line.end - line.start) * i) / tokens.length;
        const lit = interpolate(t, [wt - 0.02, wt + 0.14], [0.17, 1], clamp);
        return (
          <span key={i} style={{ color: `rgba(${INK},${lit * past})` }}>
            {tok}
            {i < tokens.length - 1 ? " " : ""}
          </span>
        );
      })}
    </p>
  );
};

export const BookPage: React.FC<PageProps> = (p) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  // title page
  const titleOut = interpolate(t, [p.hookEnd - 0.6, p.hookEnd], [1, 0], clamp);
  const titleIn = interpolate(t, [0, 0.8], [0, 1], { ...clamp, easing: soft });

  // text pages
  const pageEnd = (i: number) => (i + 1 < p.pages ? p.pageStarts[i + 1] : p.endStart);
  const ring = p.rings.some(([a, d]) => t >= a && t <= a + d);
  const shake = ring ? 2.2 * Math.sin(t * 85) : 0;

  // end page
  const endIn = interpolate(t, [p.endStart, p.endStart + 0.8], [0, 1], { ...clamp, easing: soft });

  return (
    <Paper>
      {t < p.hookEnd ? (
        <AbsoluteFill style={{ opacity: titleIn * titleOut }}>
          <Header book={p.book} author={p.author} />
          <div style={{ position: "absolute", top: 640, left: PAD, right: PAD, textAlign: "center" }}>
            <div style={{ font: "600 26px Inter", letterSpacing: "0.34em", color: RED, marginBottom: 60 }}>
              FROM {p.book.toUpperCase()}
            </div>
            <div style={{ font: "italic 500 92px/1.12 Corm", color: `rgb(${INK})` }}>{p.hook}</div>
            <div style={{ width: 90, height: 5, background: RED, margin: "64px auto 0" }} />
          </div>
          <Footer handle={p.handle} />
        </AbsoluteFill>
      ) : null}

      {Array.from({ length: p.pages }).map((_, pi) => {
        const a = p.pageStarts[pi];
        const b = pageEnd(pi);
        if (t < a - 0.6 || t > b + 0.6) return null;
        const inn = interpolate(t, [a - 0.5, a + 0.1], [0, 1], { ...clamp, easing: soft });
        const out = interpolate(t, [b - 0.35, b + 0.25], [1, 0], clamp);
        const rise = interpolate(t, [a - 0.5, a + 0.1, b - 0.35, b + 0.25], [36, 0, 0, -36], clamp);
        const zoom = interpolate(t, [a, b], [1, 1.02], clamp);
        return (
          <AbsoluteFill key={pi} style={{ opacity: Math.min(inn, out) }}>
            <Header book={p.book} author={p.author} />
            <div
              style={{
                position: "absolute", top: 360, left: PAD, right: PAD,
                translate: `${shake}px ${rise}px`, scale: zoom, transformOrigin: "50% 0%",
              }}
            >
              {p.lines.filter((l) => l.page === pi).map((l, i) => (
                <Paragraph key={i} line={l} t={t} />
              ))}
            </div>
            <Footer handle={p.handle} />
          </AbsoluteFill>
        );
      })}

      {t >= p.endStart ? (
        <AbsoluteFill style={{ opacity: endIn, alignItems: "center" }}>
          <Img
            src={staticFile(p.cover)}
            style={{
              position: "absolute", top: 260, width: 560,
              boxShadow: "0 30px 60px rgba(40,30,15,0.45)",
              translate: `0 ${interpolate(t, [p.endStart, p.endStart + 1], [24, 0], { ...clamp, easing: soft })}px`,
            }}
          />
          <div style={{ position: "absolute", top: 1240, left: PAD, right: PAD, textAlign: "center" }}>
            {p.end.kicker ? (
              <div style={{ font: "600 26px Inter", letterSpacing: "0.34em", color: RED, marginBottom: 28 }}>
                {p.end.kicker.toUpperCase()}
              </div>
            ) : null}
            <div style={{ font: "600 84px/1.05 Corm", color: `rgb(${INK})` }}>{p.end.title ?? p.book}</div>
            <div style={{ width: 90, height: 5, background: RED, margin: "34px auto" }} />
            <div style={{ font: "500 36px/1.5 Inter", color: MUTED, whiteSpace: "pre-line" }}>{p.end.body}</div>
          </div>
          <Footer handle={p.handle} />
        </AbsoluteFill>
      ) : null}
    </Paper>
  );
};
