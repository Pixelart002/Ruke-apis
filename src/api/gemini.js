import axios from 'axios';

const GEMINI_API_KEY = 'AIzaSyDATuXl_5gMVK4ULJiH3hvZ4PGHsDQhD0c';
const GEMINI_ENDPOINT = 'https://gemini.googleapis.com/v1/models/text-bison-001:generate';

export const fetchGeminiResponse = async (prompt) => {
  try {
    const response = await axios.post(
      GEMINI_ENDPOINT,
      {
        prompt: prompt,
        temperature: 0.7,
        maxOutputTokens: 300,
      },
      {
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${GEMINI_API_KEY}`,
        },
      }
    );
    return response.data?.candidates[0]?.content || 'No response';
  } catch (error) {
    console.error('Gemini API error:', error);
    return 'Error fetching response';
  }
};