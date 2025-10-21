#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple Terminal-Based Quiz Bot Manager
Cross-platform compatible: Windows, Linux, macOS, Termux, VPS
Manages accounts and monitors quiz through terminal interface
Sends questions to @askplexbot and extracts answers
"""

import json
import os
import sys
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
import re
import time
import platform
import locale
import random

# Set UTF-8 encoding for all platforms
if sys.platform == 'win32':
    # Windows specific UTF-8 setup
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer, 'strict')
    sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer, 'strict')
    # Set console code page to UTF-8
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleCP(65001)
        kernel32.SetConsoleOutputCP(65001)
    except:
        pass

# Set locale to UTF-8 for all platforms
try:
    locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
except:
    try:
        locale.setlocale(locale.LC_ALL, 'C.UTF-8')
    except:
        pass

# Suppress ALL Telethon logs before importing
logging.getLogger('telethon').setLevel(logging.ERROR)
logging.getLogger('telethon.network.mtprotosender').setLevel(logging.ERROR)
logging.getLogger('telethon.extensions.messagepacker').setLevel(logging.ERROR)
logging.getLogger('telethon.client.telegrambaseclient').setLevel(logging.ERROR)

from telethon import TelegramClient, events
from telethon.errors import SessionPasswordNeededError, PhoneCodeInvalidError

# Configure our own logging
logging.basicConfig(
    level=logging.WARNING,  # Changed to WARNING to reduce output
    format='%(message)s'  # Simplified format
)
logger = logging.getLogger(__name__)

# Platform detection
PLATFORM = platform.system().lower()
IS_WINDOWS = PLATFORM == 'windows'
IS_TERMUX = 'termux' in os.environ.get('PREFIX', '').lower() or os.path.exists('/data/data/com.termux')
IS_MACOS = PLATFORM == 'darwin'
IS_LINUX = PLATFORM == 'linux' and not IS_TERMUX

# Get proper data directory based on platform
def get_data_dir():
    """Get appropriate data directory for the platform"""
    if IS_TERMUX:
        # Termux has specific storage locations
        return os.path.expanduser('~/storage/shared/quiz_bot')
    elif IS_WINDOWS:
        # Windows - use current directory or AppData
        return os.path.join(os.getcwd(), 'quiz_bot_data')
    else:
        # Linux/macOS/VPS - use home directory
        return os.path.expanduser('~/.quiz_bot')

# Create data directory if it doesn't exist
DATA_DIR = get_data_dir()
os.makedirs(DATA_DIR, exist_ok=True)

# Constants - with cross-platform paths
ACCOUNTS_FILE = os.path.join(DATA_DIR, 'accounts.json')
QUESTIONS_FILE = os.path.join(DATA_DIR, 'questions.json')
AI_CONFIG_FILE = os.path.join(DATA_DIR, 'ai_config.json')

# Default Configuration
DEFAULT_AI_BOT = '@askplexbot'  # Default bot to send questions to
DEFAULT_OTP = '12345'  # Default OTP for simplicity
RESEARCH_DELAY = 20  # Seconds to wait for bot response

# Quiz Monitoring Configuration
TARGET_GROUP = 'FUNToken_OfficialChat'  # The group to monitor for quizzes
QUIZ_BOT_ID = 7901924377  # The bot ID that posts quizzes
SCAN_INTERVAL = 5  # Check every 5 seconds
MAX_SCAN_MESSAGES = 50  # Check last 50 messages

# Available AI Bots (for getting quiz answers)
AI_BOTS = {
    '1': '@askplexbot',
    '2': '@askplexbot',  # Default, most reliable
    '3': '@askplexbot'   # Can add other bots here if needed
}

# The prompt template used to send to @askplexbot
QUIZ_PROMPT_TEMPLATE = """📚 QUIZ ANALYSIS TIME - {research_delay} seconds to research!

Question: {question}

{options}

🌐 Use internet for better quality and accurate answers:
• Search for key terms from the question
• Apply the elimination method
• Do deep analysis of each option
• Consider context clues in the question

🎯 EMOJI INTERPRETATION GUIDE:
• Emojis can be tricky - sometimes they determine crypto related, movies, and other things
• Emojis don't always have straight answers - research a little bit
• Think about popular culture references
• Consider gaming and virtual reality concepts
• Look for tech and digital world connections
• Match emoji combinations to well-known concepts

🧠 Analysis Strategy:
1. Read the question carefully
2. Analyze emoji meanings in context of movies/games/tech
3. Eliminate obviously wrong options
4. Research remaining options online
5. Use logical reasoning and elimination
6. Make your MOST ACCURATE final decision - NO ERRORS!

⏰ Take {research_delay} seconds to research and analyze...

🚨 CRITICAL: RESPONSE FORMAT REQUIREMENTS 🚨
❌ DO NOT provide explanations, analysis, or reasoning
❌ DO NOT provide detailed breakdowns or context
❌ DO NOT use any format like [Claude 4 🧠] or emojis
❌ DO NOT write anything except the single letter

✅ REQUIRED RESPONSE FORMAT:
✅ Reply with ONLY one letter: A, B, C, D, or E
✅ Nothing else - just the letter
✅ NEVER write answer twice like AA BB CC DD EE OR AAAA
✅ ALWAYS one single digit answer
✅ Example correct response: B
✅ Example wrong response: [Claude 4 🧠] B (TOO MUCH)
✅ Example wrong response: BB or AAA (DUPLICATED)

⚡ REMINDER: SINGLE LETTER ONLY! ⚡
🎯 ACCURACY IS CRITICAL - Make the RIGHT choice!
💡 Start your research now - Be 100% accurate!"""

class AccountManager:
    """Manages Telegram accounts"""
    
    def __init__(self):
        self.accounts_file = ACCOUNTS_FILE
        self.load_accounts()
        
    def load_accounts(self):
        """Load accounts from JSON file"""
        if os.path.exists(self.accounts_file):
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self.accounts = data.get('accounts', [])
        else:
            self.accounts = []
            self.save_accounts()
    
    def save_accounts(self):
        """Save accounts to JSON file"""
        with open(self.accounts_file, 'w', encoding='utf-8') as f:
            json.dump({'accounts': self.accounts}, f, indent=2)
    
    async def add_account(self):
        """Add a new account through terminal input"""
        print("\nAdd New Account")
        print("-" * 20)
        
        api_id = input("API ID: ").strip()
        if not api_id.isdigit():
            print("Error: API ID must be a number")
            return False
            
        api_hash = input("API Hash: ").strip()
        if not api_hash:
            print("Error: API Hash cannot be empty")
            return False
            
        phone = input("Phone (with +): ").strip()
        if not phone.startswith('+'):
            print("Error: Phone must start with + and country code")
            return False
            
        account_id = input("Account Name: ").strip()
        if not account_id:
            print("Error: Account name cannot be empty")
            return False
            
        # Check if account already exists
        for acc in self.accounts:
            if acc['phone'] == phone or acc['account_id'] == account_id:
                print("Error: Account already exists")
                return False
        
        # Create account data
        new_account = {
            'api_id': int(api_id),
            'api_hash': api_hash,
            'phone': phone,
            'two_fa_pass': 'null',
            'account_id': account_id
        }
        
        # Now authorize and save session immediately
        print("\nAuthorizing account...")
        if await self.authorize_and_save_session(new_account):
            # Only save account if authorization successful
            self.accounts.append(new_account)
            self.save_accounts()
            print(f"\n✓ Account '{account_id}' added and authorized")
            return True
        else:
            print(f"\n✗ Failed to add account '{account_id}'")
            return False
    
    async def authorize_and_save_session(self, account):
        """Authorize account and save session during account addition"""
        try:
            session_name = account['account_id']
            session_path = os.path.join(DATA_DIR, session_name)
            client = TelegramClient(
                session_path,
                account['api_id'],
                account['api_hash']
            )
            
            await client.connect()
            
            # Send code request
            await client.send_code_request(account['phone'])
            
            # Ask for OTP
            code = input(f"Enter OTP code (or press Enter for {DEFAULT_OTP}): ").strip()
            if not code:
                code = DEFAULT_OTP
            
            try:
                # Try to sign in with OTP
                await client.sign_in(account['phone'], code)
                print("✓ Authorized successfully")
                await client.disconnect()
                return True
                
            except SessionPasswordNeededError:
                # Account has 2FA, ask for password
                password = input("Enter 2FA password: ").strip()
                if password:
                    try:
                        await client.sign_in(password=password)
                        print("✓ Authorized with 2FA")
                        # Save 2FA password for future use
                        account['two_fa_pass'] = password
                        await client.disconnect()
                        return True
                    except Exception as e:
                        print(f"✗ 2FA failed: {str(e)[:50]}")
                        await client.disconnect()
                        return False
                else:
                    print("✗ 2FA password required but not provided")
                    await client.disconnect()
                    return False
                    
            except PhoneCodeInvalidError:
                print("✗ Invalid OTP code")
                await client.disconnect()
                return False
                
        except Exception as e:
            print(f"✗ Authorization failed: {str(e)[:50]}")
            return False
    
    def delete_account(self):
        """Delete an account"""
        if not self.accounts:
            print("\nNo accounts to delete")
            return False
            
        self.list_accounts()
        
        try:
            choice = input("\nDelete account # (0 to cancel): ").strip()
            idx = int(choice) - 1
            
            if idx == -1:
                return False
                
            if 0 <= idx < len(self.accounts):
                acc = self.accounts[idx]
                confirm = input(f"Delete '{acc['account_id']}'? (y/n): ").lower()
                
                if confirm == 'y':
                    # Remove session file if exists (check multiple locations)
                    session_files = [
                        os.path.join(DATA_DIR, f"{acc['account_id']}.session"),
                        os.path.join(os.getcwd(), f"{acc['account_id']}.session"),
                        f"{acc['account_id']}.session"
                    ]
                    for session_file in session_files:
                        if os.path.exists(session_file):
                            try:
                                os.remove(session_file)
                            except:
                                pass
                    
                    self.accounts.pop(idx)
                    self.save_accounts()
                    print(f"\n✓ Deleted '{acc['account_id']}'")
                    return True
                else:
                    return False
            else:
                print("Invalid number")
                return False
                
        except ValueError:
            print("Invalid input")
            return False
    
    def list_accounts(self):
        """List all accounts"""
        if not self.accounts:
            print("\nNo accounts configured")
            return
            
        print("\nAccounts:")
        print("-" * 30)
        for i, acc in enumerate(self.accounts, 1):
            print(f"{i}. {acc['account_id']} ({acc['phone']})")


class QuizMonitor:
    """Monitors and handles quiz questions"""
    
    def __init__(self, account_manager):
        self.account_manager = account_manager
        self.questions = self.load_questions()
        self.clients = {}
        self.monitoring = False
        self.load_ai_config()
        
    def load_questions(self):
        """Load saved questions"""
        if os.path.exists(QUESTIONS_FILE):
            with open(QUESTIONS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def save_questions(self):
        """Save questions to file"""
        with open(QUESTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.questions, f, indent=2)
    
    def load_ai_config(self):
        """Load AI configuration"""
        if os.path.exists(AI_CONFIG_FILE):
            with open(AI_CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                self.ai_bot = config.get('ai_bot', DEFAULT_AI_BOT)
                self.ai_account = config.get('ai_account', None)
        else:
            self.ai_bot = DEFAULT_AI_BOT
            self.ai_account = None
            self.save_ai_config()
    
    def save_ai_config(self):
        """Save AI configuration"""
        config = {
            'ai_bot': self.ai_bot,
            'ai_account': self.ai_account
        }
        with open(AI_CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)
    
    def change_ai_bot(self):
        """Change the AI bot used for answers"""
        print("\nChange AI Bot")
        print("-" * 30)
        print(f"Current AI Bot: {self.ai_bot}")
        print("\nAvailable Options:")
        print("1. @askplexbot (default/recommended)")
        print("2. Custom (enter your own bot)")
        
        choice = input("\nSelect option (1-2): ").strip()
        
        if choice == '1':
            self.ai_bot = '@askplexbot'
        elif choice == '2':
            custom_bot = input("Enter bot username (with @): ").strip()
            if custom_bot.startswith('@'):
                self.ai_bot = custom_bot
            else:
                self.ai_bot = '@' + custom_bot
        else:
            print("Invalid choice")
            return False
        
        self.save_ai_config()
        print(f"\n✓ AI Bot changed to: {self.ai_bot}")
        return True
    
    def choose_ai_account(self):
        """Choose which account to use for AI queries"""
        print("\nChoose AI Account")
        print("-" * 30)
        
        if not self.account_manager.accounts:
            print("No accounts available")
            return False
        
        print(f"Current AI Account: {self.ai_account or 'Auto (uses first available)'}")
        print("\nAvailable accounts:")
        print("0. Auto (uses first available)")
        
        for i, acc in enumerate(self.account_manager.accounts, 1):
            print(f"{i}. {acc['account_id']} ({acc['phone']})")
        
        try:
            choice = input("\nSelect account (0 for auto): ").strip()
            idx = int(choice)
            
            if idx == 0:
                self.ai_account = None
                print("\n✓ AI Account set to: Auto")
            elif 1 <= idx <= len(self.account_manager.accounts):
                selected_acc = self.account_manager.accounts[idx - 1]
                self.ai_account = selected_acc['account_id']
                print(f"\n✓ AI Account set to: {self.ai_account}")
            else:
                print("Invalid choice")
                return False
            
            self.save_ai_config()
            return True
            
        except ValueError:
            print("Invalid input")
            return False
    
    async def create_client(self, account):
        """Create Telegram client for an account"""
        try:
            session_name = account['account_id']
            session_path = os.path.join(DATA_DIR, session_name)
            
            # Try to use existing session first
            client = TelegramClient(
                session_path,
                account['api_id'],
                account['api_hash']
            )
            
            await client.connect()
            
            # Check if authorized
            if await client.is_user_authorized():
                # Session is valid, we're good to go
                return client
            else:
                # Need to authorize
                print(f"  Session expired for {account['account_id']}")
                print(f"  Please re-authorize:")
                
                try:
                    await client.send_code_request(account['phone'])
                except Exception as e:
                    if "PHONE_NUMBER_INVALID" in str(e):
                        print(f"  ✗ Invalid phone number: {account['phone']}")
                    else:
                        print(f"  ✗ Failed to send code: {str(e)[:40]}")
                    await client.disconnect()
                    return None
                
                code = input(f"  Enter OTP (or press Enter for {DEFAULT_OTP}): ").strip()
                if not code:
                    code = DEFAULT_OTP
                    
                try:
                    await client.sign_in(account['phone'], code)
                    print(f"  ✓ Re-authorized")
                    return client
                except SessionPasswordNeededError:
                    # Handle 2FA
                    password = None
                    if account.get('two_fa_pass') and account['two_fa_pass'] != 'null':
                        # Try saved password
                        try:
                            await client.sign_in(password=account['two_fa_pass'])
                            print(f"  ✓ Re-authorized with saved 2FA")
                            return client
                        except:
                            pass  # Saved password didn't work
                    
                    # Ask for 2FA password
                    password = input("  Enter 2FA password: ").strip()
                    if password:
                        try:
                            await client.sign_in(password=password)
                            print(f"  ✓ Re-authorized with 2FA")
                            # Update saved password
                            account['two_fa_pass'] = password
                            return client
                        except Exception as e:
                            print(f"  ✗ 2FA failed: {str(e)[:40]}")
                    else:
                        print(f"  ✗ 2FA required but not provided")
                    
                    await client.disconnect()
                    return None
                    
                except PhoneCodeInvalidError:
                    print(f"  ✗ Invalid OTP code")
                    await client.disconnect()
                    return None
                except Exception as e:
                    print(f"  ✗ Sign in failed: {str(e)[:40]}")
                    await client.disconnect()
                    return None
            
        except Exception as e:
            error_msg = str(e)
            if "database is locked" in error_msg.lower():
                print(f"  ✗ Session file locked, cleaning up...")
                # Try to remove the session file and retry
                try:
                    session_file = f"{account['account_id']}.session"
                    if os.path.exists(session_file):
                        os.remove(session_file)
                    print(f"  Session cleaned, please try again")
                except:
                    pass
            else:
                print(f"  ✗ Error: {error_msg[:40]}")
            return None
    
    def format_quiz_prompt(self, question, options):
        """Format the quiz prompt to send to @askplexbot"""
        # Format options
        formatted_options = ""
        for i, option in enumerate(options):
            formatted_options += f"{chr(65 + i)}) {option}\n"
        
        # Replace placeholders in template
        formatted_prompt = QUIZ_PROMPT_TEMPLATE.format(
            question=question,
            options=formatted_options,
            research_delay=RESEARCH_DELAY
        )
        
        return formatted_prompt
    
    async def get_bot_answer(self, client, question, options):
        """Send question to AI bot and extract answer - exactly like old ai.py"""
        try:
            # Use configured AI account if specified, otherwise use provided client
            ai_client = client
            if self.ai_account:
                # Try to use the specified AI account
                ai_client = self.clients.get(self.ai_account, client)
            
            # Format the prompt
            prompt = self.format_quiz_prompt(question, options)
            
            # Record timestamp BEFORE sending (with timezone)
            send_time = datetime.now(timezone.utc)
            
            # Send to configured AI bot
            await ai_client.send_message(self.ai_bot, prompt)
            
            # Wait for bot to research
            await asyncio.sleep(RESEARCH_DELAY)
            
            # Give bot a moment to finish any final edits
            await asyncio.sleep(2)
            
            # Try multiple times to get the bot's response (in case it's still editing)
            bot_answer = None
            for attempt in range(3):
                # Get messages from bot after our timestamp
                messages = []
                async for message in ai_client.iter_messages(self.ai_bot, limit=20):
                    if message.text:
                        # Compare timestamps properly (both are timezone-aware)
                        if message.date > send_time:
                            messages.append(message)
                
                if not messages:
                    if attempt < 2:
                        await asyncio.sleep(2)  # Wait before retry
                    continue
                
                # Sort messages by date (newest first)
                messages.sort(key=lambda m: m.date, reverse=True)
                
                # Look through messages for bot's response
                for message in messages:
                    answer = self.extract_answer_from_text(message.text)
                    if answer:
                        bot_answer = answer
                        break
                
                if bot_answer:
                    break
            
            return bot_answer
            
        except Exception as e:
            print(f"    Error: {str(e)[:40]}")
            return None
    
    def is_quiz_message(self, text):
        """Detect if message is a quiz - EXACT method from quiz_monitor.py"""
        if not text:
            return False
        
        text_lower = text.lower()
        
        # Must contain quiz indicators
        quiz_indicators = [
            "quick quiz",
            "emoji puzzle",
            "answer within",
            "choose the correct option below"
        ]
        
        # Must contain time limit
        time_indicators = ["⏳", "minutes"]
        
        # Must contain reward mention
        reward_indicators = ["reward:", "wheel of fortune", "spin"]
        
        has_quiz = any(indicator in text_lower for indicator in quiz_indicators)
        has_time = any(indicator in text_lower for indicator in time_indicators)
        has_reward = any(indicator in text_lower for indicator in reward_indicators)
        
        return has_quiz and has_time and has_reward
    
    def extract_quiz_question(self, text):
        """Extract question from quiz message INCLUDING emojis - like original quiz_monitor.py"""
        if not text:
            return "Question not found"
        
        lines = [line.strip() for line in text.split('\n') if line.strip()]
        
        # Skip common non-question lines
        skip_phrases = [
            'quick quiz', 'emoji puzzle', 'reward:', 'make sure', 'choose the correct',
            'answer within', 'add our bot', 'do not share', 'spin for all'
        ]
        
        # Check if this is an emoji puzzle
        text_lower = text.lower()
        is_emoji_puzzle = 'emoji puzzle' in text_lower or '🧩' in text
        
        if is_emoji_puzzle:
            # For emoji puzzles, we need to find BOTH the question AND the emoji sequence
            question_part = None
            emoji_part = None
            
            # Enhanced emoji pattern to catch ALL emojis
            emoji_pattern = r'[\U0001F300-\U0001F9FF\U00002600-\U000027BF\U0001F000-\U0001F02F\U0001F0A0-\U0001F0FF\U0001F100-\U0001F1FF\U0001F200-\U0001F2FF\U0001F680-\U0001F6FF\U0001F700-\U0001F77F\U0001F780-\U0001F7FF\U0001F800-\U0001F8FF\U0001F900-\U0001F9FF\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002300-\U000023FF\U000025A0-\U000025FF\U000026A0-\U000026FF\U000027C0-\U000027EF\U00002B00-\U00002BFF]+'
            
            # Find the question line
            for line in lines:
                line_lower = line.lower()
                if any(skip in line_lower for skip in skip_phrases):
                    continue
                
                if ('what' in line_lower and ('these emojis' in line_lower or 'emoji' in line_lower or 'represent' in line_lower)):
                    question_part = line.strip()
                    break
            
            # Find the emoji sequence line (usually just emojis or emojis with minimal text)
            for line in lines:
                # Skip lines that are clearly not the emoji sequence
                if any(skip in line.lower() for skip in skip_phrases):
                    continue
                if line.lower() == (question_part.lower() if question_part else ''):
                    continue
                    
                # Look for lines with significant emoji content
                emojis = re.findall(emoji_pattern, line)
                if emojis:
                    emoji_text = ''.join(emojis)
                    # Must have at least 2 emojis to be the puzzle
                    if len(emoji_text) >= 2 and len(line) <= 50:
                        emoji_part = line.strip()
                        break
            
            # Combine question with emojis
            if question_part and emoji_part:
                return f"{question_part} {emoji_part}"
            elif emoji_part:
                return f"What do these emojis represent? {emoji_part}"
            elif question_part:
                return question_part
        
        # Regular question extraction for non-emoji puzzles
        for line in lines:
            line_lower = line.lower()
            
            # Skip lines with skip phrases
            if any(skip in line_lower for skip in skip_phrases):
                continue
            
            # Look for question indicators
            if ('what' in line_lower or 'which' in line_lower or 'who' in line_lower or
                'how' in line_lower or 'when' in line_lower or 'where' in line_lower or
                line.strip().endswith('?')):
                
                # Clean the question but keep emojis
                question = re.sub(r'^[🧠🧩✨🔥⚡🎯]+\s*', '', line)
                question = question.strip()
                
                if len(question) > 10:
                    return question
        
        # If no question found, return first substantial line
        for line in lines:
            if len(line) > 20 and not any(skip in line.lower() for skip in skip_phrases):
                return line
        
        return "Question not found"
    
    def extract_answer_from_text(self, text):
        """Extract answer letter (A, B, C, D, E) from bot's response"""
        if not text:
            return None
        
        response_clean = text.strip()
        
        # Method 0: Direct answer patterns
        answer_patterns = [
            r'[Aa]nswer[:\s]+([A-Ea-e])\b',
            r'[Tt]he answer is[:\s]+([A-Ea-e])\b',
            r'[Cc]orrect answer[:\s]+([A-Ea-e])\b',
            r'[Cc]hoose[:\s]+([A-Ea-e])\b',
            r'[Oo]ption[:\s]+([A-Ea-e])\b',
            r'^([A-Ea-e])[\s\)\.]',  # A) or A. at start
        ]
        
        for pattern in answer_patterns:
            match = re.search(pattern, response_clean)
            if match:
                return match.group(1).upper()
        
        # Method 1: Single letter on its own line
        for line in text.splitlines():
            line_clean = line.strip()
            if re.fullmatch(r'[A-Ea-e]', line_clean):
                return line_clean.upper()
        
        # Method 2: Single letter between newlines
        match = re.search(r'\n\s*([A-Ea-e])\s*\n', text)
        if match:
            return match.group(1).upper()
        
        # Method 3: Single letter at end of message
        match = re.search(r'\n\s*([A-Ea-e])\s*$', text)
        if match:
            return match.group(1).upper()
        
        # Method 4: Any single letter as word boundary
        match = re.search(r'\b([A-Ea-e])\b', text)
        if match:
            return match.group(1).upper()
        
        return None
    
    async def handle_quiz_message_clean(self, event, client_name):
        """Handle quiz message with clean output - using button clicks like original"""
        try:
            msg = event.message
            
            # Extract question from message text
            text = msg.message or ''
            question = self.extract_quiz_question(text)
            
            # Get options from buttons (like original quiz_monitor.py)
            options = []
            button_data = []
            
            if msg.reply_markup and hasattr(msg.reply_markup, 'rows'):
                absolute_button_index = 0
                for row_idx, row in enumerate(msg.reply_markup.rows):
                    for btn_idx, btn in enumerate(row.buttons):
                        option_text = btn.text.strip()
                        if option_text:
                            options.append(option_text)
                            button_data.append({
                                'text': option_text,
                                'row': row_idx,
                                'button': btn_idx,
                                'absolute_index': absolute_button_index
                            })
                            absolute_button_index += 1
            
            if not options:
                # Fallback to text parsing if no buttons
                question, options = self.extract_question_and_options(text)
            
            if question and options:
                # Get the answer index - either from cache or from _current_quiz_answer
                answer_index = None
                
                # First check if we have a cached answer for this specific question
                question_key = question.lower().strip()
                if question_key in self.questions:
                    # Use cached answer
                    answer_data = self.questions[question_key]
                    answer_letter = answer_data.get('answer_letter', '')
                    if answer_letter:
                        answer_index = ord(answer_letter) - ord('A')
                
                # If no cached answer, use the current quiz answer (set by the first account)
                if answer_index is None and hasattr(self, '_current_quiz_answer'):
                    answer_index = self._current_quiz_answer
                
                # If still no answer, default to B
                if answer_index is None:
                    answer_index = 1  # Default to B
                
                # Submit answer by clicking button
                if answer_index < len(button_data):
                    try:
                        button_info = button_data[answer_index]
                        # Click the button
                        await msg.click(button_info['row'], button_info['button'])
                        return True
                    except Exception as e:
                        error_str = str(e)
                        # Common errors when quiz already answered or buttons expired
                        if any(err in error_str for err in ["MessageNotModifiedError", "BUTTON_DATA_INVALID", "message is too old", "QueryIdInvalidError"]):
                            # Quiz might be already answered, consider it success
                            return True
                        
                        # Button click failed
                        return False
                else:
                    # No button available for this answer index
                    return False
                    
        except Exception as e:
            print(f"Error in handle_quiz_message_clean: {e}")
            return False
        
        return False
    
    async def handle_quiz_message(self, event, client_name):
        """Handle incoming quiz messages"""
        # Get message text - handle both real events and our fake events
        if hasattr(event.message, 'message'):
            message = event.message.message
        else:
            message = event.message.text or event.message.message
        
        # Check if it's a quiz question (contains options A, B, C, D)
        if re.search(r'[A-D]\)', message):
            question, options = self.extract_question_and_options(message)
            
            if question and options:
                print(f"  Question: {question[:50]}...")
                
                # Check if we already have the answer saved
                question_key = question.lower().strip()
                
                if question_key in self.questions:
                    # Use saved answer
                    answer_data = self.questions[question_key]
                    answer = answer_data.get('answer_letter', '')
                    print(f"  ✓ Cached: {answer}")
                    
                    # Update usage count
                    self.questions[question_key]['usage_count'] = self.questions[question_key].get('usage_count', 0) + 1
                    self.save_questions()
                else:
                    # Get answer from AI bot
                    print(f"  🔍 Researching...")
                    client = self.clients.get(client_name)
                    if client:
                        answer = await self.get_bot_answer(client, question, options)
                        
                        if answer and answer in ['A', 'B', 'C', 'D', 'E']:
                            # Save the answer for future use
                            self.questions[question_key] = {
                                'answer_letter': answer,
                                'answer_text': options[ord(answer) - ord('A')] if ord(answer) - ord('A') < len(options) else '',
                                'saved_at': datetime.now().isoformat(),
                                'original_question': question,
                                'usage_count': 1
                            }
                            self.save_questions()
                            print(f"  ✓ Answer: {answer}")
                        else:
                            # Fallback to option B if bot doesn't respond properly
                            answer = 'B'
                            print(f"  Using fallback: {answer}")
                    else:
                        # No client available, use fallback
                        answer = 'B'
                
                # Small delay before submitting (to appear more human-like)
                await asyncio.sleep(2)
                
                # Submit the answer to the group
                if answer and event.chat_id:
                    try:
                        # Send just the letter answer
                        await event.client.send_message(event.chat_id, answer)
                        print(f"  ✓ Submitted: {answer}")
                    except Exception as e:
                        print(f"  ✗ Failed: {str(e)[:30]}")
    
    def extract_question_and_options(self, message):
        """Extract question and options from quiz message"""
        lines = message.split('\n')
        question_lines = []
        options = []
        
        for line in lines:
            # Check if this line is an option
            option_match = re.match(r'^([A-E])\)\s*(.+)', line)
            if option_match:
                options.append(option_match.group(2).strip())
            elif not options:  # Still collecting question lines
                question_lines.append(line)
        
        question = ' '.join(question_lines).strip()
        
        if question and options:
            return question, options
        return None, None
    
    async def start_monitoring(self):
        """Start monitoring all accounts"""
        if not self.account_manager.accounts:
            print("\nNo accounts available. Please add accounts first.")
            return
        
        clear_screen()
        print("Starting Quiz Monitor...")
        await asyncio.sleep(1)
        
        # Create clients for all accounts in parallel batches
        connected_clients = []
        print(f"Connecting {len(self.account_manager.accounts)} accounts...")
        
        # Connect in batches of 5 for faster startup
        batch_size = 5
        for i in range(0, len(self.account_manager.accounts), batch_size):
            batch = self.account_manager.accounts[i:i+batch_size]
            
            # Create connection tasks
            tasks = []
            for account in batch:
                task = self.create_client(account)
                tasks.append((account['account_id'], task))
            
            # Wait for batch to connect
            for acc_id, task in tasks:
                try:
                    client = await task
                    if client:
                        self.clients[acc_id] = client
                        connected_clients.append((acc_id, client))
                        print(f"✓ {acc_id}")
                except:
                    print(f"✗ {acc_id}")
        
        if not connected_clients:
            print("\nNo accounts could be connected")
            return
        
        self.monitoring = True
        
        # Clear screen for clean monitoring
        clear_screen()
        
        # Start monitoring loop - EXACTLY like quiz_monitor.py
        processed_quiz_ids = set()  # Track processed quiz IDs to avoid duplicates
        quiz_count = 0
        total_submitted = 0  # Track total submissions across all quizzes
        total_accounts = len(connected_clients)
        last_quiz_time = 0  # Track last quiz time for cooldown
        POST_QUIZ_REST = 60  # Cooldown after quiz
        
        # IMPORTANT: Mark all existing messages as processed to ignore old quizzes
        print("Initializing... ignoring old messages")
        try:
            first_client = connected_clients[0][1]
            group = await first_client.get_entity(TARGET_GROUP)
            
            # Mark all existing quiz messages as already processed
            async for msg in first_client.iter_messages(group, limit=MAX_SCAN_MESSAGES):
                if msg.sender_id == QUIZ_BOT_ID:
                    text = msg.message or ''
                    if self.is_quiz_message(text):
                        processed_quiz_ids.add(msg.id)
            
            print(f"Marked {len(processed_quiz_ids)} old quizzes as processed")
            await asyncio.sleep(2)
        except:
            pass
        
        # Display initial status
        def show_status(quiz_num=0, submitted=0, status="Waiting for next quiz"):
            clear_screen()
            print(f"Quiz detected: {quiz_num}")
            print(f"Submitted: {submitted}")
            print(f"Total acc submitted: {submitted}/{total_accounts}")
            print(f"{status} {'.' * (int(time.time()) % 10)}")
        
        show_status()
        
        # Keep monitoring running no matter what
        error_count = 0
        max_consecutive_errors = 5
        
        while self.monitoring:
            try:
                # Cooldown check (like original)
                if time.time() - last_quiz_time < POST_QUIZ_REST:
                    await asyncio.sleep(5)
                    continue
                
                # Reconnect dead clients periodically
                if int(time.time()) % 300 == 0:  # Every 5 minutes
                    for acc_id, client in list(connected_clients):
                        if not client.is_connected():
                            try:
                                await client.connect()
                            except:
                                pass
                
                # Use first account to scan for quizzes
                for account_id, client in connected_clients[:1]:  # Only use first account for scanning
                    try:
                        # Get the target group
                        try:
                            group = await client.get_entity(TARGET_GROUP)
                        except:
                            # Try with @ prefix
                            group = await client.get_entity(f"@{TARGET_GROUP}")
                        
                        quiz_found = False
                        bot_messages = 0
                        
                        # Scan messages using iter_messages (like original quiz_monitor.py)
                        async for msg in client.iter_messages(group, limit=MAX_SCAN_MESSAGES):
                            # Only check messages from the quiz bot
                            if msg.sender_id != QUIZ_BOT_ID:
                                continue
                            
                            bot_messages += 1
                            
                            # Skip if already processed
                            if msg.id in processed_quiz_ids:
                                continue
                            
                            text = msg.message or ''
                            
                            # Check if it's a quiz using EXACT method from original
                            if self.is_quiz_message(text):
                                # Check if quiz is recent (not older than 5 minutes)
                                from datetime import datetime, timezone, timedelta
                                now = datetime.now(timezone.utc)
                                msg_time = msg.date
                                if not msg_time.tzinfo:
                                    msg_time = msg_time.replace(tzinfo=timezone.utc)
                                
                                age_minutes = (now - msg_time).total_seconds() / 60
                                
                                # Only process if quiz is less than 5 minutes old
                                if age_minutes > 5:
                                    # Old quiz, mark as processed but don't handle
                                    processed_quiz_ids.add(msg.id)
                                    continue
                                
                                # Mark as processed immediately
                                processed_quiz_ids.add(msg.id)
                                quiz_found = True
                                quiz_count += 1
                                last_quiz_time = time.time()
                                
                                # Show quiz detected
                                clear_screen()
                                print("Quiz detected")
                                print("Asking for ans")
                                
                                # Clear any previous answer cache
                                if hasattr(self, '_current_quiz_answer'):
                                    delattr(self, '_current_quiz_answer')
                                
                                # Create a fake event object for compatibility
                                class FakeEvent:
                                    def __init__(self, message, chat_id, client):
                                        self.message = message
                                        self.chat_id = chat_id
                                        self.client = client
                                
                                # Get answer from AI first (only once)
                                first_event = FakeEvent(msg, group.id, connected_clients[0][1])
                                
                                # Extract question and options for AI
                                text = msg.message or ''
                                question = self.extract_quiz_question(text)
                                
                                # Get options from buttons if available
                                options = []
                                if msg.reply_markup and hasattr(msg.reply_markup, 'rows'):
                                    for row in msg.reply_markup.rows:
                                        for btn in row.buttons:
                                            if btn.text:
                                                options.append(btn.text.strip())
                                
                                # If no buttons, try text parsing
                                if not options:
                                    _, options = self.extract_question_and_options(text)
                                
                                # Get answer from AI
                                if question and options:
                                    answer = await self.get_bot_answer(connected_clients[0][1], question, options)
                                    if answer:
                                        print("Received ans")
                                        # Cache answer for all accounts
                                        self._current_quiz_answer = ord(answer) - ord('A') if answer in 'ABCDE' else 1
                                        
                                        # Also save to questions cache for future
                                        question_key = question.lower().strip()
                                        self.questions[question_key] = {
                                            'answer_letter': answer,
                                            'answer_text': options[self._current_quiz_answer] if self._current_quiz_answer < len(options) else '',
                                            'saved_at': datetime.now().isoformat(),
                                            'original_question': question,
                                            'usage_count': 1
                                        }
                                        self.save_questions()
                                    else:
                                        self._current_quiz_answer = 1  # Default to B
                                else:
                                    self._current_quiz_answer = 1  # Default to B if no question/options
                                
                                # Process quiz for all accounts - like original quiz_monitor.py
                                # Each account independently processes the quiz
                                print("Submitting")
                                submission_start = time.time()
                                submitted_count = 0
                                failed_accounts = []
                                
                                # Fixed batch size: 10 accounts every 5 seconds
                                batch_size = 10
                                batch_delay = 5  # 5 seconds between batches
                                
                                for i in range(0, len(connected_clients), batch_size):
                                    batch = connected_clients[i:i+batch_size]
                                    batch_num = (i // batch_size) + 1
                                    total_batches = (len(connected_clients) + batch_size - 1) // batch_size
                                    
                                    if len(batch) > 1:
                                        print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} accounts)")
                                    
                                    # Each account in batch processes independently
                                    for acc_id, acc_client in batch:
                                        try:
                                            # Each account scans for the quiz message independently
                                            quiz_msg_found = False
                                            
                                            # Scan for the quiz message with this account
                                            # Use the TARGET_GROUP string directly - Telethon handles it
                                            async for m in acc_client.iter_messages(TARGET_GROUP, limit=30):
                                                if m.sender_id == QUIZ_BOT_ID:
                                                    m_text = m.message or ''
                                                    if self.is_quiz_message(m_text) and m.id == msg.id:
                                                        # Found the quiz - now click the button
                                                        if m.reply_markup and hasattr(m.reply_markup, 'rows'):
                                                            # We have buttons, click the answer
                                                            if self._current_quiz_answer is not None:
                                                                try:
                                                                    # Count to find the right button
                                                                    button_idx = 0
                                                                    clicked = False
                                                                    
                                                                    for row_idx, row in enumerate(m.reply_markup.rows):
                                                                        for btn_idx, btn in enumerate(row.buttons):
                                                                            if button_idx == self._current_quiz_answer:
                                                                                # Click this button
                                                                                await m.click(row_idx, btn_idx)
                                                                                submitted_count += 1
                                                                                print(f"  ✓ {acc_id} submitted ({submitted_count}/{total_accounts})")
                                                                                clicked = True
                                                                                quiz_msg_found = True
                                                                                break
                                                                            button_idx += 1
                                                                        if clicked:
                                                                            break
                                                                    
                                                                    if not clicked:
                                                                        # Try direct index
                                                                        try:
                                                                            await m.click(self._current_quiz_answer)
                                                                            submitted_count += 1
                                                                            print(f"  ✓ {acc_id} submitted ({submitted_count}/{total_accounts})")
                                                                            quiz_msg_found = True
                                                                        except:
                                                                            print(f"  ✗ {acc_id} couldn't click button")
                                                                            failed_accounts.append(acc_id)
                                                                except Exception as e:
                                                                    print(f"  ✗ {acc_id} click error: {str(e)[:30]}")
                                                                    failed_accounts.append(acc_id)
                                                            else:
                                                                print(f"  ✗ {acc_id} no answer available")
                                                                failed_accounts.append(acc_id)
                                                        break  # Found the quiz message
                                            
                                            if not quiz_msg_found:
                                                print(f"  ✗ {acc_id} couldn't find quiz")
                                                failed_accounts.append(acc_id)
                                                
                                        except Exception as e:
                                            error_str = str(e)
                                            if "FLOOD" in error_str:
                                                print(f"  ⏳ {acc_id} rate limited")
                                                await asyncio.sleep(2)
                                                failed_accounts.append(acc_id)
                                            elif "Invalid channel" in error_str:
                                                print(f"  ✗ {acc_id} channel error - may need to join group first")
                                                failed_accounts.append(acc_id)
                                            else:
                                                print(f"  ✗ {acc_id} error: {error_str}")
                                                failed_accounts.append(acc_id)
                                        
                                        # Small delay between accounts in same batch
                                        await asyncio.sleep(0.2)
                                    
                                    # Wait 5 seconds before next batch (if not last batch)
                                    if i + batch_size < len(connected_clients):
                                        print(f"Waiting {batch_delay} seconds for next batch...")
                                        await asyncio.sleep(batch_delay)
                                
                                # If some accounts failed, show which ones
                                if failed_accounts:
                                    print(f"\n⚠️ Failed accounts: {', '.join(failed_accounts)}")
                                
                                # Show submission time
                                total_time = time.time() - submission_start
                                print(f"\n✓ All accounts processed")
                                print(f"Total time: {total_time:.1f} seconds")
                                print(f"Submitted: {submitted_count}/{total_accounts}")
                                
                                # Update total submitted count
                                total_submitted = submitted_count
                                
                                # Show final status
                                await asyncio.sleep(2)
                                show_status(quiz_count, total_submitted)
                                
                                # Clear answer cache after all accounts have submitted
                                if hasattr(self, '_current_quiz_answer'):
                                    delattr(self, '_current_quiz_answer')
                                
                                # Exit this account's loop to avoid duplicate processing
                                break
                        
                        # Silent - no debug output
                    
                    except Exception as e:
                        error_str = str(e)
                        if "FLOOD_WAIT" in error_str.upper():
                            wait_time = 60
                            try:
                                match = re.search(r'(\d+)', error_str)
                                if match:
                                    wait_time = int(match.group(1))
                            except:
                                pass
                            print(f"\n⏳ {account_id} rate limited, waiting {wait_time}s...")
                            await asyncio.sleep(wait_time)
                        elif "timeout" not in error_str.lower():
                            # Only print non-timeout errors
                            print(f"\n⚠️ {account_id} scan error: {error_str[:50]}")
                
                # Update waiting display every second
                for i in range(SCAN_INTERVAL):
                    if not quiz_found:
                        show_status(quiz_count, total_submitted, "Waiting for next quiz")
                    await asyncio.sleep(1)
                
                # Reset error count on successful iteration
                error_count = 0
                
            except KeyboardInterrupt:
                print("\n\nStopping...")
                await self.stop_monitoring()
                break
                
            except Exception as e:
                error_count += 1
                error_msg = str(e)
                
                # Log error but keep running
                if error_count < max_consecutive_errors:
                    # Silently continue for minor errors
                    if "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                        # Connection issues - try to reconnect
                        await asyncio.sleep(5)
                        
                        # Try to reconnect first client
                        try:
                            if connected_clients:
                                acc_id, client = connected_clients[0]
                                if not client.is_connected():
                                    await client.connect()
                        except:
                            pass
                    else:
                        # Other errors - wait a bit and continue
                        await asyncio.sleep(10)
                else:
                    # Too many errors - try full reconnect
                    print("\n⚠️ Multiple errors detected, reconnecting...")
                    error_count = 0
                    
                    # Reconnect all clients
                    new_connected = []
                    for acc_id, old_client in connected_clients:
                        try:
                            await old_client.disconnect()
                        except:
                            pass
                        
                        try:
                            # Find account info
                            for acc in self.account_manager.accounts:
                                if acc['account_id'] == acc_id:
                                    new_client = await self.create_client(acc)
                                    if new_client:
                                        new_connected.append((acc_id, new_client))
                                        self.clients[acc_id] = new_client
                                    break
                        except:
                            pass
                    
                    if new_connected:
                        connected_clients = new_connected
                        print(f"✓ Reconnected {len(connected_clients)} accounts")
                        await asyncio.sleep(5)
                        show_status(quiz_count, quiz_count, "Waiting for next quiz")
                    else:
                        print("\n❌ Failed to reconnect. Exiting...")
                        break
    
    async def stop_monitoring(self):
        """Stop monitoring and disconnect clients"""
        self.monitoring = False
        
        for client_name, client in self.clients.items():
            await client.disconnect()
        
        self.clients.clear()
        print("Stopped")


def clear_screen():
    """Clear screen for all platforms"""
    if IS_WINDOWS:
        os.system('cls')
    else:
        os.system('clear')

def get_platform_info():
    """Get platform information string"""
    if IS_TERMUX:
        return "Termux/Android"
    elif IS_WINDOWS:
        return f"Windows {platform.release()}"
    elif IS_MACOS:
        return f"macOS {platform.mac_ver()[0]}"
    elif IS_LINUX:
        return "Linux/VPS"
    else:
        return platform.system()

def show_menu():
    """Display main menu"""
    print("\n" + "="*40)
    print("         QUIZ BOT MANAGER")
    print("="*40)
    print("1. Add Account")
    print("2. Delete Account")
    print("3. List Accounts")
    print("4. Start Monitoring")
    print("5. Change AI Bot")
    print("6. Choose AI Account")
    print("7. Exit")
    print("-"*40)


async def main():
    """Main function"""
    clear_screen()
    print("\nQuiz Bot Manager")
    print(f"Platform: {get_platform_info()}")
    print(f"Data Directory: {DATA_DIR}")
    
    account_manager = AccountManager()
    quiz_monitor = QuizMonitor(account_manager)
    
    print(f"AI Bot: {quiz_monitor.ai_bot} | OTP: {DEFAULT_OTP}")
    if quiz_monitor.ai_account:
        print(f"AI Account: {quiz_monitor.ai_account}")
    
    while True:
        show_menu()
        choice = input("\nEnter your choice (1-7): ").strip()
        
        if choice == '1':
            await account_manager.add_account()
            await asyncio.sleep(1)
            
        elif choice == '2':
            account_manager.delete_account()
            await asyncio.sleep(1)
            
        elif choice == '3':
            account_manager.list_accounts()
            await asyncio.sleep(2)
            
        elif choice == '4':
            await quiz_monitor.start_monitoring()
            
        elif choice == '5':
            quiz_monitor.change_ai_bot()
            await asyncio.sleep(1)
            
        elif choice == '6':
            quiz_monitor.choose_ai_account()
            await asyncio.sleep(1)
            
        elif choice == '7':
            print("\nExiting...")
            await asyncio.sleep(0.5)
            break
            
        else:
            print("Invalid choice")
            await asyncio.sleep(1)


if __name__ == "__main__":
    try:
        # Handle asyncio for different Python versions
        if sys.version_info >= (3, 7):
            asyncio.run(main())
        else:
            # For Python 3.6 and below (some VPS systems)
            loop = asyncio.get_event_loop()
            loop.run_until_complete(main())
    except KeyboardInterrupt:
        print("\n\nGoodbye!")
    except ImportError as e:
        print(f"\nError: Missing required library: {e}")
        print("\nPlease install requirements:")
        print("  pip install telethon==1.34.0")
        if IS_TERMUX:
            print("\nFor Termux, use:")
            print("  pkg install python")
            print("  pip install telethon==1.34.0")
        sys.exit(1)
    except Exception as e:
        print(f"\nFatal error: {e}")
        if IS_WINDOWS and 'charmap' in str(e):
            print("\nWindows encoding error detected.")
            print("Try running: chcp 65001")
            print("Then run the script again.")
        sys.exit(1)


