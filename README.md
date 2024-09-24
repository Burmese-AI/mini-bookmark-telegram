# Mini Bookmark Telegram

Mini Bookmark Telegram is a web application that allows users to save and manage bookmarks through a Telegram bot interface.

## Features

- Parse and extract contents using the Telegram bot [@saveitPro_bot](https://t.me/saveitPro_bot)
- Save parsed contents for later reference
- Delete saved contents when no longer needed
- Web interface for easy bookmark management

## Technologies Used

- Python
- JavaScript
- CSS
- HTML
- Flask (Python web framework)
- Vercel (for deployment)

## Setup and Installation

1. Clone the repository:
   ```
   git clone https://github.com/tom2811/mini-bookmark-telegram.git
   ```

2. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

3. Set up your Telegram bot and obtain the necessary API credentials.

4. Create a `.env` file in the root directory and add your Telegram bot token:
   ```
   BOT_TOKEN=your_bot_token_here
   ```

5. Run the Flask application:
   ```
   python parser.py
   ```