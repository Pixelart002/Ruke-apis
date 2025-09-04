import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import ChatScreen from './src/components/ChatScreen';

export default function App() {
  return (
    <SafeAreaView style={styles.container}>
      <ChatScreen />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0F111A',
  },
});