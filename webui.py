


# THIS IS ALL IN PROGRESS.
# THIS PYTHON FILE + WEB FOLDER IS ALL USELESS UNTIL FURTHER NOTICE.




from flask import Flask, render_template, jsonify, send_from_directory
import logging
import werkzeug.serving
import flask.cli
flask.cli.show_server_banner = lambda *args, **kwargs: None

logging.getLogger('werkzeug').setLevel(logging.ERROR)
werkzeug.serving.show_server_banner = lambda *args, **kwargs: None

app = Flask(__name__, template_folder="web", static_folder="web", static_url_path="")

messages = []

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/messages")
def get_messages():
    return jsonify(messages)

def add_message(message):
    messages.append(message)

def start():
    app.run(
        host="127.0.0.1",
        port=3000,
        debug=False,
        use_reloader=False
    )