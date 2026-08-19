import type { ReactNode } from "react";

function Glyph({ children }: { children: ReactNode }) {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
      className="type-glyph"
    >
      {children}
    </svg>
  );
}

function Vinyl() {
  return (
    <Glyph>
      <circle cx="12" cy="12" r="9" />
      <circle cx="12" cy="12" r="5.4" />
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
    </Glyph>
  );
}

function VinylNote() {
  return (
    <Glyph>
      <circle cx="10.5" cy="13" r="7.2" />
      <circle cx="10.5" cy="13" r="1.35" fill="currentColor" stroke="none" />
      <path d="M16.2 5.2v8.4" />
      <ellipse cx="14.6" cy="13.6" rx="1.6" ry="1.2" fill="currentColor" stroke="none" />
    </Glyph>
  );
}

function Eighth() {
  return (
    <Glyph>
      <ellipse cx="8.2" cy="17.2" rx="2.3" ry="1.7" fill="currentColor" stroke="none" />
      <path d="M10.5 17.2V6.4l7.2-1.2v10.8" />
      <ellipse cx="15.4" cy="16" rx="2.3" ry="1.7" fill="currentColor" stroke="none" />
      <path d="M10.5 6.4c2.4 1.6 4.8 1.6 7.2 0" />
    </Glyph>
  );
}

function Piano() {
  return (
    <Glyph>
      <rect x="3" y="7" width="18" height="11" rx="1.4" />
      <path d="M3 13.5h18" />
      <path d="M7.2 7v6.5M10.8 7v6.5M14.4 7v6.5M18 7v6.5" />
    </Glyph>
  );
}

function Waves() {
  return (
    <Glyph>
      <path d="M3 8c1.8-3 3.4-3 5.2 0s3.4 3 5.2 0 3.4-3 5.2 0" />
      <path d="M3 12.5c1.8-3 3.4-3 5.2 0s3.4 3 5.2 0 3.4-3 5.2 0" />
      <path d="M3 17c1.8-3 3.4-3 5.2 0s3.4 3 5.2 0 3.4-3 5.2 0" />
    </Glyph>
  );
}

function ElectricGuitar() {
  return (
    <Glyph>
      <path d="M8 16.5c-2.4 2.4-5.2 1-5.2-1.2 0-2.2 2.6-3.4 4.4-1.6L15.5 5.4l3.2 3.2-8.3 8.3z" />
      <path d="M15.7 5.2l3.3 3.3M18.2 7.2l2.3-2.3M20.5 4.9l.8.8" />
      <circle cx="9.2" cy="15.2" r="1.1" />
    </Glyph>
  );
}

function AcousticGuitar() {
  return (
    <Glyph>
      <circle cx="9.2" cy="14.2" r="5.4" />
      <circle cx="9.2" cy="14.2" r="1.8" />
      <path d="M13.2 10.4 20 3.6M20 3.6v3.2M20 3.6h-3.2" />
    </Glyph>
  );
}

function Bass() {
  return (
    <Glyph>
      <circle cx="8.5" cy="15" r="5" />
      <path d="M12.4 11.2 20 3.6M7.2 15h2.6M8.5 13.7v2.6" />
      <path d="M16.4 7.2c1.6 1.6 1.6 1.6 0 3.2" />
    </Glyph>
  );
}

function Drums() {
  return (
    <Glyph>
      <ellipse cx="12" cy="9.2" rx="7.5" ry="3.2" />
      <path d="M4.5 9.2v6.2c0 1.8 3.4 3.2 7.5 3.2s7.5-1.4 7.5-3.2V9.2" />
      <path d="M4 5.5 8.5 9.4M20 5.5 15.5 9.4" />
    </Glyph>
  );
}

function Sax() {
  return (
    <Glyph>
      <path d="M7 4.5h3.2v8.2c0 3.8-2 6.8-5.4 7.6" />
      <path d="M10.2 7.8h4.8c2.6 0 4.6 2 4.6 4.4 0 3.2-2.4 5.2-5.6 5.2H8" />
      <circle cx="6.4" cy="20" r="1.3" />
    </Glyph>
  );
}

function Violin() {
  return (
    <Glyph>
      <path d="M8.2 14.5c-2.6 2.6-2.2 5.8.6 6.4 2.6.6 4.4-1.6 4.4-1.6l6.6-6.6c.8-2.8-.8-4.8-2.6-4.8-1.4 0-2.2.8-2.2.8" />
      <path d="M14.8 8.2 20 3M19.2 3.8 21 5.6" />
      <path d="M10.4 13.2l3.6 3.6" />
    </Glyph>
  );
}

function Synth() {
  return (
    <Glyph>
      <rect x="3" y="6" width="18" height="12" rx="1.6" />
      <path d="M6 12h2.2M10 12h2.2M14 12h2.2M18 12h.8" />
      <circle cx="7.1" cy="9" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="11.1" cy="9" r="0.9" fill="currentColor" stroke="none" />
      <circle cx="15.1" cy="9" r="0.9" fill="currentColor" stroke="none" />
    </Glyph>
  );
}

function Clapper() {
  return (
    <Glyph>
      <path d="M4 10h16v9.5H4z" />
      <path d="M4 10 8.2 4.6 20 8.2 16.2 10" />
      <path d="M8.4 5 11 10M13.2 6.4 15.6 10" />
    </Glyph>
  );
}

function House() {
  return (
    <Glyph>
      <path d="M4 11.5 12 4l8 7.5" />
      <path d="M6.5 10.8V20h11V10.8" />
      <path d="M10 20v-5.2h4V20" />
    </Glyph>
  );
}

function Gear() {
  return (
    <Glyph>
      <circle cx="12" cy="12" r="3.1" />
      <path d="M12 3.6v2.3M12 18.1v2.3M3.6 12h2.3M18.1 12h2.3M6.1 6.1l1.6 1.6M16.3 16.3l1.6 1.6M6.1 17.9l1.6-1.6M16.3 7.7l1.6-1.6" />
    </Glyph>
  );
}

function Speaker() {
  return (
    <Glyph>
      <rect x="4" y="4.5" width="10" height="15" rx="1.4" />
      <circle cx="9" cy="9.2" r="2" />
      <circle cx="9" cy="15.4" r="3" />
      <path d="M16.2 8.2c1.8 1.2 1.8 6.4 0 7.6" />
    </Glyph>
  );
}

function Mic() {
  return (
    <Glyph>
      <rect x="9" y="3.5" width="6" height="10" rx="3" />
      <path d="M7 11.2a5 5 0 0 0 10 0M12 16.2V20M9 20h6" />
    </Glyph>
  );
}

function Sparkles() {
  return (
    <Glyph>
      <path d="M12 3.5 13.4 8.6 18.5 10 13.4 11.4 12 16.5 10.6 11.4 5.5 10 10.6 8.6z" />
      <path d="M18.5 15.2 19.2 17.4 21.4 18.1 19.2 18.8 18.5 21 17.8 18.8 15.6 18.1 17.8 17.4z" />
    </Glyph>
  );
}

function Harmonica() {
  return (
    <Glyph>
      <rect x="3" y="8.5" width="18" height="7" rx="1.4" />
      <path d="M7 8.5v7M11 8.5v7M15 8.5v7M19 8.5v7" />
    </Glyph>
  );
}

function Palm() {
  return (
    <Glyph>
      <path d="M12 21V10" />
      <path d="M12 11c-3.4-3.6-6.6-3-7.4-1.4M12 12.2c3.4-3.8 6.8-3 7.6-1.2M12 9.4c-2-4.4-5.4-5-6.6-3.6M12 9.4c2.2-4.6 5.6-5 6.8-3.5" />
    </Glyph>
  );
}

function Chat() {
  return (
    <Glyph>
      <path d="M5 6.5h14v9.2H9.2L5 19.2z" />
      <path d="M8.5 10.4h7M8.5 13.2h4.6" />
    </Glyph>
  );
}

function ChordGrid() {
  return (
    <Glyph>
      <rect x="4" y="5" width="16" height="14" rx="1.4" />
      <path d="M4 10.2h16M4 14.4h16M9.3 5v14M14.7 5v14" />
    </Glyph>
  );
}

function NoteList() {
  return (
    <Glyph>
      <path d="M5 7h8M5 12h6M5 17h7" />
      <ellipse cx="17.4" cy="17.2" rx="2.1" ry="1.5" fill="currentColor" stroke="none" />
      <path d="M19.5 17.2V8.4" />
    </Glyph>
  );
}

function Merge() {
  return (
    <Glyph>
      <path d="M8 5v5.5c0 2 1.6 3.5 3.6 3.5h.8c2 0 3.6-1.5 3.6-3.5V5" />
      <path d="M12 14v5.5" />
    </Glyph>
  );
}

function Stacks() {
  return (
    <Glyph>
      <rect x="5" y="4.5" width="14" height="4" rx="1" />
      <rect x="5" y="10" width="14" height="4" rx="1" />
      <rect x="5" y="15.5" width="14" height="4" rx="1" />
    </Glyph>
  );
}

function Smile() {
  return (
    <Glyph>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M8.4 13.6c.9 2 2.2 3 3.6 3s2.7-1 3.6-3" />
      <circle cx="9.2" cy="10" r="0.8" fill="currentColor" stroke="none" />
      <circle cx="14.8" cy="10" r="0.8" fill="currentColor" stroke="none" />
    </Glyph>
  );
}

function Tear() {
  return (
    <Glyph>
      <path d="M12 4.4c3.8 4.6 6.2 7.4 6.2 10.4A6.2 6.2 0 0 1 12 21a6.2 6.2 0 0 1-6.2-6.2c0-3 2.4-5.8 6.2-10.4z" />
    </Glyph>
  );
}

function Leaf() {
  return (
    <Glyph>
      <path d="M5 19c8-1 13-7 14-14-7 1-13 6-14 14z" />
      <path d="M8.5 15.5 16 8" />
    </Glyph>
  );
}

function Bolt() {
  return (
    <Glyph>
      <path d="M13 3 6.5 13.5h5.2L11 21 17.6 10.4h-5.2z" />
    </Glyph>
  );
}

function Mountain() {
  return (
    <Glyph>
      <path d="M3 19h18L14.5 6.5 11 12 8.8 8.8z" />
    </Glyph>
  );
}

function Moon() {
  return (
    <Glyph>
      <path d="M15.4 4.8A8.2 8.2 0 1 0 19.2 15 6.4 6.4 0 0 1 15.4 4.8z" />
    </Glyph>
  );
}

function Heart() {
  return (
    <Glyph>
      <path d="M12 19.4s-7.2-4.4-7.2-9.2A4 4 0 0 1 12 8.2 4 4 0 0 1 19.2 10.2c0 4.8-7.2 9.2-7.2 9.2z" />
    </Glyph>
  );
}

function Sun() {
  return (
    <Glyph>
      <circle cx="12" cy="12" r="3.4" />
      <path d="M12 3.6v2M12 18.4v2M3.6 12h2M18.4 12h2M6.1 6.1l1.4 1.4M16.5 16.5l1.4 1.4M6.1 17.9l1.4-1.4M16.5 7.5l1.4-1.4" />
    </Glyph>
  );
}

function Cloud() {
  return (
    <Glyph>
      <path d="M7.4 17.5h10.2A3.6 3.6 0 0 0 18 10.6 5.2 5.2 0 0 0 8.2 9.4 3.7 3.7 0 0 0 7.4 17.5z" />
      <path d="M8.5 20.2h.1M12 20.6h.1M15.5 20.2h.1" />
    </Glyph>
  );
}

function Fire() {
  return (
    <Glyph>
      <path d="M12 3.8s2.8 3.2 2.8 6.4c0 1.4-.6 2.5-1.5 3.2 2.6-.2 4.7-2.2 4.7-5.2 0 5-2.6 8.8-6 8.8s-6-3.6-6-7.6C6 7.2 9.4 5 12 3.8z" />
    </Glyph>
  );
}

function Eye() {
  return (
    <Glyph>
      <path d="M2.8 12s3.6-6.4 9.2-6.4S21.2 12 21.2 12s-3.6 6.4-9.2 6.4S2.8 12 2.8 12z" />
      <circle cx="12" cy="12" r="2.4" />
    </Glyph>
  );
}

function Clock() {
  return (
    <Glyph>
      <circle cx="12" cy="12" r="8.2" />
      <path d="M12 7.4V12l3.2 2" />
    </Glyph>
  );
}

function Bulb() {
  return (
    <Glyph>
      <path d="M9 17.4h6M10 20h4" />
      <path d="M8.2 13.6A5.2 5.2 0 1 1 15.8 13.6C15.8 16 14 16.8 14 18H10c0-1.2-1.8-2-1.8-4.4z" />
    </Glyph>
  );
}

function Alert() {
  return (
    <Glyph>
      <path d="M12 4.2 3.6 19.4h16.8z" />
      <path d="M12 9.4v5.2M12 16.8h.01" />
    </Glyph>
  );
}

function Rain() {
  return (
    <Glyph>
      <path d="M7.4 14.2h9.6A3.4 3.4 0 0 0 17.2 8 4.8 4.8 0 0 0 8.2 7.2 3.5 3.5 0 0 0 7.4 14.2z" />
      <path d="M9 17.4v2.2M12 16.8v2.6M15 17.4v2.2" />
    </Glyph>
  );
}

function ArrowUp() {
  return (
    <Glyph>
      <path d="M12 19.4V5.4M7.2 10.2 12 5.4l4.8 4.8" />
    </Glyph>
  );
}

function Flute() {
  return (
    <Glyph>
      <path d="M3 13.2h16.4a2.2 2.2 0 0 0 0-4.4H8" />
      <circle cx="10.2" cy="11" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="13.2" cy="11" r="0.7" fill="currentColor" stroke="none" />
      <circle cx="16.2" cy="11" r="0.7" fill="currentColor" stroke="none" />
    </Glyph>
  );
}

function normalizeTypeKey(value: string): string {
  return value.trim().toLowerCase().replace(/[_-]+/g, " ").replace(/\s+/g, " ");
}

export function TypeIcon({
  kind,
  name,
}: {
  kind: "style" | "mood" | "mode" | "track" | "instrument" | "midiType";
  name: string;
}) {
  const key = normalizeTypeKey(name);

  if (kind === "mode") {
    if (key === "text") return <Chat />;
    if (key === "chords") return <ChordGrid />;
    if (key === "notes") return <NoteList />;
    return <Eighth />;
  }

  if (kind === "track") {
    if (key === "melody") return <Eighth />;
    if (key === "chords") return <Piano />;
    if (key === "bass") return <Bass />;
    if (key === "drums") return <Drums />;
    return <Eighth />;
  }

  if (kind === "midiType") {
    return key === "0" || key.includes("type 0") ? <Merge /> : <Stacks />;
  }

  if (kind === "instrument") {
    if (key.includes("drum")) return <Drums />;
    if (key.includes("bass")) return <Bass />;
    if (key.includes("guitar")) return <ElectricGuitar />;
    if (key.includes("piano") || key.includes("harpsi") || key.includes("clavi"))
      return <Piano />;
    if (
      key.includes("violin") ||
      key.includes("viola") ||
      key.includes("cello") ||
      key.includes("string") ||
      key.includes("harp")
    )
      return <Violin />;
    if (key.includes("flute") || key.includes("pan")) return <Flute />;
    if (key.includes("sax") || key.includes("oboe") || key.includes("clarinet"))
      return <Sax />;
    if (key.includes("lead") || key.includes("pad") || key.includes("synth"))
      return <Synth />;
    if (key.includes("trumpet") || key.includes("trombone") || key.includes("horn"))
      return <Sax />;
    return <Eighth />;
  }

  if (kind === "mood") {
    if (key === "happy" || key === "playful") return <Smile />;
    if (key === "sad") return <Tear />;
    if (key === "calm" || key === "relaxing") return <Leaf />;
    if (key === "energetic") return <Bolt />;
    if (key === "epic") return <Mountain />;
    if (key === "dark") return <Moon />;
    if (key === "romantic") return <Heart />;
    if (key === "hopeful" || key === "uplifting") return <Sun />;
    if (key === "emotional") return <Heart />;
    if (key === "aggressive" || key === "tense") return key === "tense" ? <Alert /> : <Fire />;
    if (key === "mysterious") return <Eye />;
    if (key === "dreamy") return <Cloud />;
    if (key === "cinematic") return <Clapper />;
    if (key === "melancholic") return <Rain />;
    if (key === "nostalgic") return <Clock />;
    if (key === "inspirational") return <Bulb />;
    return <Eighth />;
  }

  // style — one unique glyph per genre
  if (key === "pop") return <Sparkles />;
  if (key === "rock") return <ElectricGuitar />;
  if (key === "hip hop" || key === "hiphop") return <VinylNote />;
  if (key === "trap") return <Speaker />;
  if (key === "edm") return <Waves />;
  if (key === "house") return <House />;
  if (key === "techno") return <Gear />;
  if (key === "lo fi" || key === "lofi") return <Vinyl />;
  if (key === "jazz") return <Sax />;
  if (key === "blues") return <Harmonica />;
  if (key === "classical") return <Piano />;
  if (key === "orchestral") return <Violin />;
  if (key === "cinematic") return <Clapper />;
  if (key === "ambient") return <Waves />;
  if (key === "synthwave") return <Synth />;
  if (key === "funk") return <Bass />;
  if (key === "r&b" || key === "r and b" || key === "rnb") return <Mic />;
  if (key === "country") return <AcousticGuitar />;
  if (key === "folk") return <AcousticGuitar />;
  if (key === "reggae") return <Palm />;
  return <Eighth />;
}
