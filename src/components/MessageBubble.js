import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export default function MessageBubble({ message }) {
  const isUser = message.type === 'user';

  return (
    <View style={[styles.bubble, isUser ? styles.userBubble : styles.aiBubble]}>
      <Text style={[styles.text, isUser ? styles.userText : styles.aiText]}>
        {message.text}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  bubble: {
    maxWidth: '80%',
    padding: 10,
    borderRadius: 12,
    marginVertical: 5,
  },
  userBubble: {
    backgroundColor: '#1F2937',
    alignSelf: 'flex-end',
  },
  aiBubble: {
    backgroundColor: '#111827',
    alignSelf: 'flex-start',
  },
  text: { fontSize: 16 },
  userText: { color: '#fff' },
  aiText: { color: '#f0f0f0' },
});