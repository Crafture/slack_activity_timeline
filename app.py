from flask import Flask, jsonify, send_from_directory, render_template_string, url_for, render_template, request, redirect
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

@app.route('/handle_command', methods=['POST'])
def return_datepicker():
    token = request.form.get('token')
    if token != VERIFICATION_TOKEN:
        abort(403)

    text = request.form.get('text')
    user_id = request.form.get('user_id')
    channel_id = request.form.get('channel_id')
    date_pattern = r'^\d{2}-\d{2}-\d{4}$'
    
    if text:
        if text == "help":
            return "/timeline -> pick date"
        if text == "week":
            dates = []
            start_date = datetime.today() + timedelta(days=1)
            dates.append((start_date - timedelta(weeks=1)).strftime("%d-%m-%Y"))
            dates.append(start_date.strftime("%d-%m-%Y"))
        else:
            dates = text.split(' ')
        if len(dates) == 2 and re.match(date_pattern, dates[0]) and re.match(date_pattern, dates[1]):
            oldest = convert_to_timestamp(dates[0])
            latest = convert_to_timestamp(dates[1])
            if oldest >= latest:
                return jsonify({"text": "Last date has to be later than the oldest"})
            verification = generate_token(user_id)
            timeline_url = f"https://slack-activity-timeline.crafture.com/timeline/{channel_id}?verification={verification}&oldest={oldest}&latest={latest}"
            return jsonify({"text": f"Click here to see Timeline: {timeline_url}"})
        else:
            return jsonify({"text": "Usage example: /timeline 21-01-2024 22-01-2024"})
    initial_date = datetime.today() - timedelta(weeks=4)
    formatted_initial_date = initial_date.strftime("%Y-%m-%d")
    return_form = {
        "blocks": [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "To get timeline, *select a date*."
                }
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "datepicker",
                        "initial_date": formatted_initial_date,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "Select a date",
                            "emoji": True
                        },
                        "action_id": "datepicker-action-2"
                    }
                ]
            }
        ]
    }
    return jsonify(return_form)

@app.route('/interactivity', methods=['POST'])
def interactivity():
    payload = request.form['payload']
    data = json.loads(payload)

    token = data.get('token')
    if token != VERIFICATION_TOKEN:
        return send_from_directory(app.static_folder, 'invalid_page.html')
    
    # Extract the selected date from the payload
    selected_date = data['actions'][0]['selected_date']
    
    # Extract the response_url from the payload
    response_url = data['response_url']
    
    # Create the response message
    start_date = datetime.strptime(selected_date, '%Y-%m-%d')
    end_date = start_date + timedelta(days=1) - timedelta(seconds=1)
    verification = generate_token(data['user']['id'])
    channel_id = data['channel']['id']
    timeline_url = f"https://slack-activity-timeline.crafture.com/timeline/{channel_id}?verification={verification}&oldest={start_date.timestamp()}&latest={end_date.timestamp()}"

    response_message = {
        "text": f"Click here to see Timeline: {timeline_url}"
    }
    
    # Send the response message to the response_url
    requests.post(response_url, json=response_message)
    
    return jsonify({"text": "Thank you for selecting a date."})


def convert_to_timestamp(date_string):
    date_format = "%d-%m-%Y"
    dt_object = datetime.strptime(date_string, date_format)
    timestamp = dt_object.timestamp()
    return timestamp

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
        return send_from_directory(app.static_folder, 'invalid_page.html')

    params = {
        'channel': channel,
        'limit': 100,
    }

    if oldest:
        params['oldest'] = oldest
    if latest:
        params['latest'] = latest

    response = requests.get('https://slack.com/api/conversations.history', headers=headers, params=params)
    # return response.json()
    if response.status_code == 200:
        data = response.json()
        if data['ok']:
            if data['messages'] == []:
                return send_from_directory(app.static_folder, 'no_messages_found.html')
            with open(output_file_path, 'w') as file:
                json.dump(data, file, indent=4)
            conversion(channel)
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
        conversion(chat_id)

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
        return send_from_directory(app.static_folder, 'unauthorized.html')

@app.route('/permalink/<channel_id>/<message_ts>')
def get_message_permalink(channel_id, message_ts):
    url = "https://slack.com/api/chat.getPermalink"
    headers = {
        "Authorization": f"Bearer {SLACK_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {
        "channel": channel_id,
        "message_ts": message_ts
    }

    response = requests.get(url, headers=headers, params=data)

    if response.ok:
        response_data = response.json()
        if response_data.get("ok"):
            permalink = response_data["permalink"]
            return redirect(permalink)
        else:
            return send_from_directory(app.static_folder, 'error_fetching_permalink.html'), 500
    else:
        return send_from_directory(app.static_folder, 'error_fetching_permalink.html'), 500

def conversion(chat_id):
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

    def formatJSON(file_path, exportdata, output_file_path, slack_token, channel_id):
        with open(file_path, 'r') as file:
            importdata = json.load(file)
            
        array = importdata.get('messages', [])
        if array:
            first_timestamp = float(array[0]['ts'])
            last_timestamp = float(array[-1]['ts'])
            first_date = datetime.fromtimestamp(first_timestamp) + timedelta(hours=2)
            last_date = datetime.fromtimestamp(last_timestamp) + timedelta(hours=2)
        else:
            return {"message": "No available messages"}, 400

        if first_date - last_date < timedelta(hours=24):
            while last_date <= first_date:
                date_str = first_date.date().isoformat()
                for hour in range(24):
                    hour_str = f"{hour:02d}:00"
                    exportdata['days'].append({
                        'date': date_str,
                        'hour': hour_str,
                        'activities': []
                    })
                last_date += timedelta(days=1)

        for message in array:
            timestamp = float(message.get('ts'))
            msgdate = datetime.fromtimestamp(timestamp)
            date_str = msgdate.date().isoformat()
            hour_str = msgdate.strftime('%H:00')

            result = process_message(msgdate, message, date_str, hour_str, slack_token, channel_id)
            if result:
                exportdata = result

        exportdata['days'].sort(key=lambda x: (x['date'], x['hour']))
        with open(output_file_path, 'w') as file:
            json.dump(exportdata, file, indent=4)

        return exportdata



    def get_user_info(slack_token, user_id):
        url = "https://slack.com/api/users.info"
        headers = {
            "Authorization": f"Bearer {slack_token}",
            "Content-Type": "application/json"
        }
        params = {
            "user": user_id
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get("ok"):
                return response_data["user"]["profile"]["real_name"]
            else:
                raise Exception(f"Error fetching user info: {response_data.get('error')}")


    def replace_user_mentions(text, slack_token):
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
                user_name = get_user_info(slack_token, user_id)
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

    def process_message(msgdate, message, date_str, hour_str, slack_token, channel_id):
        print("process_message")
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
        title = replace_user_mentions(title, slack_token)
        activity['title'] = (title[:70] + '..') if len(title) > 70 else title
        description = (f"[ {user_name} ] : ' {msg} ' ")
        description = pattern.sub(r'<a href="\1" target="_blank" style="text-decoration: underline; color: black; font-weight: bold;">Klik hier om link te openen.</a>', description)
        description = replace_user_mentions(description, slack_token)
        ts = message.get('ts', None)
        if ts:
            msg_link = f'/permalink/{channel_id}/{ts}'
            description += f'<br><br><a href="{msg_link}" target="_blank" style="text-decoration: underline; color: green; font-weight: bold;">Open in slack</a>'
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

    file_path = os.path.join(DOWNLOAD_FOLDER, f"{chat_id}.json")
    formatted_data = formatJSON(file_path, exportdata, output_file_path, SLACK_TOKEN, chat_id)
    return formatted_data

if __name__ == '__main__':
    app.run(debug=False, host='0.0.0.0', port=5000)



