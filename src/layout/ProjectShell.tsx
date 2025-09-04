import React from "react";
import Topbar from "../components/Topbar";
import ChatPane from "../components/ChatPane";
import PreviewFrame from "../components/PreviewFrame";

export default function ProjectShell() {
  return (
    <div className="app-shell min-h-screen">
      <Topbar />
      <main className="max-w-7xl mx-auto px-4 lg:px-8 py-6 grid grid-cols-1 lg:grid-cols-3 gap-6">
        <section className="lg:col-span-1">
          <div className="card h-full">
            <ChatPane />
          </div>
        </section>

        <section className="lg:col-span-2 flex flex-col gap-4">
          <div className="card flex-1">
            <PreviewFrame />
          </div>
          <div className="flex gap-3 justify-end">
            <button className="btn-hero">Run</button>
            <button className="px-4 py-2 rounded-md border border-gray-200">
              Save
            </button>
          </div>
        </section>
      </main>
    </div>
  );
}