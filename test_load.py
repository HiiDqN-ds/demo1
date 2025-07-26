import json
import os

DATA_PATH = './data'
USERS_FILE = os.path.join(DATA_PATH, 'users.json')
ITEMS_FILE = os.path.join(DATA_PATH, 'items.json')

def load_json(file_path):
    with open(file_path, 'r') as f:
        return json.load(f)

def test_load():
    users = load_json(USERS_FILE)
    items = load_json(ITEMS_FILE)
    print("Users loaded:")
    for u in users:
        print(f" - {u['username']} ({u['role']}) Activated: {u['activated']}")
    print("\nItems loaded:")
    for i in items:
        print(f" - {i['name']} | Barcode: {i['barcode']} | Price: {i['price']} | Quantity: {i['quantity']}")

if __name__ == "__main__":
    test_load()
