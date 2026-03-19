from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from time import sleep
from urllib.parse import quote
import os
import pandas as pd

DELAY = 10
SEND_DELAY = 2

# Chrome user data directory — change this if your Chrome profile is in a different location.
# Default: %LOCALAPPDATA%\Google\Chrome\User Data
# To use a custom isolated profile instead, set a path like:
#   os.path.join(os.environ['LOCALAPPDATA'], 'WABulker', 'User Data')
CHROME_USER_DATA_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'WABulker', 'User Data')

def send_messages(driver, contacts, template):
	for idx, contact in enumerate(contacts):
		name = contact['name']
		number = contact['number']

		number = str(number).strip()
		if number == "":
			continue
		if len(number) == 10 and number.isdigit():
			number = "91" + number

		personalized_message = template
		for key, value in contact['fields'].items():
			personalized_message = personalized_message.replace('{' + key + '}', value)
		encoded_message = quote(personalized_message)

		print(f'\n{idx+1}/{len(contacts)} => Sending message to {name} ({number}).')
		try:
			url = 'https://web.whatsapp.com/send?phone=' + number + '&text=' + encoded_message
			sent = False
			for i in range(3):
				if not sent:
					driver.get(url)
					try:
						click_btn = WebDriverWait(driver, DELAY).until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']")))
					except Exception as e:
						print(f"\nFailed to send message to: {name} ({number}), retry ({i+1}/3)")
						print("Make sure your phone and computer is connected to the internet.")
						print("If there is an alert, please dismiss it.")
					else:
						sleep(1)
						click_btn.click()
						sleep(SEND_DELAY)
						sent = True
						sleep(3)
						print(f'Message sent to: {name} ({number})')
						break
		except Exception as e:
			print(f'Failed to send message to {name} ({number}): {e}')

def print_intro():
	print("\n************************************************************")
	print("*****                                                   *****")
	print("*****   THANK YOU FOR USING WHATSAPP BULK MESSENGER     *****")
	print("*****                                                   *****")
	print("************************************************************")

def get_message_template() -> str:
	with open("message.txt", "r", encoding="utf8") as f:
		template = f.read()
	print('\nMessage template:')
	print(template)
	return template

def get_contacts(filepath=None):
	if filepath is None:
		for fname in ['contacts.xlsx', 'contacts.csv']:
			if os.path.exists(fname):
				filepath = fname
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

	# Normalize column names for internal use, but keep originals for placeholder matching
	orig_columns = [c.strip() for c in df.columns]
	df.columns = orig_columns

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
