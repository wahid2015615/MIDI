import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { formatApiDetail, isAbortError, resolveApiBase } from "./studioApi";

describe("formatApiDetail", () => {
  it("returns fallback for null", () => {
    expect(formatApiDetail(null, "fail")).toBe("fail");
  });

  it("returns a string detail", () => {
    expect(formatApiDetail("bad token")).toBe("bad token");
  });

  it("joins FastAPI validation arrays", () => {
    const msg = formatApiDetail([
      { loc: ["body", "bpm"], msg: "Input should be less than or equal to 300" },
      { loc: ["body", "prompt"], msg: "String too long" },
    ]);
    expect(msg).toContain("bpm:");
    expect(msg).toContain("prompt:");
  });

  it("reads object msg", () => {
    expect(formatApiDetail({ msg: "nope" })).toBe("nope");
  });
});

describe("isAbortError", () => {
  it("detects AbortError name", () => {
    expect(isAbortError({ name: "AbortError" })).toBe(true);
    expect(isAbortError({ name: "CanceledError" })).toBe(true);
    expect(isAbortError(new Error("x"))).toBe(false);
    expect(isAbortError(null)).toBe(false);
  });
});

describe("resolveApiBase", () => {
  const originalEnv = process.env.NEXT_PUBLIC_API_URL;

  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  afterEach(() => {
    if (originalEnv === undefined) {
      delete process.env.NEXT_PUBLIC_API_URL;
    } else {
      process.env.NEXT_PUBLIC_API_URL = originalEnv;
    }
  });

  it("uses env when window is undefined-like via configured URL", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000";
    expect(resolveApiBase()).toMatch(/8000/);
  });

  it("rewrites loopback API host to the LAN page host", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("window", {
      location: { hostname: "192.168.1.20" },
    });
    expect(resolveApiBase()).toBe("http://192.168.1.20:8000");
  });

  it("keeps loopback when the page is also loopback", () => {
    process.env.NEXT_PUBLIC_API_URL = "http://127.0.0.1:8000";
    vi.stubGlobal("window", {
      location: { hostname: "localhost" },
    });
    expect(resolveApiBase()).toBe("http://127.0.0.1:8000");
  });
});
