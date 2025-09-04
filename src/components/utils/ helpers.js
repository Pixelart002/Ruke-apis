import { FlatList } from 'react-native';

export const scrollToBottom = (flatListRef) => {
  flatListRef?.current?.scrollToEnd({ animated: true });
};

export const formatMessageId = () => Date.now().toString();