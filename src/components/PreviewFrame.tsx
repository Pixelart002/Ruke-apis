import React, { useRef, useState } from "react";

export default function PreviewFrame() {
  const iframeRef = useRef<HTMLIFrameElement | null>(null);
  const [url] = useState("about:blank");

  return (
    <div className="flex flex-col h-[60vh]">
      <div className="flex items-center justify-between mb-3">
        <div className="text-sm text-gray-600">Live Preview</div>
        <div className="text-xs text-gray-500">iframe sandbox (read-only)</div>
      </div>

      <div className="flex-1 border border-gray-200 rounded-md overflow-hidden">
        <iframe
          ref={iframeRef}
          title="preview"
          src={url}
          sandbox="allow-scripts allow-same-origin"
          className="w-full h-full"
        />
      </div>
    </div>
  );
}