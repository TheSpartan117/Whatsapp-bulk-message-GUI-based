from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from time import sleep
from urllib.parse import quote
import os
import platform
import sys
import pandas as pd

DELAY = 10
SEND_DELAY = 2
# Brief pause so the button registers the click correctly
PRE_CLICK_DELAY = 1
# Wait for WhatsApp Web to process the send before navigating away
POST_SEND_DELAY = 3

# Bundled data-file directory: sys._MEIPASS when frozen, script dir otherwise.
_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# Chrome user data directory — isolated WABulker profile, per OS.
_sys = platform.system()
if _sys == 'Windows':
    CHROME_USER_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'WABulker', 'User Data')
elif _sys == 'Darwin':
    CHROME_USER_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'WABulker')
else:  # Linux
    CHROME_USER_DATA_DIR = os.path.join(os.path.expanduser('~'), '.config', 'WABulker')

def _attempt_send(driver, url, name, number, log_fn, delay, send_delay):
	driver.get(url)
	try:
		click_btn = WebDriverWait(driver, delay).until(
			EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']")))
	except Exception as e:
		log_fn(f"\nCould not send to {name} ({number}): {e}")
		log_fn("Make sure your phone and computer is connected to the internet.")
		log_fn("If there is an alert, please dismiss it.")
		return False
	sleep(PRE_CLICK_DELAY)
	click_btn.click()
	sleep(send_delay)
	sleep(POST_SEND_DELAY)
	log_fn(f'Message sent to: {name} ({number})')
	return True


def send_messages(driver, contacts, template, log_fn=print, stop_event=None, progress_fn=None, delay=None, send_delay=None):
	_delay = delay if delay is not None else DELAY
	_send_delay = send_delay if send_delay is not None else SEND_DELAY

	for idx, contact in enumerate(contacts):
		if stop_event is not None and stop_event.is_set():
			log_fn("Sending stopped by user.")
			break

		name = contact['name']
		number = contact['number']

		number = str(number).strip()
		if number == "":
			continue
		if not number.isdigit():
			log_fn(f"  Skipping {name}: invalid number '{number}' (must contain digits only).")
			continue
		# Prepend India country code for bare 10-digit numbers (Indian customers only)
		if len(number) == 10:
			number = "91" + number
		# Validate final length is within E.164 range (10–15 digits)
		if not (10 <= len(number) <= 15):
			log_fn(f"  Skipping {name}: number '{number}' has invalid length ({len(number)} digits).")
			continue

		personalized_message = template
		for key, value in contact['fields'].items():
			personalized_message = personalized_message.replace('{' + key + '}', value)
		encoded_message = quote(personalized_message)

		log_fn(f'\n{idx+1}/{len(contacts)} => Sending message to {name} ({number}).')
		url = 'https://web.whatsapp.com/send?phone=' + number + '&text=' + encoded_message
		for i in range(3):
			if stop_event is not None and stop_event.is_set():
				log_fn("Sending stopped by user.")
				return
			if _attempt_send(driver, url, name, number, log_fn, _delay, _send_delay):
				if progress_fn is not None:
					progress_fn(idx + 1, len(contacts))
				break
			log_fn(f"  Retry {i+1}/3 for {name}...")

def print_intro():
	"""CLI entry point only — not used by the GUI."""
	print("\n************************************************************")
	print("*****                                                   *****")
	print("*****   THANK YOU FOR USING WHATSAPP BULK MESSENGER     *****")
	print("*****                                                   *****")
	print("************************************************************")

def get_message_template(log_fn=print) -> str:
	"""Read and return the message template from message.txt."""
	try:
		with open(os.path.join(_BASE_DIR, "message.txt"), "r", encoding="utf8") as f:
			template = f.read()
	except FileNotFoundError:
		raise FileNotFoundError(
			"message.txt not found. Please create it with your message template."
		)
	log_fn('\nMessage template:')
	log_fn(template)
	return template

def get_contacts(filepath=None):
	if filepath is None:
		# Search bundle dir first, then CWD; deduplicate when they are the same path.
		for fname in ['contacts.xlsx', 'contacts.csv']:
			for directory in dict.fromkeys([_BASE_DIR, os.getcwd()]):
				candidate = os.path.join(directory, fname)
				if os.path.exists(candidate):
					filepath = candidate
					break
			if filepath is not None:
				break
		if filepath is None:
			raise FileNotFoundError(
				"No contacts file found. Please create contacts.csv or contacts.xlsx "
				"with columns: Name, Phone Number, and any placeholder columns used in message.txt"
			)

	ext = os.path.splitext(filepath)[1].lower()
	if ext == '.xlsx':
		df = pd.read_excel(filepath)
	elif ext == '.csv':
		df = pd.read_csv(filepath)
	else:
		raise ValueError(f"Unsupported file format: {ext}. Use .csv or .xlsx")

	# Normalize column names — use rename() to avoid in-place mutation
	df = df.rename(columns={c: c.strip() for c in df.columns})
	orig_columns = list(df.columns)

	required = {'Name', 'Phone Number'}
	if not required.issubset(set(orig_columns)):
		raise ValueError(
			f"File must have at least 'Name' and 'Phone Number' columns. Found: {orig_columns}"
		)

	contacts = []
	for _, row in df.iterrows():
		# Build a fields dict with all columns (used for placeholder substitution)
		fields = {col: str(row[col]).strip() for col in orig_columns if col != 'Phone Number'}
		contacts.append({
			'name': str(row['Name']).strip(),
			'number': str(row['Phone Number']).strip(),
			'fields': fields,
		})
	return contacts

def get_driver():
	options = Options()
	options.add_experimental_option("excludeSwitches", ["enable-logging"])
	options.add_argument("--profile-directory=Default")
	options.add_argument("--user-data-dir=" + CHROME_USER_DATA_DIR)
	driver = webdriver.Chrome(service=Service(), options=options)
	return driver

def login_whatsapp(driver):
	"""CLI entry point only — not used by the GUI."""
	print('Once your browser opens up sign in to web whatsapp')
	driver.get('https://web.whatsapp.com')
	input("AFTER logging into Whatsapp Web is complete and your chats are visible, press ENTER...")

def main():
	print_intro()
	template = get_message_template()
	contacts = get_contacts()
	print(f"\nFound {len(contacts)} contacts in the file.")
	driver = get_driver()
	login_whatsapp(driver)
	send_messages(driver, contacts, template)
	driver.quit()
	print("\nAll done! Thanks for using WhatsApp Bulk Messenger.")

if __name__ == "__main__":
	main()
