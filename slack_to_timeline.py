import json
import re
from datetime import datetime, timedelta

palette = ["BAFFFF", "FFC4C4", "DABFFF", "BAFFC9", "FFFFBA", "FFDFBA", "FFB3BA"]

output_file_path = './output.json'
exportdata = {
        'meta': {
            "version": "1.4.0",
            "locale": "en-us"
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

def formatJSON(file_path, exportdata, output_file_path):
    with open(file_path, 'r') as file:
        importdata = json.load(file)

    first_timestamp = float(importdata[0]['ts'])
    last_timestamp = float(importdata[-1]['ts'])
    first_date = datetime.fromtimestamp(first_timestamp)
    last_date = datetime.fromtimestamp(last_timestamp)

    # Generate all hourly timestamps between the first and last message
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

    for message in importdata:
        msg = message.get('text', '')
        if not msg:
            msg = "[ ZONDER TEKST ]"
        timestamp = float(message.get('ts'))
        msgdate = datetime.fromtimestamp(timestamp)
        date_str = msgdate.date().isoformat()
        hour_str = msgdate.strftime('%H:00')
        user_name = get_name(message)
        exportdata = get_activities(msgdate, user_name, msg, message, date_str, hour_str)

    exportdata['days'].sort(key=lambda x: (x['date'], x['hour']))
    with open(output_file_path, 'w') as file:
        json.dump(exportdata, file, indent=4)

    return exportdata


def get_name(message):
    user_profile = message.get('user_profile', {})
    display_name = user_profile.get('display_name', 'User')
    name = user_profile.get('real_name', display_name)
    return name

def get_activities(msgdate, user_name, msg, message, date_str, hour_str):
    daynum = int(msgdate.date().strftime('%u'))
    color = f"#{ palette[daynum] }"
    pattern = re.compile(r'<(https?://[^>]+)>')
    activity = {
            'timestamp': msgdate.time().strftime('%H:%M:%S'),
            'title': '',
            'description': '',
            'fillColor': color,
            'strokeColor': '#C27B25',
            'imgUrl': ''
        }

    title = (f"[ { user_name } ] : ' { msg }")
    title = pattern.sub(r'\1', title)
    activity['title'] = (title[:50] + '..') if len(title) > 35 else title
    description = (f"[ { user_name } ] : ' { msg } ' ")
    description = pattern.sub(r'<a href="\1" target="_blank" style="text-decoration: underline; color: black; font-weight: bold;">Klik hier om link te openen.</a>', description)
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



file_path = './test.json'
formatted_data = formatJSON(file_path, exportdata, output_file_path)

# outputJSON(output)

# "timestamp": "13:55",
# "title": "Restarted sql cluster",
# "description": "Some additional information about the activity",
# "fillColor": "#FAD7AC",
# "strokeColor": "#C27B25"
