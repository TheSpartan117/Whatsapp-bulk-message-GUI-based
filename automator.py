from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.common.exceptions import NoAlertPresentException
from time import sleep
from urllib.parse import quote
import os
import platform
import re
import sys
import pandas as pd

DELAY = 10
SEND_DELAY = 2
# Brief pause so the button registers the click correctly
PRE_CLICK_DELAY = 1
# Wait for WhatsApp Web to process the send before navigating away
POST_SEND_DELAY = 3
# Maximum allowed file size for contacts files (10 MB)
MAX_FILE_SIZE = 10 * 1024 * 1024

# Bundled data-file directory: sys._MEIPASS when frozen, script dir otherwise.
_BASE_DIR = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))

# Strings that appear in page source / alert text when a number is not on WhatsApp.
# Checked case-insensitively against the full page source AND native alert text.
# IMPORTANT: keep these specific — they are matched against the entire DOM, which
# includes loaded chat history.  Broad substrings (e.g. "use whatsapp") risk false
# positives when a chat message happens to contain the phrase.
_NOT_ON_WHATSAPP_MARKERS = (
	"phone number shared via url is invalid",  # WhatsApp's own error string
	"isn't on whatsapp",                        # shown in some locales
)

# Chrome user data directory — isolated WABulker profile, per OS.
_sys = platform.system()
if _sys == 'Windows':
    CHROME_USER_DATA_DIR = os.path.join(os.environ.get('LOCALAPPDATA', os.path.expanduser('~')), 'WABulker', 'User Data')
elif _sys == 'Darwin':
    CHROME_USER_DATA_DIR = os.path.join(os.path.expanduser('~'), 'Library', 'Application Support', 'WABulker')
else:  # Linux
    CHROME_USER_DATA_DIR = os.path.join(os.path.expanduser('~'), '.config', 'WABulker')

def _is_not_on_whatsapp(driver) -> bool:
	"""Return True if the page signals that the number is not on WhatsApp.

	Checks two sources (case-insensitive):
	  1. Native browser alert text (dismiss it after reading).
	  2. The rendered page source for WhatsApp's own error strings.

	Returns False on any unexpected exception so the caller falls back to
	treating the failure as transient (retryable).
	"""
	# 1. Native alert (rare but possible in some Chrome/WhatsApp combinations).
	#    Only dismiss if the text actually matches a marker — leave unrelated
	#    alerts (e.g. "reload page?", security dialogs) intact for the user.
	#    Catch only NoAlertPresentException (expected case: no alert shown);
	#    any other exception indicates a genuine driver problem and falls through.
	try:
		alert = driver.switch_to.alert
		text = alert.text.lower()
		if any(marker in text for marker in _NOT_ON_WHATSAPP_MARKERS):
			alert.dismiss()
			return True
	except NoAlertPresentException:
		pass  # Expected: no alert — continue to page-source check

	# 2. Page source (WhatsApp renders a custom HTML error popup).
	#    Exceptions here usually mean the driver is in a bad state (crashed
	#    browser, lost session).  Return False so the caller logs the failure
	#    via _attempt_send's normal error path rather than silently swallowing it.
	try:
		source = driver.page_source.lower()
		return any(marker in source for marker in _NOT_ON_WHATSAPP_MARKERS)
	except Exception:
		return False  # treat as "could not determine" → transient

	return False  # noqa: unreachable — explicit for readability


def _attempt_send(driver, url, name, number, log_fn, delay, send_delay):
	"""Try to send one message.

	Returns:
	    True  — message sent successfully.
	    None  — permanent failure (number not on WhatsApp); do NOT retry.
	    False — transient failure (timeout / network); caller may retry.
	"""
	driver.get(url)
	try:
		click_btn = WebDriverWait(driver, delay).until(
			EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']")))
	except Exception as e:
		if _is_not_on_whatsapp(driver):
			return None  # permanent — caller must not retry
		# Use only the exception type — raw Selenium messages can expose
		# internal browser state (CDP session IDs, WebDriver paths, etc.)
		err_type = type(e).__name__
		log_fn(f"\nCould not send to {name} ({number}): {err_type}")
		log_fn("Make sure your phone and computer is connected to the internet.")
		log_fn("If there is an alert, please dismiss it.")
		return False  # transient — caller may retry
	sleep(PRE_CLICK_DELAY)
	click_btn.click()
	sleep(send_delay)
	sleep(POST_SEND_DELAY)
	log_fn(f'Message sent to: {name} ({number})')
	return True


def send_messages(driver, contacts, template, log_fn=print, stop_event=None, progress_fn=None, delay=None, send_delay=None, country_code="91"):
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
		# Prepend country code for bare 10-digit numbers
		if len(number) == 10 and country_code:
			number = country_code + number
		# Validate final length is within E.164 range (10–15 digits)
		if not (10 <= len(number) <= 15):
			log_fn(f"  Skipping {name}: number '{number}' has invalid length ({len(number)} digits).")
			continue

		# Single-pass substitution prevents second-order injection where a
		# field value containing '{OtherKey}' would be re-expanded in a loop.
		fields = contact['fields']
		personalized_message = re.sub(
			r'\{([^{}]+)\}',
			lambda m: fields.get(m.group(1), m.group(0)),
			template
		)
		remaining = re.findall(r'\{[^{}]+\}', personalized_message)
		if remaining:
			log_fn(f"  Warning: unresolved placeholders {remaining} — check column names.")
		encoded_message = quote(personalized_message)

		log_fn(f'\n{idx+1}/{len(contacts)} => Sending message to {name} ({number}).')
		url = 'https://web.whatsapp.com/send?phone=' + quote(number, safe='') + '&text=' + encoded_message
		for i in range(3):
			if stop_event is not None and stop_event.is_set():
				log_fn("Sending stopped by user.")
				return
			result = _attempt_send(driver, url, name, number, log_fn, _delay, _send_delay)
			if result is True:
				if progress_fn is not None:
					progress_fn(idx + 1, len(contacts))
				break
			if result is None:  # permanent — number not on WhatsApp
				log_fn(f"  Skipping {name} ({number}): number not registered on WhatsApp.")
				if progress_fn is not None:  # advance progress bar even on skip
					progress_fn(idx + 1, len(contacts))
				break
			if i < 2:
				log_fn(f"  Retry {i+1}/3 for {name}...")
		else:
			log_fn(f"  Failed to send to {name} ({number}) after 3 attempts — skipped.")

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
	if ext not in ('.csv', '.xlsx'):
		raise ValueError(f"Unsupported file format: {ext}. Use .csv or .xlsx")

	file_size = os.path.getsize(filepath)
	if file_size > MAX_FILE_SIZE:
		raise ValueError(
			f"File is too large ({file_size // 1024 // 1024} MB). "
			f"Maximum allowed size is {MAX_FILE_SIZE // 1024 // 1024} MB."
		)

	if ext == '.xlsx':
		df = pd.read_excel(filepath)
	else:
		df = pd.read_csv(filepath)

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
