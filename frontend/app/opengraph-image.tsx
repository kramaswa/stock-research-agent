import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt = "Stock Research Agent";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default async function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          background: "#f9fafb",
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          padding: "60px",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            background: "#eff6ff",
            color: "#2563eb",
            fontSize: "18px",
            fontWeight: "600",
            padding: "10px 20px",
            borderRadius: "100px",
            marginBottom: "28px",
          }}
        >
          Multi-Agent Stock Research
        </div>
        <div
          style={{
            fontSize: "68px",
            fontWeight: "700",
            color: "#111827",
            textAlign: "center",
            marginBottom: "20px",
            lineHeight: 1.1,
          }}
        >
          Stock Research Agent
        </div>
        <div
          style={{
            fontSize: "26px",
            color: "#6b7280",
            textAlign: "center",
            maxWidth: "780px",
          }}
        >
          AI agents to help you find, analyze, and hold stocks with conviction.
        </div>
        <div style={{ display: "flex", gap: "16px", marginTop: "48px" }}>
          {["Discover", "Research", "Hold Check"].map((label) => (
            <div
              key={label}
              style={{
                background: "white",
                border: "1px solid #e5e7eb",
                borderRadius: "12px",
                padding: "12px 28px",
                fontSize: "20px",
                fontWeight: "600",
                color: "#374151",
              }}
            >
              {label}
            </div>
          ))}
        </div>
      </div>
    ),
    { ...size }
  );
}
