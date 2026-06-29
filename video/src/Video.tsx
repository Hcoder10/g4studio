import React from "react";
import {
  AbsoluteFill, Sequence, Img, OffthreadVideo, staticFile,
  useCurrentFrame, useVideoConfig, interpolate, spring, Easing,
} from "remotion";

const C = {
  bg: "#070b16", ink: "#eaf0ff", dim: "#8aa0c8",
  blue: "#39b6ff", cyan: "#36f0d0", mag: "#ff4fd8", gold: "#ffcf48",
};
const FONT = '"Segoe UI", system-ui, -apple-system, "Helvetica Neue", sans-serif';

// ---- helpers ---------------------------------------------------------------
const useReveal = (delay = 0, dist = 26) => {
  const f = useCurrentFrame();
  const { fps } = useVideoConfig();
  const p = spring({ frame: f - delay, fps, config: { damping: 200, mass: 0.7 } });
  return { opacity: p, transform: `translateY(${(1 - p) * dist}px)` } as React.CSSProperties;
};
const glow = (c: string, s = 24) => `0 0 ${s}px ${c}aa, 0 0 ${s * 2}px ${c}55`;

const Reveal: React.FC<{ delay?: number; dist?: number; style?: React.CSSProperties; children: React.ReactNode }> =
  ({ delay = 0, dist = 26, style, children }) => (
    <div style={{ ...useReveal(delay, dist), ...style }}>{children}</div>
  );

const Bg: React.FC = () => {
  const f = useCurrentFrame();
  const a = Math.sin(f / 70) * 120;
  const b = Math.cos(f / 90) * 100;
  return (
    <AbsoluteFill style={{ background: C.bg }}>
      <AbsoluteFill style={{
        background: `radial-gradient(820px 820px at ${960 + a}px ${300 + b}px, #11214a 0%, transparent 60%),
                     radial-gradient(900px 900px at ${500 - a}px ${860 - b}px, #1a1140 0%, transparent 62%)`,
      }} />
      <AbsoluteFill style={{
        backgroundImage:
          "linear-gradient(#ffffff08 1px, transparent 1px), linear-gradient(90deg, #ffffff08 1px, transparent 1px)",
        backgroundSize: "64px 64px", maskImage: "radial-gradient(circle at 50% 45%, #000 30%, transparent 80%)",
      }} />
    </AbsoluteFill>
  );
};

const Kicker: React.FC<{ children: React.ReactNode; color?: string; delay?: number }> = ({ children, color = C.cyan, delay = 0 }) => (
  <Reveal delay={delay}>
    <div style={{
      color, fontSize: 26, fontWeight: 700, letterSpacing: 6, textTransform: "uppercase",
      textShadow: glow(color, 10),
    }}>{children}</div>
  </Reveal>
);

// ---- scenes ----------------------------------------------------------------
const Intro: React.FC = () => {
  const f = useCurrentFrame();
  const ring = interpolate(f, [0, 40], [0, 1], { extrapolateRight: "clamp", easing: Easing.out(Easing.cubic) });
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 22 }}>
      <div style={{
        width: 150, height: 150, borderRadius: 30, border: `3px solid ${C.blue}`,
        boxShadow: glow(C.blue, 30), transform: `scale(${ring}) rotate(${(1 - ring) * 40}deg)`,
        display: "flex", justifyContent: "center", alignItems: "center", opacity: ring,
      }}>
        <div style={{ fontSize: 76, fontWeight: 900, color: C.ink }}>G4</div>
      </div>
      <Reveal delay={18}><div style={{ fontSize: 104, fontWeight: 900, color: C.ink, letterSpacing: 2, textShadow: glow(C.blue, 18) }}>
        G4&nbsp;STUDIO</div></Reveal>
      <Reveal delay={28}><div style={{ fontSize: 40, color: C.dim, fontWeight: 600 }}>
        Roblox as a robot-data factory</div></Reveal>
      <Reveal delay={40}><div style={{ fontSize: 24, color: C.cyan, letterSpacing: 4, marginTop: 8 }}>
        GEMMA-4&nbsp;&nbsp;×&nbsp;&nbsp;CEREBRAS</div></Reveal>
    </AbsoluteFill>
  );
};

const Hook: React.FC = () => (
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 28, padding: 120, textAlign: "center" }}>
    <Kicker delay={0} color={C.mag}>the bottleneck</Kicker>
    <Reveal delay={10}><div style={{ fontSize: 64, fontWeight: 800, color: C.ink, maxWidth: 1300, lineHeight: 1.15 }}>
      Robot manipulation runs on <span style={{ color: C.mag, textShadow: glow(C.mag, 12) }}>demonstration data</span>.
      It's slow and expensive to collect.</div></Reveal>
    <Reveal delay={52}><div style={{ fontSize: 50, fontWeight: 700, color: C.cyan, marginTop: 26, textShadow: glow(C.cyan, 12) }}>
      So we made collecting it a game.</div></Reveal>
  </AbsoluteFill>
);

const Arm: React.FC = () => (
  <AbsoluteFill>
    <OffthreadVideo src={staticFile("arm.mp4")} playbackRate={1} muted style={{ position: "absolute", width: "100%", height: "100%", objectFit: "contain" }} />
    <AbsoluteFill style={{ justifyContent: "flex-end", padding: 90 }}>
      <Reveal delay={8}><div style={{ fontSize: 46, fontWeight: 800, color: C.ink, textShadow: glow(C.blue, 12) }}>
        A faithful SO-101 arm</div></Reveal>
      <Reveal delay={20}><div style={{ fontSize: 27, color: C.dim, marginTop: 6 }}>
        reconstructed from the official URDF · exact joints &amp; limits · damped-least-squares IK</div></Reveal>
    </AbsoluteFill>
  </AbsoluteFill>
);

const games = ["Coin Sweep", "Star Collector", "Neon Disco Dash", "Cosmic Coin Toss", "Space Push", "Garden Splash", "Coin Storm"];
const Gemma: React.FC = () => (
  <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 24, padding: 90 }}>
    <Kicker color={C.gold}>the generator</Kicker>
    <Reveal delay={8}><div style={{ fontSize: 60, fontWeight: 800, color: C.ink, textAlign: "center", maxWidth: 1300, lineHeight: 1.12 }}>
      <span style={{ color: C.gold, textShadow: glow(C.gold, 12) }}>Gemma-4</span> invents fun games where
      <br />playing the game <span style={{ color: C.cyan }}>is</span> labeling the data.</div></Reveal>
    <div style={{ display: "flex", flexWrap: "wrap", gap: 16, justifyContent: "center", maxWidth: 1400, marginTop: 18 }}>
      {games.map((g, i) => (
        <Reveal key={g} delay={30 + i * 6}>
          <div style={{
            padding: "14px 26px", borderRadius: 14, border: `1.5px solid ${C.blue}66`, color: C.ink,
            fontSize: 28, fontWeight: 700, background: "#0e1730cc", boxShadow: glow(C.blue, 8),
          }}>{g}</div>
        </Reveal>
      ))}
    </div>
    <Reveal delay={84}><div style={{ fontSize: 24, color: C.dim, marginTop: 14 }}>
      designed, coded, syntax + runtime-validated, packaged — in seconds</div></Reveal>
  </AbsoluteFill>
);

const Loop: React.FC = () => (
  <AbsoluteFill style={{ padding: 90, flexDirection: "row", alignItems: "center", gap: 60 }}>
    <div style={{ flex: 1.05 }}>
      <Kicker color={C.cyan}>data, for free</Kicker>
      <Reveal delay={8}><div style={{ fontSize: 56, fontWeight: 800, color: C.ink, marginTop: 14, lineHeight: 1.12 }}>
        Every playthrough is a<br /><span style={{ color: C.cyan, textShadow: glow(C.cyan, 12) }}>labeled demonstration.</span></div></Reveal>
      <Reveal delay={26} style={{ marginTop: 40 }}>
        <div style={{ display: "flex", gap: 40 }}>
          {[["192", "episodes"], ["14", "games"], ["73k", "frames"]].map(([n, l]) => (
            <div key={l}>
              <div style={{ fontSize: 76, fontWeight: 900, color: C.blue, textShadow: glow(C.blue, 14) }}>{n}</div>
              <div style={{ fontSize: 24, color: C.dim, letterSpacing: 2 }}>{l.toUpperCase()}</div>
            </div>
          ))}
        </div>
      </Reveal>
      <Reveal delay={44}><div style={{ fontSize: 24, color: C.dim, marginTop: 30 }}>
        from real human play — verified live on the server</div></Reveal>
    </div>
    <Reveal delay={20} style={{ flex: 1 }}>
      <Img src={staticFile("dataset_bars.png")} style={{ width: "100%" }} />
    </Reveal>
  </AbsoluteFill>
);

const DataSci: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ padding: 80, flexDirection: "column", justifyContent: "center", gap: 18 }}>
      <Kicker color={C.blue}>real training data</Kicker>
      <Reveal delay={6}><div style={{ fontSize: 50, fontWeight: 800, color: C.ink, lineHeight: 1.1 }}>
        Recorded in the arm's native <span style={{ color: C.blue }}>joint space</span> → exported to <span style={{ color: C.cyan }}>LeRobot v2.1</span>.</div></Reveal>
      <div style={{ display: "flex", gap: 40, marginTop: 10, alignItems: "center" }}>
        <Reveal delay={20} style={{ flex: 1 }}>
          <Img src={staticFile("trace.png")} style={{ width: "100%" }} />
          <div style={{ color: C.dim, fontSize: 22, textAlign: "center" }}>joint angles + actions, per frame, labeled by skill</div>
        </Reveal>
        <div style={{ flex: 1, opacity: interpolate(f, [40, 60], [0, 1], { extrapolateRight: "clamp" }) }}>
          <Img src={staticFile("bc_r2.png")} style={{ width: "100%" }} />
          <div style={{ color: C.dim, fontSize: 22, textAlign: "center" }}>a behavior-cloning policy recovers the actions</div>
        </div>
      </div>
      <Reveal delay={64}><div style={{ fontSize: 38, fontWeight: 800, color: C.cyan, textAlign: "center", textShadow: glow(C.cyan, 10) }}>
        Learnable — R² 0.94–1.0, 48× better than baseline.</div></Reveal>
    </AbsoluteFill>
  );
};

const Generalize: React.FC = () => (
  <AbsoluteFill style={{ padding: 80, flexDirection: "row", alignItems: "center", gap: 50 }}>
    <Reveal delay={16} style={{ flex: 0.85 }}>
      <Img src={staticFile("reach.png")} style={{ width: "100%" }} />
    </Reveal>
    <div style={{ flex: 1.1 }}>
      <Kicker color={C.mag}>any robot</Kicker>
      <Reveal delay={8}><div style={{ fontSize: 56, fontWeight: 800, color: C.ink, marginTop: 12, lineHeight: 1.12 }}>
        Point it at a new arm.</div></Reveal>
      <Reveal delay={22}><div style={{ fontSize: 30, color: C.dim, marginTop: 18, lineHeight: 1.4, maxWidth: 760 }}>
        One command derives the kinematics from a URDF and auto-finds a working pose.</div></Reveal>
      <Reveal delay={40} style={{ marginTop: 34, display: "flex", gap: 50 }}>
        {[["SO-101", "93%"], ["SO-100", "100%"]].map(([n, r]) => (
          <div key={n}>
            <div style={{ fontSize: 30, color: C.ink, fontWeight: 700 }}>{n}</div>
            <div style={{ fontSize: 58, fontWeight: 900, color: C.mag, textShadow: glow(C.mag, 12) }}>{r}</div>
            <div style={{ fontSize: 20, color: C.dim, letterSpacing: 2 }}>WORKSPACE REACH</div>
          </div>
        ))}
      </Reveal>
    </div>
  </AbsoluteFill>
);

const Outro: React.FC = () => {
  const f = useCurrentFrame();
  return (
    <AbsoluteFill style={{ justifyContent: "center", alignItems: "center", flexDirection: "column", gap: 26, textAlign: "center" }}>
      <Reveal delay={4}><div style={{ fontSize: 90, fontWeight: 900, color: C.ink, letterSpacing: 2, textShadow: glow(C.blue, 18) }}>
        G4&nbsp;STUDIO</div></Reveal>
      <Reveal delay={16}><div style={{ fontSize: 44, color: C.cyan, fontWeight: 700, maxWidth: 1200, textShadow: glow(C.cyan, 8) }}>
        Play becomes the data that teaches robots.</div></Reveal>
      <Reveal delay={34}><div style={{ fontSize: 26, color: C.dim, letterSpacing: 3, marginTop: 18 }}>
        Gemma-4 &nbsp;·&nbsp; Cerebras &nbsp;·&nbsp; SO-101 &nbsp;·&nbsp; LeRobot</div></Reveal>
      <div style={{ position: "absolute", bottom: 60, width: 220, height: 3, background: C.blue, boxShadow: glow(C.blue, 12),
        transform: `scaleX(${interpolate(f, [10, 40], [0, 1], { extrapolateRight: "clamp" })})` }} />
    </AbsoluteFill>
  );
};

// ---- timeline --------------------------------------------------------------
export const Video: React.FC = () => (
  <AbsoluteFill style={{ background: C.bg, fontFamily: FONT }}>
    <Bg />
    <Sequence durationInFrames={90}><Intro /></Sequence>
    <Sequence from={90} durationInFrames={130}><Hook /></Sequence>
    <Sequence from={220} durationInFrames={170}><Arm /></Sequence>
    <Sequence from={390} durationInFrames={170}><Gemma /></Sequence>
    <Sequence from={560} durationInFrames={160}><Loop /></Sequence>
    <Sequence from={720} durationInFrames={190}><DataSci /></Sequence>
    <Sequence from={910} durationInFrames={130}><Generalize /></Sequence>
    <Sequence from={1040} durationInFrames={100}><Outro /></Sequence>
  </AbsoluteFill>
);
