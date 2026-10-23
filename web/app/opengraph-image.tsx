import { ImageResponse } from "next/og";

export const alt = "Daily Berlin Jobs — engineering jobs in Berlin, updated daily";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#f8f5ec",
          color: "#17201e",
          padding: "76px",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", gap: "18px" }}>
          <div
            style={{
              width: "54px",
              height: "54px",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              borderRadius: "16px",
              background: "#17201e",
              color: "#fff",
              fontSize: "30px",
              fontWeight: 800,
            }}
          >
            B
          </div>
          <div style={{ fontSize: "28px", fontWeight: 700 }}>Daily Berlin Jobs</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
          <div style={{ color: "#0f766e", fontSize: "20px", fontWeight: 700, letterSpacing: "3px" }}>
            BERLIN · ENGINEERING
          </div>
          <div style={{ maxWidth: "930px", fontSize: "68px", fontWeight: 800, lineHeight: 1.08 }}>
            Engineering jobs in Berlin, updated daily
          </div>
        </div>
        <div style={{ color: "#6f7774", fontSize: "22px" }}>
          Software · Data · Platform · Security · Mobile · Embedded
        </div>
      </div>
    ),
    size,
  );
}
