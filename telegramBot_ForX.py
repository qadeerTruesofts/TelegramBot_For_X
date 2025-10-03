import logging
import requests
import os
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import pickle
import time
import tempfile
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service


COOKIE_FILE = "twitter_cookies.pkl"


# ---------------- LOAD ENV ----------------
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ADMIN_PRIVATE_KEY = eval(os.getenv("ADMIN_PRIVATE_KEY"))  # loads as list of ints
BOT_WALLET = os.getenv("BOT_WALLET")
ADMINS = [int(x) for x in os.getenv("ADMINS").split(",")]
MONGO_URI = os.getenv("MONGO_URI")
X_LOGIN_USER = os.getenv("X_LOGIN_USER")   # Twitter login username/email
X_LOGIN_PASS = os.getenv("X_LOGIN_PASS")   # Twitter login password


# ---------------- LOGGING ----------------
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- MONGO DB ----------------
client = MongoClient(MONGO_URI)
db = client['broke_bot']
users_col = db['users']
tasks_col = db['tasks']
claims_col = db['claims']

# ---------------- HELPER FUNCTION ----------------
def get_next_task_id():
    """Get the next task ID from MongoDB to allow multiple tasks."""
    last_task = tasks_col.find_one(sort=[("task_id", -1)])
    if last_task:
        return last_task["task_id"] + 1
    else:
        return 1

# ---------------- VERIFICATION FUNCTIONS ----------------

# def get_driver(headless=True):
#     chrome_options = Options()
#     if headless:
#         chrome_options.add_argument("--headless=new")
#     chrome_options.add_argument("--disable-gpu")
#     chrome_options.add_argument("--window-size=1920,1080")
#     chrome_options.add_argument("--disable-blink-features=AutomationControlled")
#     service = Service()  # uses chromedriver_binary automatically
#     return webdriver.Chrome(service=service, options=chrome_options)
def get_driver(headless=True):
    options = Options()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")

    service = Service(os.getenv("CHROMEDRIVER", "/usr/bin/chromedriver"))
    driver = webdriver.Chrome(service=service, options=options)
    return driver



def login_and_save_cookies(driver, username, password):
    print("🌐 Opening login page...")
    driver.get("https://x.com/login")
    time.sleep(5)

    print("⌨️ Entering username...")
    user_input = driver.find_element(By.NAME, "text")
    user_input.send_keys(username)
    user_input.send_keys(Keys.RETURN)
    time.sleep(3)

    print("🔑 Entering password...")
    pass_input = driver.find_element(By.NAME, "password")
    pass_input.send_keys(password)
    pass_input.send_keys(Keys.RETURN)
    time.sleep(5)

    pickle.dump(driver.get_cookies(), open(COOKIE_FILE, "wb"))
    print("✅ Login succeed, cookies saved!")


def load_cookies(driver):
    if os.path.exists(COOKIE_FILE):
        logger.info("🍪 Loading cookies...")
        driver.get("https://x.com")
        cookies = pickle.load(open(COOKIE_FILE, "rb"))
        for cookie in cookies:
            driver.add_cookie(cookie)
        logger.info("🍪 Cookies loaded successfully!")
        driver.refresh()
        time.sleep(5)
        return True
    logger.info("⚠️ No cookies found, will login manually.")
    return False


def scrape_replies(username, keyword="$Broke", login_user=None, login_pass=None, headless=True):
    logger.info("🚀 Starting browser...")
    driver = get_driver(headless=headless)

    if not load_cookies(driver):
        if not login_user or not login_pass:
            raise Exception("❌ No cookies and no login credentials provided!")
        login_and_save_cookies(driver, login_user, login_pass)

    url = f"https://x.com/{username}/with_replies"
    logger.info(f"🌐 Opening replies page: {url}")
    driver.get(url)
    time.sleep(5)

    logger.info("🔍 Finding all tweets...")
    tweets = driver.find_elements(By.CSS_SELECTOR, "article")
    logger.info(f"📌 Found {len(tweets)} tweets on replies page.")

    parent_link = None

    for t in tweets:
        text = t.text
        logger.info(f"📝 Checking tweet:\n{text[:120]}...")  # print first 120 chars
        if keyword.lower() in text.lower():
            logger.info(f"✅ Keyword '{keyword}' found in this reply!")

            try:
                reply_link = t.find_element(By.CSS_SELECTOR, "a[href*='/status/']").get_attribute("href")
                logger.info(f"👉 Reply link: {reply_link}")
            except:
                reply_link = None
                logger.info("⚠️ Could not extract reply link.")

            if reply_link:
                logger.info("🌐 Opening reply thread to find parent tweet...")
                driver.get(reply_link)
                time.sleep(5)

                thread = driver.find_elements(By.CSS_SELECTOR, "article")
                logger.info(f"📌 Found {len(thread)} tweets in thread.")

                if len(thread) >= 2:
                    try:
                        parent_link = thread[0].find_element(By.CSS_SELECTOR, "a[href*='/status/']").get_attribute("href")
                        print(f"👑 Parent tweet link: {parent_link}")
                    except:
                        parent_link = None
                        print("⚠️ Could not extract parent tweet link.")
            break

    driver.quit()
    print("🛑 Browser closed.")
    return parent_link


def check_retweet(username, task_url, login_user=None, login_pass=None, headless=True):
    """Check if user retweeted the given task_url"""
    logger.info("🚀 Starting browser for retweet check...")
    driver = get_driver(headless=headless)

    if not load_cookies(driver):
        if not login_user or not login_pass:
            raise Exception("❌ No cookies and no login credentials provided!")
        login_and_save_cookies(driver, login_user, login_pass)

    url = f"https://x.com/{username}"
    logger.info(f"🌐 Opening user profile: {url}")
    driver.get(url)
    time.sleep(5)

    posts = driver.find_elements(By.CSS_SELECTOR, "article a[href*='/status/']")
    logger.info(f"📌 Found {len(posts)} posts on profile.")

    retweeted = False
    for p in posts:
        link = p.get_attribute("href")
        if task_url in link:
            logger.info(f"✅ Retweet found: {link}")
            retweeted = True
            break

    driver.quit()
    print("🛑 Browser closed after retweet check.")
    return retweeted


# ---------------- TELEGRAM BOT HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Welcome! Use /register to register your X username."
    )


async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Please send me your X username (without @)."
    )


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id
    text = update.message.text.strip()

    try:
        # save only X username
        x_username = text.lstrip("@").strip()
        users_col.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"x_username": x_username}},
            upsert=True
        )
        logger.info(f"✅ Registered user {telegram_id} with X={x_username}")
        await update.message.reply_text(f"✅ Registered X username: {x_username}")
    except Exception as e:
        logger.error(f"❌ Registration failed for {telegram_id}, error: {e}")
        await update.message.reply_text(f"❌ Something went wrong. Error: {str(e)}")


# ---------------- ADMIN ADD TASK (BROADCAST) ----------------
async def add_task(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id

    if telegram_id not in ADMINS:
        logger.warning(f"❌ Unauthorized add_task attempt by {telegram_id}")
        await update.message.reply_text("❌ You are not authorized to add tasks.")
        return

    if len(context.args) < 2:
        await update.message.reply_text("Usage: /add_task <tweet_url> <reward>")
        return

    tweet_url = context.args[0]
    reward = float(context.args[1])

    task_id = get_next_task_id()

    task = {"task_id": task_id, "url": tweet_url, "reward": reward}
    tasks_col.insert_one(task)
    claims_col.insert_one({"task_id": task_id, "telegram_ids": []})

    logger.info(f"✅ Task #{task_id} added by admin {telegram_id}, URL={tweet_url}, Reward={reward}")

    # Prepare task message
    keyboard = [
        [InlineKeyboardButton("Go to Post", url=tweet_url),
         InlineKeyboardButton("Verify", callback_data=f"verify|{task_id}|0")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = (
        f"**📌 New Task #{task_id}!**\n\n"
        f"**Comment $Broke on this post and Retweet this post.**\n\n"
        f"💰 Reward: {reward} Broke Coin\n"
        f"🔗 Tweet: {tweet_url}"
    )

    # Broadcast to all registered users
    users = users_col.find({})
    success_count, fail_count = 0, 0

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=message_text,
                parse_mode='Markdown',
                reply_markup=reply_markup
            )
            success_count += 1
        except Exception as e:
            logger.error(f"❌ Failed to send task to {user['telegram_id']}: {e}")
            fail_count += 1

    await update.message.reply_text(
        f"✅ Task #{task_id} broadcasted.\n📨 Sent: {success_count}, ❌ Failed: {fail_count}"
    )


# ---------------- ADMIN BROADCAST ----------------
async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_id = update.message.from_user.id

    if telegram_id not in ADMINS:
        logger.warning(f"❌ Unauthorized broadcast attempt by {telegram_id}")
        await update.message.reply_text("❌ You are not authorized to broadcast messages.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return

    message_text = " ".join(context.args)

    users = users_col.find({})
    success_count, fail_count = 0, 0

    for user in users:
        try:
            await context.bot.send_message(
                chat_id=user["telegram_id"],
                text=f"📢 Broadcast:\n\n{message_text}"
            )
            success_count += 1
        except Exception as e:
            logger.error(f"❌ Failed to send broadcast to {user['telegram_id']}: {e}")
            fail_count += 1

    await update.message.reply_text(
        f"✅ Broadcast complete.\n📨 Sent: {success_count}, ❌ Failed: {fail_count}"
    )


# ---------------- HANDLE BUTTON CLICKS ----------------
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split("|")

    if data[0] == "verify":
        task_id = int(data[1])
        telegram_id = query.from_user.id
        user = users_col.find_one({"telegram_id": telegram_id})

        if not user:
            logger.warning(f"❌ Unregistered user {telegram_id} tried to verify Task #{task_id}")
            await query.message.reply_text("❌ You are not registered. Use /register first.")
            return

        claim = claims_col.find_one({"task_id": task_id})
        if telegram_id in claim["telegram_ids"]:
            logger.warning(f"⚠️ User {telegram_id} tried to re-claim Task #{task_id}")
            await query.message.reply_text("❌ You already claimed this task.")
            return
        
        # ---------------- NEW PART ----------------
        task_url = tasks_col.find_one({"task_id": task_id})["url"]
        username = user["x_username"]

        logger.info(f"🔎 Checking reply for user={username} on task={task_url}")
        parent_link = scrape_replies(
            username=username,
            keyword="$Broke",
            login_user=X_LOGIN_USER,
            login_pass=X_LOGIN_PASS,
            headless=True
        )
        if parent_link and task_url in parent_link:
            logger.info("✅ Comment verification passed (reply with $Broke found)")
        else:
            logger.warning("❌ Comment verification failed (no matching reply found)")

        logger.info(f"🔎 Checking retweet for user={username} on task={task_url}")
        retweeted = check_retweet(
            username=username,
            task_url=task_url,
            login_user=X_LOGIN_USER,
            login_pass=X_LOGIN_PASS,
            headless=True
        )
        if retweeted:
            logger.info("✅ Retweet verification passed")
        else:
            logger.warning("❌ Retweet verification failed (no retweet found)")

        if parent_link and task_url in parent_link and retweeted:
            # ✅ Both reply + retweet found
            claims_col.update_one(
                {"task_id": task_id},
                {"$push": {"telegram_ids": telegram_id}}
            )
            reward = tasks_col.find_one({"task_id": task_id})['reward']

            # Edit task message
            await query.edit_message_text(f"✅ Verified! {reward} Broke Coin will be sent to your wallet.")
            logger.info(f"✅ Verification success for {telegram_id}, task={task_id}")


            # Send congratulation message to user
            await query.message.reply_text(
                f"🎉 Congratulations {query.from_user.first_name}!! "
                f"You have completed Task #{task_id}.\n\n"
                f"💰 Reward: {reward} Broke Coin will be added to your account."
            )
        else:
            # ❌ Verification failed
            logger.warning(f"❌ Verification failed for {telegram_id}, task={task_id}")
            await query.message.reply_text(
                "❌ Verification failed.\nMake sure you commented '$Broke' and retweeted the task post."
            )

# ---------------- MAIN ----------------
def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("register", register))
    app.add_handler(CommandHandler("add_task", add_task))  # Admin only
    app.add_handler(CommandHandler("broadcast", broadcast))  # Admin only
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(CallbackQueryHandler(button))
    logger.info("🤖 Bot started and running...")
    app.run_polling()


if __name__ == "__main__":
    main()
