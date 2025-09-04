import React, { useState, useRef } from 'react';
import { View, FlatList, StyleSheet, KeyboardAvoidingView, Platform } from 'react-native';
import InputBar from './InputBar';
import MessageBubble from './MessageBubble';
import { fetchGeminiResponse } from '../api/gemini';

export default function ChatScreen() {
  const [messages, setMessages] = useState([]);
  const flatListRef = useRef();

  const sendMessage = async (text) => {
    if (!text) return;

    const userMsg = { id: Date.now().toString(), text, type: 'user' };
    setMessages(prev => [...prev, userMsg]);
    scrollToBottom();

    const aiMsg = { id: (Date.now() + 1).toString(), text: '...', type: 'ai' };
    setMessages(prev => [...prev, userMsg, aiMsg]);
    scrollToBottom();

    const aiResponse = await fetchGeminiResponse(text);
    setMessages(prev => prev.map(msg => msg.id === aiMsg.id ? { ...msg, text: aiResponse } : msg));
    scrollToBottom();
  };

  const scrollToBottom = () => {
    flatListRef.current?.scrollToEnd({ animated: true });
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      keyboardVerticalOffset={80}
    >
      <FlatList
        ref={flatListRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => <MessageBubble message={item} />}
        contentContainerStyle={styles.messagesContainer}
      />
      <InputBar onSend={sendMessage} />
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  messagesContainer: { padding: 10 },
});