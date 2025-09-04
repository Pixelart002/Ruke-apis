import React, { useState } from 'react';
import { View, TextInput, TouchableOpacity, Text, StyleSheet } from 'react-native';

export default function InputBar({ onSend }) {
  const [text, setText] = useState('');

  const handleSend = () => {
    onSend(text.trim());
    setText('');
  };

  return (
    <View style={styles.container}>
      <TextInput
        style={styles.input}
        placeholder="Type your message..."
        placeholderTextColor="#888"
        value={text}
        onChangeText={setText}
        onSubmitEditing={handleSend}
      />
      <TouchableOpacity style={styles.button} onPress={handleSend}>
        <Text style={styles.buttonText}>Send</Text>
      </TouchableOpacity>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    padding: 8,
    borderTopWidth: 1,
    borderTopColor: '#333',
    backgroundColor: '#0F111A',
  },
  input: {
    flex: 1,
    color: '#fff',
    padding: 10,
    borderRadius: 20,
    backgroundColor: '#1F2937',
    marginRight: 8,
  },
  button: {
    backgroundColor: '#2563EB',
    borderRadius: 20,
    paddingHorizontal: 15,
    justifyContent: 'center',
  },
  buttonText: { color: '#fff', fontWeight: 'bold' },
});