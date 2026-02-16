import { cn, fmtMoney, fmtPct, fmtInt, actionColor, returnColor } from "./utils";

describe("cn", () => {
  it("merges class names", () => {
    expect(cn("px-2", "py-1")).toBe("px-2 py-1");
  });

  it("resolves Tailwind conflicts", () => {
    expect(cn("px-2", "px-4")).toBe("px-4");
  });

  it("handles conditional values", () => {
    const hide = false;
    expect(cn("base", hide && "hidden", "visible")).toBe("base visible");
  });
});

describe("fmtMoney", () => {
  it("returns em-dash for null", () => {
    expect(fmtMoney(null)).toBe("\u2014");
  });

  it("returns em-dash for undefined", () => {
    expect(fmtMoney(undefined)).toBe("\u2014");
  });

  it("formats small values as standard USD", () => {
    const result = fmtMoney(1234.56);
    expect(result).toBe("$1,234.56");
  });

  it("formats values >= 1M as compact", () => {
    const result = fmtMoney(2_500_000);
    expect(result).toMatch(/\$2\.5M/);
  });

  it("formats negative values", () => {
    const result = fmtMoney(-50.3);
    expect(result).toBe("-$50.30");
  });

  it("formats zero", () => {
    expect(fmtMoney(0)).toBe("$0.00");
  });
});

describe("fmtPct", () => {
  it("returns em-dash for null", () => {
    expect(fmtPct(null)).toBe("\u2014");
  });

  it("returns em-dash for undefined", () => {
    expect(fmtPct(undefined)).toBe("\u2014");
  });

  it("formats percentage (divides by 100)", () => {
    expect(fmtPct(50)).toBe("50.0%");
  });

  it("formats negative percentage", () => {
    expect(fmtPct(-12.5)).toBe("-12.5%");
  });

  it("formats zero", () => {
    expect(fmtPct(0)).toBe("0.0%");
  });
});

describe("fmtInt", () => {
  it("returns em-dash for null", () => {
    expect(fmtInt(null)).toBe("\u2014");
  });

  it("formats integer with commas", () => {
    expect(fmtInt(1234567)).toBe("1,234,567");
  });

  it("rounds decimals", () => {
    expect(fmtInt(99.7)).toBe("100");
  });
});

describe("actionColor", () => {
  it("returns green for buy", () => {
    expect(actionColor("Buy")).toContain("text-good");
  });

  it("returns green for strong buy", () => {
    expect(actionColor("Strong Buy")).toContain("text-good");
  });

  it("returns red for sell", () => {
    expect(actionColor("Sell")).toContain("text-bad");
  });

  it("returns red for strong sell", () => {
    expect(actionColor("Strong Sell")).toContain("text-bad");
  });

  it("returns amber for hold", () => {
    expect(actionColor("Hold")).toContain("text-warn");
  });
});

describe("returnColor", () => {
  it("returns slate for null", () => {
    expect(returnColor(null)).toBe("text-slate-500");
  });

  it("returns slate for undefined", () => {
    expect(returnColor(undefined)).toBe("text-slate-500");
  });

  it("returns green for > 5", () => {
    expect(returnColor(10)).toContain("text-good");
  });

  it("returns red for < -5", () => {
    expect(returnColor(-10)).toContain("text-bad");
  });

  it("returns amber for values between -5 and 5", () => {
    expect(returnColor(3)).toContain("text-warn");
  });

  it("returns amber for exactly 5", () => {
    expect(returnColor(5)).toContain("text-warn");
  });

  it("returns amber for exactly -5", () => {
    expect(returnColor(-5)).toContain("text-warn");
  });
});
