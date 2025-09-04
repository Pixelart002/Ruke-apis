import { useState, useRef } from 'react';
import { fetchGeminiResponse } from '../api/gemini';
import { scrollToBottom, formatMessageId } from '../utils/helpers';

export const useChat = () => {
  const [messages, setMessages] = useState([]);
  const flatListRef = useRef();

  const sendMessage = async (text) => {
    if (!text) return;

    const userMsg = { id: formatMessageId(), text, type: 'user' };
    setMessages(prev => [...prev, userMsg]);
    scrollToBottom(flatListRef);

    const aiMsg = { id: formatMessageId(), text: '...', type: 'ai' };
    setMessages(prev => [...prev, aiMsg]);
    scrollToBottom(flatListRef);

    const aiResponse = await fetchGeminiResponse(text);
    setMessages(prev => prev.map(msg => msg.id === aiMsg.id ? { ...msg, text: aiResponse } : msg));
    scrollToBottom(flatListRef);
  };

  return { messages, sendMessage, flatListRef };
};