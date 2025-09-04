import React from "react";

export default function Topbar() {
  return (
    <header className="w-full shadow-sm">
      <div className="max-w-7xl mx-auto px-4 lg:px-8 py-4 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-lg"
            style={{
              background:
                "linear-gradient(135deg,var(--color-primary),var(--color-accent))",
              boxShadow: "var(--shadow-glow)",
            }}
          />
          <div>
            <div className="text-lg font-semibold">Lovable Editor</div>
            <div className="text-sm text-gray-500">
              React · Vite · TypeScript · Tailwind
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <div className="hidden sm:block text-sm text-gray-600">
            Preview shows live changes in the iframe
          </div>
          <button className="btn-hero">New Project</button>
        </div>
      </div>
    </header>
  );
}