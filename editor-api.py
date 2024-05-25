
from flask import request
from flask import render_template_string
from flask import render_template
from flask import Flask
from flask import redirect
from flask import url_for
from flask_cors import CORS
from dbutils import Connection

app = Flask(__name__)
app.config['Access-Control-Allow-Origin'] = '*'
CORS(app)
connection = Connection("data/main.db")

@app.route('/', methods=['GET'])
def index():
    return render_template_string("""
    <html>
        <head>
            <title>Editor API</title>
        </head>
        <body>
            <h1>Editor API</h1>
            <p>API for the editor</p>
        </body>
    </html>""")

def main():
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=True)

if __name__ == "__main__":
    main()
