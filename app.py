from flask import Flask, jsonify, send_from_directory, render_template_string, url_for, render_template, request
import json
import re
import os
import aiohttp
import asyncio
from dotenv import load_dotenv
import requests
import os
from datetime import datetime, timedelta

app = Flask(__name__, static_folder='public', template_folder='public')

UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
DOWNLOAD_FOLDER = os.path.join(app.static_folder, 'downloads')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/dm/<channel>')
def send_dm(channel):
    load_dotenv()
    SLACK_TOKEN = os.getenv('SLACK_TOKEN')
    headers = {
        'Authorization': f'Bearer {SLACK_TOKEN}',
        'Content-Type': 'application/json'
    }
    
    # Step 1: Open a direct message channel to yourself
    payload_open_conversation = {
        'users': 'U06QXUN2E9L'  # Replace YOUR_USER_ID with your actual Slack user ID
    }
    response = requests.post('https://slack.com/api/conversations.open', headers=headers, json=payload_open_conversation)
    
    if response.status_code == 200:
        data = response.json()
        if data['ok']:
            channel_id = data['channel']['id']
        else:
            return {"error": data.get('error', 'Unknown error')}, response.status_code
    else:
        return {"error": "Failed to open a direct message channel"}, response.status_code
    
    # Step 2: Send a message to the opened direct message channel
    payload_message = {
        'channel': channel_id,
        'text': f"https://2e12-31-160-179-82.ngrok-free.app/timeline/{channel}"
    }
    response = requests.post('https://slack.com/api/chat.postMessage', headers=headers, json=payload_message)
    
    if response.status_code == 200:
        data = response.json()
        if data['ok']:
            return {"message": "success"}, response.status_code
        else:
            return {"error": data.get('error', 'Unknown error')}, response.status_code
    else:
        return {"error": "Failed to send message"}, response.status_code

# @app.route('/download', methods=['POST'])
# def handle_slash_command():
#     data = request.form
#     print(request.form)
#     command = data.get('command')  # This will be '/download'
#     text = data.get('text')  # This will contain the parameters 'chat_id param2'
#     user_id = data.get('user_id')
#     channel_id = data.get('channel_id')

#     # Parse parameters
#     params = text.split()
    
#     if len(params) < 1:
#         return jsonify(response_type="ephemeral", text="Invalid parameters. Please provide a chat ID.")
    
#     chat_id = params[0]

#     # Generate the link
#     link = f"https://49de9e74a6b0e7854abed8476fe2ee32.loophole.site/timeline/{channel_id}"

#     # Return the link to the user
#     response_message = {
#         "response_type": "in_channel",
#         "text": f"Here is your timeline link: {link}"
#     }
#     return jsonify(response_message)

@app.route('/timeline/<channel>')
def get_history(channel):
    output_file_path = os.path.join(DOWNLOAD_FOLDER, f"{channel}.json")
    load_dotenv()
    SLACK_TOKEN = os.getenv('SLACK_TOKEN')
    
    headers = {
        'Authorization': f'Bearer {SLACK_TOKEN}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    oldest = request.args.get('oldest')
    latest = request.args.get('latest')

    params = {
        'channel': channel,
        'limit': 100,
    }
    
    if oldest:
        params['oldest'] = oldest
    if latest:
        params['latest'] = latest

    response = requests.get('https://slack.com/api/conversations.history', headers=headers, params=params)

    if response.status_code == 200:
        data = response.json()
        if data['ok']:
            with open(output_file_path, 'w') as file:
                json.dump(data, file, indent=4)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(conversion(channel))
            return download_file(channel)
        else:
            return {"error": data.get('error', 'Unknown error')}, response.status_code
    else:
        return {"error": "Failed to fetch data from Slack"}, response.status_code

            



@app.route('/get_timeline/<chat_id>', methods=['GET'])
def download_file(chat_id):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(conversion(chat_id))

        download_url = url_for('send_file', filename=f"{chat_id}.json")
        html_content = f"""
        <!DOCTYPE html>
        <html lang="en">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Download File</title>
        </head>
        <body>
            <script>
                function initiateDownload() {{
                    window.location.href = "{download_url}";
                    setTimeout(() => {{
                        window.location.href = "/";
                    }}, 1000);
                }}
                window.onload = initiateDownload;
            </script>
        </body>
        </html>
        """
        return render_template_string(html_content)
    except Exception as e:
        return jsonify({"error": str(e)}), 400

@app.route('/send_file/<filename>', methods=['GET'])
def send_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)


async def conversion(chat_id):
    palette = ["BAFFFF", "FFC4C4", "DABFFF", "BAFFC9", "FFFFBA", "FFDFBA", "FFB3BA"]

    output_file_path = os.path.join(UPLOAD_FOLDER, f"{chat_id}.json")
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
            importdata = json.load(file)
            
        array = importdata.get('messages', {})

        first_timestamp = float(array[0]['ts'])
        last_timestamp = float(array[-1]['ts'])
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
        for message in array:
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

    async def process_message(msgdate, message, date_str, hour_str, slack_token):
        daynum = int(msgdate.date().strftime('%u'))
        color = f"#{palette[daynum]}"
        pattern = re.compile(r'<(https?://[^>]+)>')
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

    file_path = os.path.join(DOWNLOAD_FOLDER, f"{chat_id}.json")
    formatted_data = await formatJSON(file_path, exportdata, output_file_path, slack_token)
    return formatted_data

if __name__ == '__main__':
    app.run(debug=False)