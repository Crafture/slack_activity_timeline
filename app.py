from flask import Flask, jsonify, send_from_directory, render_template_string, url_for, render_template, request
import json
import re
import os
import aiohttp
import asyncio
from dotenv import load_dotenv
import requests
import os
import jwt
from datetime import datetime, timedelta, timezone

app = Flask(__name__, static_folder='public', template_folder='public')

load_dotenv()
UPLOAD_FOLDER = os.path.join(app.static_folder, 'uploads')
DOWNLOAD_FOLDER = os.path.join(app.static_folder, 'downloads')
SECRET_KEY = os.getenv('SECRET_KEY')
SLACK_TOKEN = os.getenv('SLACK_TOKEN')
VERIFICATION_TOKEN = os.getenv('VERIFICATION_TOKEN')
AUTHORIZED_USERS = os.getenv('AUTHORIZED_USERS').split(',')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/test')
def test():
    oldest, latest = "test"
    return jsonify({"message": oldest}), 200

def convert_to_timestamp(date_string):
    date_format = "%d-%m-%Y"
    dt_object = datetime.strptime(date_string, date_format)
    timestamp = dt_object.timestamp()
    return timestamp

@app.route('/dm', methods=['POST'])
def send_dm():
    date_pattern = r'^\d{2}-\d{2}-\d{4}$'
    if not SLACK_TOKEN or not VERIFICATION_TOKEN:
        return jsonify({"error": "SLACK_TOKEN or VERIFICATION_TOKEN is not set in the environment"}), 500

    token = request.form.get('token')
    user_id = request.form.get('user_id')
    text = request.form.get('text')
    if text:
        if text == "help":
            return "For now, there is no help available. Just the /timeline command. When there are new functionalities added, I will update this"
        dates = text.split(' ')
        if len(dates) == 2:
            if re.match(date_pattern, dates[0]):
                oldest = convert_to_timestamp(dates[0])
            if re.match(date_pattern, dates[1]):
                latest = convert_to_timestamp(dates[1])
            if not oldest and latest:
                return "Usage example: /timeline 21-01-2024 22-01-2024"

    if token != VERIFICATION_TOKEN:
        return jsonify({"error": "Invalid request token"}), 403

    if user_id not in AUTHORIZED_USERS:
        return jsonify({"error": "Unauthorized user"}), 403

    channel_id = request.form.get('channel_id')
    if not channel_id:
        return jsonify({"error": "channel_id is required"}), 400

    verification = generate_token(user_id)
    if not oldest and latest:
        return f"Click here to see Timeline: https://slack-activity-timeline.onrender.com/timeline/{channel_id}?verification={verification}"
    else:
        return f"Click here to see Timeline: https://slack-activity-timeline.onrender.com/timeline/{channel_id}?verification={verification}&oldest={oldest}&latest={latest}"

@app.route('/timeline/<channel>')
def get_history(channel):
    output_file_path = os.path.join(DOWNLOAD_FOLDER, f"{channel}.json")
    
    headers = {
        'Authorization': f'Bearer {SLACK_TOKEN}',
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    oldest = request.args.get('oldest')
    latest = request.args.get('latest')
    verification = request.args.get('verification')
    user_id = verify_token(verification)
    if user_id not in AUTHORIZED_USERS:
        return jsonify({"error": "unauthorized"}), 403

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
            print("test", flush=True)
            return download_file(channel, SECRET_KEY)
        else:
            return {"error": data.get('error', 'Unknown error')}, response.status_code
    else:
        return {"error": "Failed to fetch data from Slack"}, response.status_code

def generate_token(user_id):
    expiration = datetime.now(timezone.utc) + timedelta(minutes=10)
    token = jwt.encode({
        'user_id': user_id,
        'exp': expiration
    }, SECRET_KEY, algorithm='HS256')
    return token

def verify_token(token):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=['HS256'])
        return payload['user_id']
    except jwt.ExpiredSignatureError:
        return 'Token has expired'
    except jwt.InvalidTokenError:
        return 'Invalid token'

def download_file(chat_id, secret_key):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(conversion(chat_id))

        download_url = url_for('send_file_route', filename=f"{chat_id}.json")
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
                    fetch("{download_url}", {{
                        headers: {{
                            'Authorization': 'Bearer {SECRET_KEY}'
                        }}
                    }}).then(response => {{
                        if (response.ok) {{
                            return response.blob();
                        }} else {{
                            throw new Error('Unauthorized');
                        }}
                    }}).then(blob => {{
                        const url = window.URL.createObjectURL(blob);
                        const a = document.createElement('a');
                        a.style.display = 'none';
                        a.href = url;
                        a.download = "{chat_id}.json";
                        document.body.appendChild(a);
                        a.click();
                        window.URL.revokeObjectURL(url);
                        setTimeout(() => {{
                            window.location.href = "/";
                        }}, 1000);
                    }}).catch(error => {{
                        console.error('Error:', error);
                        window.location.href = "/";
                    }});
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
def send_file_route(filename):
    secret_key = request.headers.get('Authorization')
    if secret_key == f"Bearer {SECRET_KEY}":
        return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
    else:
        return jsonify({"error": "Unauthorized"}), 403

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

        known_users = {}
        if os.path.exists("known_users.json"):
            try:
                with open("known_users.json", "r") as file:
                    known_users = json.load(file)
            except (json.JSONDecodeError, FileNotFoundError):
                known_users = {}

        replacements = {}
        for match in matches:
            user_id = match.group(1)
            if user_id in known_users:
                user_name = known_users[user_id]
            else:
                user_name = await get_user_info(slack_token, user_id)
                known_users[user_id] = user_name
            replacements[match.group(0)] = user_name

        with open("known_users.json", "w") as file:
            json.dump(known_users, file)

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

    file_path = os.path.join(DOWNLOAD_FOLDER, f"{chat_id}.json")
    formatted_data = await formatJSON(file_path, exportdata, output_file_path, SLACK_TOKEN)
    return formatted_data

if __name__ == '__main__':
    app.run()