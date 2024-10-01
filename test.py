import json

file_path = "./test.json"

total = 0
with open(file_path, 'r') as file:
    importdata = json.load(file)

print(f"total messages = {len(importdata['messages'])}")

