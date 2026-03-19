from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.by import By
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from time import sleep
from urllib.parse import quote
import os

DELAY = 10

# Chrome user data directory — change this if your Chrome profile is in a different location.
# Default: %LOCALAPPDATA%\Google\Chrome\User Data
# To use a custom isolated profile instead, set a path like:
#   os.path.join(os.environ['LOCALAPPDATA'], 'WABulker', 'User Data')
CHROME_USER_DATA_DIR = os.path.join(os.environ['LOCALAPPDATA'], 'WABulker', 'User Data')

def send_messages(driver, numbers, message):
	for idx, number in enumerate(numbers):
		number = number.strip()
		if number == "":
			continue
		print('\n{}/{} => Sending message to {}.'.format((idx+1), len(numbers), number))
		try:
			url = 'https://web.whatsapp.com/send?phone=' + number + '&text=' + message
			sent = False
			for i in range(3):
				if not sent:
					driver.get(url)
					try:
						click_btn = WebDriverWait(driver, DELAY).until(EC.element_to_be_clickable((By.XPATH, "//button[@aria-label='Send']")))
					except Exception as e:
						print(f"\nFailed to send message to: {number}, retry ({i+1}/3)")
						print("Make sure your phone and computer is connected to the internet.")
						print("If there is an alert, please dismiss it.")
					else:
						sleep(1)
						click_btn.click()
						sent=True
						sleep(3)
						print(f'Message sent to: {number}')
						break
		except Exception as e:
			print(f'Failed to send message to {number}: {e}')

def print_intro():
	print("\n**********************************************************")
	print("*****                                                 ******")
	print("*****  THANK YOU FOR USING WHATSAPP BULK MESSENGER    ******")
	print("*****      This tool was built by Aishik Das          ******")
	print("*****           www.github.com/theSpartan117          ******")
	print("*****                                                 ******")
	print("************************************************************")

def get_message() -> str:
	with open("message.txt", "r", encoding="utf8") as f:
		message = f.read()
	print('\nThis is your message-')
	print(message)
	message = quote(message)
	return message

def get_numbers() -> list:
	numbers = []
	with open("numbers.txt", "r", encoding="utf8") as f:
		for line in f.read().splitlines():
			number = line.strip()
			if number == "":
				continue
			if len(number) == 10 and number.isdigit():
				number = "91" + number
			numbers.append(number)
	return numbers

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
	message = get_message()
	numbers = get_numbers()
	print(f"\nFound {len(numbers)} numbers in the file.")
	driver = get_driver()
	login_whatsapp(driver)
	send_messages(driver, numbers, message)
	driver.quit()
	print("\nAll done! Thanks for using WhatsApp Bulk Messenger.")

if __name__ == "__main__":
	main()