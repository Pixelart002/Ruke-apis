chatgpt-clone/
├─ package.json
├─ App.js
├─ babel.config.js
├─ app.json
├─ node_modules/
├─ assets/
│   ├─ logo.png
│   └─ ...
├─ src/
│   ├─ api/
│   │   └─ gemini.js            # Gemini API request logic
│   ├─ components/
│   │   ├─ ChatScreen.js        # Main chat interface
│   │   ├─ MessageBubble.js     # User/AI messages
│   │   └─ InputBar.js          # Input field + send button
│   ├─ constants/
│   │   └─ colors.js            # App colors
│   ├─ hooks/
│   │   └─ useChat.js           # Custom chat hook (optional)
│   └─ utils/
│       └─ helpers.js           # Helper functions (e.g., scroll to bottom)
└─ web/
    └─ index.html