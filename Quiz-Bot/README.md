# 🤖 Quiz Bot Manager - Terminal Edition

A lightweight, terminal-based Telegram quiz automation system that monitors quiz messages and automatically provides intelligent answers using AI assistance.

## ✨ Features

- **🎯 Automatic Quiz Detection** - Monitors FUNToken_OfficialChat group for quiz messages
- **🧠 AI-Powered Answers** - Gets intelligent answers from @askplexbot with 20-second research
- **💾 Answer Caching** - Saves answers for instant response to repeated questions
- **👥 Multi-Account Support** - Manage multiple Telegram accounts from one interface
- **🔐 Session Management** - Saves login sessions for quick reconnection
- **📱 2FA Support** - Handles two-factor authentication seamlessly
- **🖥️ Clean Terminal UI** - Simple, non-cluttered command-line interface

## 📋 Prerequisites

- Python 3.7 or higher
- Telegram API credentials (API ID and API Hash)
- Phone number registered with Telegram

## 🚀 Quick Start

### 1. Installation

```bash
# Clone or download the project
cd quiz-bot-manager

# Install dependencies
pip install telethon==1.34.0
```

### 2. Get Telegram API Credentials

1. Visit https://my.telegram.org
2. Log in with your phone number
3. Go to "API Development Tools"
4. Create a new application
5. Copy your `API ID` and `API Hash`

### 3. Run the Bot

```bash
python3 main.py
```

## 📖 Usage Guide

### Main Menu Options

```
========================================
         QUIZ BOT MANAGER
========================================
1. Add Account
2. Delete Account
3. List Accounts
4. Start Monitoring
5. Exit
----------------------------------------
```

### Adding Your First Account

1. Select option `1` from the main menu
2. Enter your Telegram API credentials:
   - **API ID**: Your numeric API ID
   - **API Hash**: Your API hash string
   - **Phone**: Your phone number with country code (e.g., +1234567890)
   - **Account Name**: A friendly name for this account
3. Enter the OTP code sent to your Telegram
4. If you have 2FA enabled, enter your 2FA password
5. The account will be saved and ready to use

### Starting Quiz Monitoring

1. Select option `4` from the main menu
2. The bot will:
   - Connect to your account(s)
   - Join the FUNToken_OfficialChat group
   - Start scanning for quiz messages every 5 seconds
   - When a quiz is detected:
     - Send the question to @askplexbot
     - Wait 20 seconds for research
     - Extract the answer
     - Submit it to the group

### Example Output

```
🎯 [14:23:45] Quiz detected!
  Account: myaccount
  Question: What is the native token of Ethereum?...
  🔍 Getting answer from @askplexbot...
    Sending to @askplexbot...
    Waiting 20s for research...
  ✅ Got answer from bot: C
  📤 Submitted answer: C ✓
```

## 🔧 Configuration

### Default Settings

- **Target Group**: `@FUNToken_OfficialChat`
- **Quiz Bot ID**: `7901924377`
- **AI Assistant**: `@askplexbot`
- **Research Time**: 20 seconds
- **Scan Interval**: 5 seconds
- **Default OTP**: `12345` (press Enter to use)

### Files Structure

```
quiz-bot-manager/
├── main.py           # Main application
├── accounts.json     # Stored account credentials
├── questions.json    # Cached quiz answers
├── requirements.txt  # Python dependencies
└── *.session        # Telegram session files (created automatically)
```

## 💡 Tips & Tricks

### Session Management
- Sessions are saved automatically after first login
- No need to re-enter OTP unless session expires
- Session files are named after your account names

### Answer Caching
- Answers are saved in `questions.json`
- Repeated questions get instant cached answers
- Cache grows automatically as you encounter new questions

### Multiple Accounts
- Add multiple accounts for parallel monitoring
- Each account monitors independently
- All accounts share the same answer cache

### Troubleshooting

**"Session expired" message**
- The bot will automatically ask for a new OTP
- Enter the code to create a new session

**"No accounts could be connected"**
- Check your internet connection
- Verify API credentials are correct
- Make sure the phone number is active

**Quiz not being detected**
- Ensure you're a member of FUNToken_OfficialChat
- Check if the account is not banned from the group
- Verify the bot is running (you should see "Scanning every 5 seconds")

## 🔒 Security Notes

- API credentials are stored locally in `accounts.json`
- Session files are stored in the current directory
- 2FA passwords are optionally saved (you can skip saving)
- All data is stored locally, nothing is sent to external servers

## 📊 How It Works

1. **Monitoring**: Scans the target Telegram group every 5 seconds
2. **Detection**: Identifies quiz messages from bot ID 7901924377
3. **AI Processing**: Sends questions to @askplexbot with research instructions
4. **Answer Extraction**: Waits 20 seconds and extracts the single-letter answer
5. **Submission**: Automatically sends the answer back to the group
6. **Caching**: Saves answers for future use

## 🛠️ Advanced Features

### Answer Extraction Methods
The bot can extract answers in multiple formats:
- Direct: "Answer: B" or "The answer is C"
- Single letter on its own line
- Letter at the end of message
- Any single letter found as word boundary

### Fallback System
- If @askplexbot doesn't respond: Uses option B
- If connection fails: Uses cached answer if available
- If no cache exists: Defaults to option B

## 📝 Requirements

- **Python**: 3.7+
- **Library**: telethon==1.34.0
- **OS**: Windows, Linux, macOS
- **Network**: Stable internet connection
- **Telegram**: Active account with API access

## ⚡ Performance

- **Response Time**: ~22 seconds for new questions
- **Cached Response**: Instant
- **Memory Usage**: Minimal (~50MB)
- **CPU Usage**: Low (< 5%)

## 🤝 Support

For issues or questions:
1. Check the troubleshooting section above
2. Verify all prerequisites are met
3. Ensure you're using the latest version

## 📄 License

This project is for educational purposes. Use responsibly and in accordance with Telegram's Terms of Service.

---

**Note**: This bot is designed for automated quiz participation. Ensure you have permission to use automation in the target group.