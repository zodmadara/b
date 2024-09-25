import requests
import time
import re
from bs4 import BeautifulSoup
import logging
from urllib.parse import urlparse, urlunparse
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, CallbackContext
import sys

# Set up logging to only show critical issues
logging.basicConfig(level=logging.CRITICAL)

TELEGRAM_TOKEN = '8031298999:AAHqydBkrLcb9uiWt06atqxoq2q61d2TXwk'
TELEGRAM_CHAT_ID = '1984468312'

def clean_url(url):
    """Remove checkout-specific paths and return the base URL."""
    parsed_url = urlparse(url)
    base_url = urlunparse((
        parsed_url.scheme,
        parsed_url.netloc,
        '/',
        '',
        '',
        ''
    ))
    return base_url

def validate_shop_url(shop_url):
    """Ensure the shop URL is correctly formatted."""
    if not shop_url.startswith('https://'):
        if not shop_url.startswith('http://'):
            shop_url = 'https://' + shop_url
        else:
            shop_url = 'https://' + shop_url[7:]
    return shop_url

def detect_graphql(shop_url):
    """Check for GraphQL endpoints."""
    graphql_patterns = [
        '/graphql',
        '/admin/api/2023-01/graphql.json',
        '/api/2023-01/graphql.json'
    ]
    
    test_query = {"query": "{ __typename }"}

    try:
        shop_url = validate_shop_url(shop_url)
        
        for pattern in graphql_patterns:
            graphql_url = f'{shop_url}{pattern}'
            try:
                graphql_response = requests.post(graphql_url, json=test_query)
                if graphql_response.status_code == 200 and "__typename" in graphql_response.text:
                    return True
            except requests.exceptions.RequestException:
                continue
        
        response = requests.get(shop_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        scripts = soup.find_all('script')
        for script in scripts:
            if script.get('src'):
                script_url = script['src']
                if re.search(r'graphql', script_url, re.IGNORECASE):
                    return True
            elif script.string:
                if re.search(r'\bgraphql\b', script.string, re.IGNORECASE) or \
                   re.search(r'\bquery\b', script.string, re.IGNORECASE) or \
                   re.search(r'\bmutation\b', script.string, re.IGNORECASE):
                    return True
        
        return False
    except requests.exceptions.RequestException:
        return False

def find_cheapest_product(shop_url):
    """Find the cheapest product and check for GraphQL endpoints."""
    start_time = time.time()

    base_url = clean_url(shop_url)
    graphql_detected = detect_graphql(base_url)

    products_url = f'{base_url}/products.json?limit=250'

    try:
        response = requests.get(products_url)
        response.raise_for_status()
        products = response.json().get('products', [])
        
        soup = BeautifulSoup(response.text, 'html.parser')

        if not products:
            result = "No products found or unable to retrieve product data."
            print(result)
            send_telegram_message(result)
            return

        cheapest_product = None
        for product in products:
            for variant in product['variants']:
                price = float(variant['price'])
                if price > 0:
                    if cheapest_product is None or price < cheapest_product['price']:
                        cheapest_product = {
                            'name': product['title'],
                            'price': price,
                            'variant_id': variant['id'],
                            'product_url': f"{base_url}/products/{product['handle']}?variant={variant['id']}"
                        }

        if cheapest_product:
            checkout_url = f"{base_url}/cart/{cheapest_product['variant_id']}:1?checkout[guest]=true"
            time_taken = round(time.time() - start_time, 2)
            
            result = f"""
- - - - - - - - - Shopify Hunter - - - - - - -
⸙ Shopify Site ⌁ {base_url}
⸙ Product Name ⌁ {cheapest_product['name']}
⸙ Product PRICE ⌁ ${cheapest_product['price']:.2f}
⸙ Variant ID ⌁ {cheapest_product['variant_id']}
⸙ Product URL ⌁ {cheapest_product['product_url']}
⸙ Graphql ⌁ {'yes' if graphql_detected else 'no'}
⸙ Time Taken ⌁ {time_taken}(s)
⸙ Checkout URL ⌁ {checkout_url}
⸙ Developed By ⌁ @ZodMadara 
"""
            print(result)
            send_telegram_message(result)
            return result
        else:
            result = "No products with a price greater than 0 found."
            print(result)
            send_telegram_message(result)
    
    except requests.exceptions.RequestException as e:
        result = f"Error occurred: {e}"
        print(result)
        send_telegram_message(result)

def send_telegram_message(message):
    """Send a message to a Telegram chat."""
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        'chat_id': TELEGRAM_CHAT_ID,
        'text': message
    }
    try:
        response = requests.post(telegram_url, json=payload)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        print(f"Failed to send message to Telegram: {e}")

async def handle_message(update: Update, context: CallbackContext):
    """Handle incoming messages from Telegram."""
    shop_url = update.message.text.strip()
    if shop_url:
        await update.message.reply_text("URL received: " + shop_url)
        find_cheapest_product(shop_url)
    else:
        await update.message.reply_text("No URL received. Please try again.")

def telegram_mode():
    """Receive URLs from Telegram and process them."""
    # Send a message to Telegram indicating that the bot is ready
    print("Ready to receive URLs from the console.")
    
    send_telegram_message("The bot is now ready to receive URLs. Please send a Shopify URL to begin.")

    # Create an Application object
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Add message handler for receiving URLs
    message_handler = MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    application.add_handler(message_handler)
    
    # Run the bot
    application.run_polling()

def console_mode():
    """Receive URLs via the console and process them."""
    while True:
        shop_url = input("Enter a Shopify URL (or type 'exit' to quit): ").strip()
        if shop_url.lower() == 'exit':
            print("Exiting Console mode.")
            break
        if shop_url:
            find_cheapest_product(shop_url)
        else:
            print("No URL provided. Please try again.")

        another_check = input("Do you want to perform another check? (yes/no): ").strip().lower()
        if another_check != 'yes':
            print("Exiting Console mode.")
            break

def main():
    """Main function to choose between console and Telegram modes."""
    mode = input("Choose mode (1 for Console, 2 for Telegram): ").strip()
    
    if mode == '1':
        console_mode()
    elif mode == '2':
        telegram_mode()
    else:
        print("Invalid choice. Please choose 1 for Console or 2 for Telegram.")

if __name__ == "__main__":
    main()

