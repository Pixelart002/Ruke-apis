#!/usr/bin/env python3
"""Direct monitoring test with detailed output"""

import asyncio
from telethon import TelegramClient
import json

async def test_direct_monitoring():
    """Test direct monitoring of the group"""
    
    # Load accounts
    with open('accounts.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    if not data.get('accounts'):
        print("No accounts found!")
        return
    
    # Use first account
    account = data['accounts'][0]
    print(f"Using account: {account['account_id']}")
    
    # Create client
    client = TelegramClient(
        f"test_session_{account['account_id']}",
        account['api_id'],
        account['api_hash']
    )
    
    try:
        await client.start()
        print("✓ Connected to Telegram")
        
        # Get the group
        group = await client.get_entity('FUNToken_OfficialChat')
        print(f"✓ Found group: {group.title}")
        
        # Check for messages from quiz bot
        QUIZ_BOT_ID = 7901924377
        print(f"\nScanning for messages from Quiz Bot (ID: {QUIZ_BOT_ID})...")
        
        messages_found = 0
        quiz_messages = 0
        
        async for msg in client.iter_messages(group, limit=100):
            if msg.sender_id == QUIZ_BOT_ID:
                messages_found += 1
                text = msg.message or ''
                
                # Check if it's a quiz
                is_quiz = False
                if 'A)' in text and 'B)' in text and 'C)' in text and 'D)' in text:
                    is_quiz = True
                    quiz_messages += 1
                
                print(f"\nMessage {messages_found} (ID: {msg.id}):")
                print(f"  Date: {msg.date}")
                print(f"  Is Quiz: {is_quiz}")
                print(f"  First 200 chars: {text[:200]}...")
                
                if messages_found >= 5:  # Show first 5 bot messages
                    break
        
        print(f"\n" + "="*50)
        print(f"Summary:")
        print(f"  Total bot messages found: {messages_found}")
        print(f"  Quiz messages found: {quiz_messages}")
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        await client.disconnect()
        print("\n✓ Disconnected")

if __name__ == "__main__":
    asyncio.run(test_direct_monitoring())