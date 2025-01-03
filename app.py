import os
import time
import threading
import pyqrcode
import requests
from solana.rpc.api import Client
from telebot import types
import telebot
import html
import schedule
from collections import deque
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

API_TOKEN = os.getenv('TELEBOT_API_TOKEN')
FOMO_SITE = os.getenv('FOMO_SITE')
FOMO_TWITTER = os.getenv('FOMO_TWITTER')
FOMO_TELEGRAM = os.getenv('FOMO_TELEGRAM')
bot_link = os.getenv('BOT_LINK')
CHANNEL_ID = os.getenv('CHANNEL_ID')
RECIPIENT_PUBLIC_KEY = os.getenv('RECIPIENT_PUBLIC_KEY')
FOMO_IMG = os.getenv('FOMO_IMG')

bot = telebot.TeleBot(API_TOKEN)


# Dictionaries for tracking user activities
user_submissions = {}
user_selected_plans = {}
used_hashes = {}
active_posts = {}


class FOMOGateway:
    def __init__(self):
        self.client = Client("https://api.mainnet-beta.solana.com", timeout=30)
        self.recipient_public_key =  RECIPIENT_PUBLIC_KEY
        self.plans = {
            'daily': 0.7,    
            'weekly': 3,     
            'monthly': 10   
        }

    def generate_payment_request(self, chat_id, plan):
        amount_sol = self.plans.get(plan)
        if amount_sol is None:
            raise ValueError("Invalid plan selected")

        recipient_address = self.recipient_public_key
        solana_pay_url = f"solana:{recipient_address}?amount={amount_sol}&label=Payment&message=Pay%20{amount_sol}%20SOL%20for%20{plan.capitalize()}%20Plan"

        qr_code = pyqrcode.create(solana_pay_url)
        qr_code_file = f'payment_qr_{chat_id}_{plan}.png'
        qr_code.png(qr_code_file, scale=8)

        return solana_pay_url, qr_code_file, amount_sol

    def verify_transaction_with_solanafm(self, tx_hash, expected_amount):
        if tx_hash in used_hashes:
            return False, "This transaction has already been verified."

        solanafm_url = f"https://api.solana.fm/v0/transfers/{tx_hash}"
        try:
            response = requests.get(solanafm_url)
            response.raise_for_status()
            transaction = response.json()

            if transaction["status"] != "success":
                return False, "Transaction is not successful."

            for transfer in transaction["result"].get("data", []):
                if transfer["action"] == "transfer" and transfer["status"] == "Successful":
                    destination = transfer.get("destination")
                    amount = transfer.get("amount", 0)

                    if destination == self.recipient_public_key and amount == int(expected_amount * 1e9):
                        used_hashes[tx_hash] = True
                        return True, f"Payment of {amount / 1e9} SOL confirmed for {destination}!"
            return False, "Transaction details do not match the expected amount or recipient."
        except requests.RequestException as e:
            return False, f"Error verifying payment: {str(e)}"

class PendingQueue:
    def __init__(self):
        self.queue = deque()

    def add(self, item):
        self.queue.append(item)

    def get_next(self):
        if self.queue:
            return self.queue.popleft()
        return None

    def size(self):
        return len(self.queue)

pending_queue = PendingQueue()

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    main_menu(message.chat.id)

def main_menu(chat_id):
    message = (
        f"🔮 Welcome to FOMO Trending 🔮\n\n\n"
        f"🚀 Discover trending cryptocurrencies\n"
        f"📈 Analyze token metrics\n"
        f"👥 Join community discussions\n"
        f"🛠️ Customize your dashboard\n\n\n"
        )
    if FOMO_SITE:
        SITE = f"<a href='{html.escape(FOMO_SITE)}'> 🌐 Website</a>"
        message += f"{SITE}\n"
    if FOMO_TWITTER:
        twitter = f"<a href='{html.escape(FOMO_TWITTER)}'>🐦 Twitter</a>"
        message += f"{twitter}\n"
    if FOMO_TELEGRAM:
        telegram = f"<a href='{html.escape(FOMO_TELEGRAM)}'> 💬 Telegram</a>"
        message += f"{telegram}\n\n"

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Submit Coin", callback_data="submit_coin"),
              types.InlineKeyboardButton("Pending Submissions", callback_data="view_pending"),
              types.InlineKeyboardButton("Clear Pending", callback_data="clear_pending"))
    bot.send_photo(chat_id,FOMO_IMG  ,caption=message, reply_markup=markup, parse_mode="HTML")


@bot.callback_query_handler(func=lambda call: call.data == "submit_coin")
def handle_coin_submission(call):
    chat_id = call.message.chat.id
    if chat_id in user_submissions:
        bot.send_message(chat_id, "You already have an active submission. Please complete it first.")
        return

    bot.send_message(chat_id, "Please enter your coin details in the format: `Coin Name - Address - Link`")
tt
@bot.message_handler(func=lambda message: message.text and "-" in message.text)
def process_coin_details(message):
    chat_id = message.chat.id
    try:
        details = message.text.strip().split(" - ")
        if len(details) != 3:
            raise ValueError("Invalid format")

        name, contract_address, link = details
        user_submissions[chat_id] = {
            "name": name.strip(),
            "contract_address": contract_address.strip(),
            "link": link.strip()
        }

        bot.send_message(
            chat_id,
            f"✅ Submission received!\n\n"
            f"🔹 Name: {name.strip()}\n"
            f"🔹 Contract Address: `{contract_address.strip()}`\n"
            f"🔹 Link: [{name.strip()}]({link.strip()})",
            parse_mode="Markdown"
        )
        pending_queue.add({"chat_id": chat_id, "details": user_submissions[chat_id]})
        show_payment_menu(chat_id)
    except ValueError:
         bot.send_message(
            chat_id,
            "❌ Invalid format. Please use:\n"
            "`Coin Name - Address - Link`",
            parse_mode="Markdown"
        )


def show_payment_menu(chat_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("🌅 Daily", callback_data="plan_daily"),
              types.InlineKeyboardButton("⏳ Weekly", callback_data="plan_weekly"),
              types.InlineKeyboardButton("🚀 Fast Track", callback_data="plan_monthly"))
    bot.send_message(
        chat_id,
        "🛍️ Payment Plans\nChoose a plan:\n"
        "🌅 Daily Plan (0.7 SOL)\n"
        "⏳ Weekly Plan (3 SOL)\n"
        "🚀 Fast Track (10 SOL)",
        reply_markup=markup
    )


@bot.callback_query_handler(func=lambda call: call.data.startswith("plan_"))
def process_selected_plan(call):
    chat_id = call.message.chat.id
    if chat_id not in user_submissions:
        bot.send_message(chat_id, "You must submit your coin details first. Use /start to begin.")
        return

    plan = call.data.split("_")[1]
    user_selected_plans[chat_id] = plan
    gateway = FOMOGateway()
    try:
        solana_pay_url, qr_code_file, amount_sol = gateway.generate_payment_request(chat_id, plan)

        bot.send_message(chat_id, f"To complete payment for the {plan.capitalize()} Plan, scan the QR code below or use this address:\n"
                                 f"`{gateway.recipient_public_key}`\n\nExpected Amount: {amount_sol} SOL", parse_mode="Markdown")

        with open(qr_code_file, 'rb') as qr_file:
            bot.send_photo(chat_id, qr_file)

        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("✅ Verify Payment", callback_data="verify_payment"))
        bot.send_message(chat_id, "After payment, click the button below to verify.", reply_markup=markup)
    except ValueError as e:
        bot.send_message(chat_id, str(e))

@bot.callback_query_handler(func=lambda call: call.data == "verify_payment")
def ask_for_transaction_url(call):
    chat_id = call.message.chat.id
    bot.send_message(chat_id, "Please send the transaction hash to verify the payment.")

@bot.message_handler(func=lambda message: message.text.strip())
def verify_payment(message):
    chat_id = message.chat.id
    tx_hash = message.text.strip()

    if chat_id not in user_selected_plans or chat_id not in user_submissions:
        bot.send_message(chat_id, "No plan or submission found. Please restart with /start.")
        return

    plan = user_selected_plans[chat_id]
    details = user_submissions[chat_id]
    gateway = FOMOGateway()
    expected_amount = gateway.plans[plan]

    is_verified, result_message = gateway.verify_transaction_with_solanafm(tx_hash, expected_amount)
    if not is_verified:
        bot.send_message(chat_id, f" ❌ Payment verification failed: {result_message}")
        return

    bot.send_message(chat_id, "✅ Payment verified! Your post is now being processed.")
    
    # Process the submission from the pending queue
    process_pending_submission(chat_id)

def process_pending_submission(chat_id):
    item = pending_queue.get_next()
    if item and item['chat_id'] == chat_id:
        details = item['details']
        # Fetch token data from Dexscreener
        dexscreener_api_url = f"https://api.dexscreener.com/latest/dex/tokens/{details['contract_address']}"
        dexscreener_response = requests.get(dexscreener_api_url)
        if dexscreener_response.status_code != 200:
            bot.send_message(chat_id, "Failed to fetch token details. Please try again later.")
            return
        
        dexscreener_data = dexscreener_response.json()
        pair_data = dexscreener_data["pairs"][0]

        # Extract relevant information
        market_cap = pair_data.get("marketCap", 0)
        liquidity_usd = pair_data.get("liquidity", {}).get("usd", 0)
        h24_volume = pair_data.get("volume", {}).get("h24", 0)
        openGraph = pair_data.get("info", {}).get("openGraph", "")
        symbol = pair_data.get("baseToken", {}).get("symbol", "N/A")
        dexscreener_link = pair_data.get("url", "N/A")
        boosts = pair_data.get("boosts", None)
        website_link = pair_data.get("websites", [{}])[0].get("url")
        socials = pair_data.get("info", {}).get("socials", [])
        twitter_link = next((s["url"] for s in socials if s["type"] == "twitter"), None)
        telegram_link = next((s["url"] for s in socials if s["type"] == "telegram"), None)

        # Prepare message
        symbol_link = f"<a href='{html.escape(details['link'])}'>{symbol}</a>"
        fomo_link = f"<a href='{html.escape(bot_link)}'>FOMO Trending</a>"
        snipe = "<a href='https://t.me/GMGN_sol04_bot?start'>GMGN</a>"
        message = (
            f"Sponsored Post\n\n\n"
            f"{symbol_link} is on {fomo_link}\n\n"
            f"CA: <code>{details['contract_address']}</code>\n\n"
            f"Market Cap: ${market_cap:,.2f}\n\n"
            f"Liquidity: ${liquidity_usd:,.2f}\n\n\n"
            f"🔒 Lock in your snipes with {snipe} on Telegram!\n\n"
        )
        if website_link:
            website = f"<a href='{html.escape(website_link)}'>Website</a>"
            message += f"{website}\n"
        if twitter_link:
            twitter = f"<a href='{html.escape(twitter_link)}'>Twitter</a>"
            message += f"{twitter}\n"
        if telegram_link:
            telegram = f"<a href='{html.escape(telegram_link)}'>Telegram</a>"
            message += f"{telegram}\n\n"
        if boosts:
            message += f"Dexscreener Paid:✅\n"

        message +=f"CTO:✅\n"

        gmgn_link = f"https://gmgn.ai/sol/token/{details['contract_address']}?chain=sol"

        # Post message
        markup = telebot.types.InlineKeyboardMarkup()
        markup.row_width = 2
        markup.add(telebot.types.InlineKeyboardButton("Dexscreener", url=dexscreener_link),
                   telebot.types.InlineKeyboardButton("GMGN", url=gmgn_link))

        post_message = bot.send_photo(CHANNEL_ID, openGraph, caption=message, reply_markup=markup, parse_mode="HTML")
        if post_message and hasattr(post_message, "message_id"):
            active_posts[chat_id] = post_message.message_id
            # Schedule deletion
            threading.Thread(target=delete_post_after_duration, args=(chat_id, user_selected_plans[chat_id])).start()
            del user_submissions[chat_id]
            del user_selected_plans[chat_id]
        else:
            bot.send_message(chat_id, "⚠️ Unable to store your post properly. Please try again.")
    else:
        bot.send_message(chat_id, " 💠 Your submission was not found in the pending queue.")

def delete_post_after_duration(chat_id, plan):
    duration = {'daily': 86400, 'weekly': 604800, 'monthly': 2592000}.get(plan)
    time.sleep(duration)
    if chat_id in active_posts:
        message_id = active_posts.pop(chat_id, None)  # Safely retrieve and remove the message_id
        if message_id:
            try:
                bot.delete_message(CHANNEL_ID, message_id)
                bot.send_message(chat_id, "Your post has expired.")
            except telebot.apihelper.ApiTelegramException as e:
                print(f"Failed to delete message: {e}")
        else:
            print(f"No valid message_id found for chat_id {chat_id}.")

@bot.callback_query_handler(func=lambda call: call.data == "view_pending")
@bot.message_handler(commands=['view_pending'])
def view_pending_submissions(call):
    pending_count = pending_queue.size()
    bot.send_message(call.message.chat.id, f"There are {pending_count} pending submissions.")

@bot.callback_query_handler(func=lambda call: call.data == "clear_pending")
@bot.message_handler(commands=['clear_pending'])
def clear_pending_submissions(call):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("Clear All", callback_data="clear_all"),
              types.InlineKeyboardButton("Clear One", callback_data="clear_one"))
    bot.send_message(call.message.chat.id, "Choose an option:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data == "clear_all")
@bot.message_handler(commands=['clear_all'])
def clear_all_pending(call):
    pending_queue.queue.clear()
    bot.send_message(call.message.chat.id, "All pending submissions cleared.")

@bot.callback_query_handler(func=lambda call: call.data == "clear_one")
@bot.message_handler(commands=['clear_one'])
def clear_one_pending(call):
    item = pending_queue.get_next()
    if item:
        bot.send_message(call.message.chat.id, f"Cleared submission for {item['details']['name']}.")
    else:
        bot.send_message(call.message.chat.id, "No pending submissions to clear.")

def rate_limiting_decorator(max_calls, period):
    def decorator(func):
        calls = []
        def wrapper(*args, **kwargs):
            nonlocal calls
            now = time.time()
            calls = [t for t in calls if t > now - period]
            if len(calls) >= max_calls:
                raise Exception("Rate limit exceeded")
            calls.append(now)
            return func(*args, **kwargs)
        return wrapper
    return decorator

@rate_limiting_decorator(max_calls=5, period=60)
@bot.message_handler(commands=['submit_coin'])
def submit_coin(message):
    """Send the main menu."""
    markup = types.InlineKeyboardMarkup()
    bot.send_message(
        message.chat_id,
        "🏠 Main Menu\nChoose an option below:\n\n"
        "📝 Submit the coin you want to be posted on FOMO TRENDING.\n"
        "Use the format:\n`Coin Name - Address - Link`",
        reply_markup=markup
    )

if __name__ == '__main__':
    bot.polling()

