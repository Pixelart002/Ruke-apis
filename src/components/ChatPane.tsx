import React, { useState } from "react";

const SAMPLE = [
  { id: 1, who: "You", text: "Hi Lovable — scaffold a project with a chat + preview." },
  { id: 2, who: "Lovable", text: "Got it — I created the design system tokens and core layout." },
];

export default function ChatPane() {
  const [messages, setMessages] = useState(SAMPLE);
  const [value, setValue] = useState("");

  function onSend() {
    if (!value.trim()) return;
    setMessages((m) => [...m, { id: Date.now(), who: "You", text: value }]);
    setValue("");
  }

  return (
    <div className="flex flex-col h-[70vh]">
      <div className="flex-1 overflow-auto pr-2">
        <ul className="space-y-3">
          {messages.map((m) => (
            <li
              key={m.id}
              className="p-3 rounded-md border border-gray-100 bg-white/60"
            >
              <div className="text-xs font-semibold text-gray-700">{m.who}</div>
              <div className="mt-1 text-sm text-gray-800">{m.text}</div>
            </li>
          ))}
        </ul>
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Type a message to Lovable..."
          className="flex-1 rounded-md p-3 border border-gray-200"
        />
        <button onClick={onSend} className="btn-hero">
          Send
        </button>
      </div>
    </div>
  );
}