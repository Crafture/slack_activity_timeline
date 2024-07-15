import json
import re
import os
import aiohttp
import asyncio
from dotenv import load_dotenv
from datetime import datetime, timedelta

palette = ["BAFFFF", "FFC4C4", "DABFFF", "BAFFC9", "FFFFBA", "FFDFBA", "FFB3BA"]

output_file_path = './output.json'
exportdata = {
    'meta': {
        "version": "1.4.0",
        "locale": "en-nl"
    },
    'style': {
        "textColor": "#000000",
        "timelineStrokeColor": "#24ff6d",
        "strokeColor": "#353C4B",
        "backgroundColor": "#F7F6EB",
        'fillColor': '#F2E7DC'
    },
    'days': []
}

async def formatJSON(file_path, exportdata, output_file_path, slack_token):
    with open(file_path, 'r') as file:
        importdata = json.load(file)['messages']

    first_timestamp = float(importdata[0]['ts'])
    last_timestamp = float(importdata[-1]['ts'])
    first_date = datetime.fromtimestamp(first_timestamp)
    last_date = datetime.fromtimestamp(last_timestamp)

    current_date = first_date.replace(minute=0, second=0, microsecond=0)
    end_date = last_date.replace(minute=0, second=0, microsecond=0)

    while current_date <= end_date:
        date_str = current_date.date().isoformat()
        hour_str = current_date.strftime('%H:00')
        exportdata['days'].append({
            'date': date_str,
            'hour': hour_str,
            'activities': []
        })
        current_date += timedelta(hours=1)

    tasks = []
    for message in importdata:
        msg = message.get('text', '')
        if msg == "":
            msg = "[ ZONDER TEKST ]"
        timestamp = float(message.get('ts'))
        msgdate = datetime.fromtimestamp(timestamp)
        date_str = msgdate.date().isoformat()
        hour_str = msgdate.strftime('%H:00')
        tasks.append(asyncio.create_task(process_message(msgdate, message, date_str, hour_str, slack_token)))

    results = await asyncio.gather(*tasks)
    for result in results:
        if result:
            exportdata = result

    exportdata['days'].sort(key=lambda x: (x['date'], x['hour']))
    with open(output_file_path, 'w') as file:
        json.dump(exportdata, file, indent=4)

    return exportdata

async def get_user_info(slack_token, user_id):
    url = "https://slack.com/api/users.info"
    headers = {
        "Authorization": f"Bearer {slack_token}",
        "Content-Type": "application/json"
    }
    params = {
        "user": user_id
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, params=params) as response:
            data = await response.json()

            if data.get("ok"):
                return data["user"]["profile"]["real_name"]
            else:
                raise Exception(f"Error fetching user info: {data.get('error')}")

async def replace_user_mentions(text, slack_token):
    pattern = re.compile(r'<@([A-Z0-9]+)>')
    matches = pattern.finditer(text)

    replacements = {}
    for match in matches:
        user_id = match.group(1)
        user_name = await get_user_info(slack_token, user_id)
        replacements[match.group(0)] = user_name

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text

def get_name(message):
    user_profile = message.get('user_profile', {})
    display_name = user_profile.get('display_name', '')
    name = user_profile.get('real_name', display_name)
    if not name:
        user = message.get('user', '')
        if user:
            return f"<@{user}>"
        files = message.get('files', [])
        if isinstance(files, list):
            for file in files:
                if 'user' in file:
                    user_id = file['user']
                    return f"<@{user_id}>"
    return name

def extract_text_from_blocks(blocks):
    text = ""
    for block in blocks:
        if block.get('type') == 'rich_text':
            elements = block.get('elements', [])
            for element in elements:
                if element.get('type') == 'rich_text_section':
                    for sub_element in element.get('elements', []):
                        if sub_element.get('type') == 'text':
                            text += sub_element.get('text', '')
                        elif sub_element.get('type') == 'link':
                            text += sub_element.get('url', '')
    return text

async def process_message(msgdate, message, date_str, hour_str, slack_token):
    daynum = int(msgdate.date().strftime('%u'))
    color = f"#{palette[daynum]}"
    pattern = re.compile(r'<(https?://[^>]+)>')
    
    if 'blocks' in message:
        msg = extract_text_from_blocks(message['blocks'])
    else:
        msg = message.get('text', '')
        
    user_name = get_name(message)
    
    activity = {
        'timestamp': msgdate.time().strftime('%H:%M:%S'),
        'title': '',
        'description': '',
        'fillColor': color,
        'strokeColor': '#C27B25',
        'imgUrl': ''
    }

    title = (f"[ {user_name} ] : ' {msg} '")
    title = pattern.sub(r'\1', title)
    title = await replace_user_mentions(title, slack_token)
    activity['title'] = (title[:70] + '..') if len(title) > 70 else title
    description = (f"[ {user_name} ] : ' {msg} ' ")
    description = pattern.sub(r'<a href="\1" target="_blank" style="text-decoration: underline; color: black; font-weight: bold;">Klik hier om link te openen.</a>', description)
    description = await replace_user_mentions(description, slack_token)
    activity['description'] = description
    attachments = message.get('attachments', {})
    files = message.get('files', {})
    if attachments:
        for attachment in attachments:
            if "a href" in description:
                activity['strokeColor'] = '#FF0000'
            if 'image_url' in attachment:
                activity['imgUrl'] = attachment.get('image_url')
                activity['fillColor'] = '#57ebff'
                break

    elif files:
        for file in files:
            if 'url_private' in file:
                activity['strokeColor'] = '#000000'
                activity['imgUrl'] = file.get('url_private')
                activity['fillColor'] = '#57ebff'
                break

    date_found = False
    for day in exportdata['days']:
        if day['date'] == date_str and day.get('hour') == hour_str:
            day['activities'].append(activity)
            date_found = True
            break
    if not date_found:
        msgobject = {
            'date': date_str,
            'hour': hour_str,
            'activities': [activity]
        }
        exportdata['days'].append(msgobject)
    return exportdata

load_dotenv()
slack_token = os.getenv('SLACK_TOKEN')

file_path = './test.json'
formatted_data = asyncio.run(formatJSON(file_path, exportdata, output_file_path, slack_token))
