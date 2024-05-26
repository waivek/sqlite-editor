
from flask import request
from flask import render_template_string
from flask import render_template
from flask import Flask
from flask import redirect
from flask import url_for
from flask_cors import CORS
from dbutils import Connection
from waivek import read, write, rel2abs
import os
from datetime import datetime, timezone, timedelta
import timeago

app = Flask(__name__)
app.config['Access-Control-Allow-Origin'] = '*'
CORS(app)
connection = Connection("data/main.db")

@app.route('/api/tables/<table_name>/delete', methods=['POST'])
def delete_table(table_name):
    connection.execute(f"DROP TABLE [{table_name}];")
    state = create_table_state()
    if state['table_name'] == table_name:
        state['table_name'] = ''
        write(state, rel2abs('data/state.json'))
    return redirect(url_for('index'))

def create_table_state():
    state_path = rel2abs('data/state.json')
    if not os.path.exists(state_path):
        write({'table_name': ''}, state_path)
    state = read(state_path)
    return state

@app.route('/api/tables/<table_name>/select', methods=['POST'])
def select_table(table_name):
    state = create_table_state()
    state['table_name'] = table_name
    write(state, rel2abs('data/state.json'))
    return redirect(url_for('index'))

@app.route('/api/tables', methods=['POST'])
def create_table():
    name = request.form.get('name')
    if not name:
        return redirect(url_for('index'))
    connection.execute(f"CREATE TABLE [{name}] (id INTEGER PRIMARY KEY AUTOINCREMENT);")
    return redirect(url_for('index'))

@app.route('/api/tables/<table_name>/columns', methods=['POST'])
def add_column(table_name):
    name = request.form.get('name')
    column_type = request.form.get('type')
    if not name or not column_type:
        return redirect(url_for('index'))
    connection.execute(f"ALTER TABLE [{table_name}] ADD COLUMN [{name}] {column_type};")
    return redirect(url_for('index'))

@app.route('/api/tables/<table_name>/rows', methods=['POST'])
def add_row(table_name):
    # form_json = request.form.to_dict()
    # return form_json
    state = create_table_state()
    columns = []
    cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
    for column in cursor.fetchall():
        columns.append(column['name'])
    values = []
    for column in columns:
        values.append(request.form.get(column))
    connection.execute(f"INSERT INTO [{table_name}] ({', '.join(columns)}) VALUES ({', '.join(['?' for _ in columns])});", values)
    connection.commit()
    return redirect(url_for('index'))

@app.route('/api/tables/<table_name>/columns/<column_name>/rows/<row_id>', methods=['POST'])
def update_cell(table_name, column_name, row_id):
    value = request.form.get('value')
    connection.execute(f"UPDATE [{table_name}] SET [{column_name}] = ? WHERE id = ?;", [value, row_id])
    connection.commit()
    return redirect(url_for('index'))

def get_textarea_html(value):
    return r'''
        <textarea name="value" value="{0}">{0}</textarea>
    '''.format(value)

def cell_to_class(value):
    if value is None:
        return 'null'
    value = str(value)
    if value.endswith('.jpg') or value.endswith('.png') or value.endswith('.jpeg'):
        return 'image'
    if value.startswith('http://') or value.startswith('https://'):
        return 'link'
    if is_date_epoch(value) or is_date_iso(value):
        return 'date'
    if len(value) > 100:
        return 'text-long'
    return 'text'

def cell_to_input(value):
    if value is None:
        return r'<input type="text" name="value" value="">'
    value = str(value)
    default = r'<input type="text" name="value" value="{0}">'.format(value)
    textarea_html = get_textarea_html(value)
    if value.endswith('.jpg') or value.endswith('.png') or value.endswith('.jpeg'):
        image_html = r'<img src="{0}" style="max-height: 100px; max-width: 100px;" alt="{0}" title="{0}">'.format(value)
        clickable_image_html = r'<a href="{0}" >{1}</a>'.format(value, image_html)
        return r"""
        <div class="tall">
            <div>{0}</div>
            {1}
        </div>
        """.format(clickable_image_html, textarea_html)
    if value.startswith('http://') or value.startswith('https://'):
        # return r'<a href="{0}">{0}</a>'.format(value)
        return r"""
        <div class="tall">
            <div><a href="{0}">{0}</a></div>
            <div>{1}</div>
        </div>
        """.format(value, textarea_html)
    if is_date_epoch(value) or is_date_iso(value):
        if is_date_epoch(value):
            date = datetime.fromtimestamp(int(value), tz=timezone.utc)
        else:
            date = datetime.fromisoformat(value)
        # make naive into utc
        if date.tzinfo is None:
            date = date.replace(tzinfo=timezone.utc)
        html_friendly_date_string = date.strftime('%Y-%m-%dT%H:%M')
        timeago_string = timeago.format(date, datetime.now(timezone.utc))
        human_readable_date_string = date.strftime('%c %Z')
        epoch_string = str(int(date.timestamp()))
        return r"""
        <div style="text-align: left;">
            <div style="color: gray;">{3}</div>
            <div>{2}</div>
            <div>{1}</div>
            <div><input type="datetime-local" name="value" value="{0}"></div>
        </div>
        """.format(html_friendly_date_string, timeago_string, human_readable_date_string, value)
        return r'<div>{0}</div><input type="datetime-local" name="value" value="{0}">'.format(html_friendly_date_string)
        return r'<input type="datetime-local" name="value" value="{0}">'.format(date.isoformat())
    if len(value) > 100:
        return textarea_html
    return default

def is_date_iso(string):
    try:
        datetime.fromisoformat(string)
        return True
    except ValueError:
        return False

def is_date_epoch(string):
    start_date = datetime(2000, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2038, 1, 19, tzinfo=timezone.utc)
    try:
        date = datetime.fromtimestamp(int(string), tz=timezone.utc)
        return start_date <= date <= end_date
    except ValueError:
        return False

@app.route('/', methods=['GET'])
def index():
    cursor = connection.execute("SELECT * FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cursor.fetchall()
    state = create_table_state()
    
    columns = []
    rows = []
    table = []
    if state['table_name']:
        cursor = connection.execute(f"PRAGMA table_info([{state['table_name']}]);")
        columns = cursor.fetchall()

        cursor = connection.execute(f"SELECT * FROM [{state['table_name']}];")
        rows = cursor.fetchall()

        for column in columns:
            table.append({ 'value': column['name'], 'is_header': True })
        for row in rows:
            for column in columns:
                table.append({ 'value': row[column['name']], 'is_header': False })

    return render_template_string("""
    <html>
        <head>
            <title>Editor API</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='css/sqlite-editor.css') }}">
            <style>
                html {
                    --main-background-color: #333;
                    --background-color: #444;
                    --text-color: white;
                    --border-color: #555;
                }
                table { color: white; }
                main { 
                    min-width: 100%;
                    width: max-content; 
                }
                table { width: auto; }

                /* td, th                { width: 200px; } */

                td.link, td.image     { width: 200px; }
                td.text-long          { width: 300px; }
                td.text-long textarea { height: 150px; }


                td.link, td.image { line-break: anywhere; }
                textarea                                    { height: 3rem; overflow-y: hidden; width: 100%; }
                textarea:focus, td.text-long textarea:focus { height: auto; field-sizing: content }

                th { text-align: left; }
                table {
                    border-collapse: collapse;
                }
                th {
                    color: #aaa;
                }
                td, th { 
                    padding: 8px;
                    border: solid 1px var(--border-color);
                }
                td input, td textarea {
                    border-color: var(--border-color) !important;
                    border-radius: 4px;
                }
                td { 
                    text-align: center; 
                    vertical-align: middle;
                }

                input[type="submit"] {
                    font-family: monospace;
                    background-color: var(--background-color);
                    border: solid 1px var(--border-color);
                    padding: 8px;
                    color: white;
                    border-radius: 4px;
                    cursor: pointer;
                    box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
                }
                /* datepicker */
                input[type="datetime-local"] {
                    border: solid 1px var(--border-color);
                    background-color: var(--background-color);
                    border-radius: 4px;
                    color: white;
                    padding: 2px;
                }
                textarea:focus-visible {
                    outline: none;
                }

                main {
                    padding: 0 !important;
                }
                .content {
                }

                main > .content{
                    padding: 1rem;
                }
                form input[type="text"] {
                    border-color: var(--border-color);
                }
                thead {
                    position: sticky;
                    top: 0;
                    background: var(--main-background-color);
                }
                .sticky {
                    box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
                }
                table {
                    box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
                }

                body {
                    background: red;
                }

                .content {
                    margin-bottom: 45px;
                }
                .bottom {
                    position: fixed;
                }


                .bottom {
                    width: 100%;
                    background: var(--main-background-color);
                    bottom: 0;
                    padding: 8px;
                    margin: 0;
                    padding-top: 8px;
                    box-shadow: 0 0 4px rgba(0, 0, 0, 0.5);
                }
                .bottom form {
                    margin-bottom: 0 !important;
                }
                    
                input.footer-input {
                    color: gray;
                }
                input.active-footer-input {
                    background: var(--main-background-color) !important;
                    font-weight: bold;
                }

                select {
                    font-family: monospace;
                    background-color: var(--background-color);
                    color: white;
                    border: solid 1px var(--border-color);
                    border-radius: 4px;
                    padding: 8px;
                }

                option {
                    background-color: var(--background-color);
                    color: white;
                }


                

            </style>
        </head>
        <body>
            <main class="font-mono">
                <div class="content">
                    {% if state['table_name'] %}
                    <form action="{{ url_for('add_column', table_name=state['table_name']) }}" method="post">
                        <input type="text" name="name" placeholder="Column name">
                        <!-- dropdown for type: TEXT, INTEGER, REAL, BLOB -->
                        <select name="type" size="1">
                            <option value="TEXT">TEXT</option>
                            <option value="INTEGER">INTEGER</option>
                            <option value="REAL">REAL</option>
                            <option value="BLOB">BLOB</option>
                        </select>
                        <input type="submit" value="Add column">
                    </form>

                    <table>
                        <thead>
                            <tr>
                                {% for column in columns %}
                                <th>
                                    {{ column.name }} ({{ column.type }})
                                    </th>
                                {% endfor %}
                            </tr>
                        </thead>
                        <tbody>
                            {% for row in rows %}
                            <tr>
                                {% for column in columns %}
                                <td class="{{ cell_to_class(row[column.name]) }}">
                                    <div>
                                        {% if column.name == 'id' %}
                                        <span style="color: gray">{{ row['id'] }}</span>
                                        {% else %}
                                        <form action="{{ url_for('update_cell', table_name=state['table_name'], column_name=column.name, row_id=row['id']) }}" method="post">

                                            <!-- cell_to_input(row[column.name]) -->
                                            {{ cell_to_input(row[column.name]) | safe }}
                                            <input type="submit" value="Update" hidden>
                                        </form>
                                        {% endif %}
                                    </div>
                                {% endfor %}
                            </tr>
                            {% endfor %}
                            <form action="{{ url_for('add_row', table_name=state['table_name']) }}" method="post">
                                <tr>
                                    <td>
                                        ID
                                    </td>
                                    {% for column in columns if column.name != 'id' %}
                                    <td>
                                        <input type="text" name="{{ column.name }}" placeholder="{{ column.name }}">
                                    </td>
                                    {% endfor %}
                                </tr>
                                <!-- make td aligned to right -->
                                <tr>
                                    {% for i in range(columns.__len__()-1) %}
                                    <td></td>
                                    {% endfor %}
                                    <td><input type="submit" value="Add row"></td>
                                </tr>
                            </form>

                        </tbody>

                    </table>


                    {% else %}
                    <h1>No active table</h1>
                    {% endif %}
                </div>
                <div class="wide bottom">
                    {% for table in tables %}
                    <form action="{{ url_for('select_table', table_name=table.name) }}" method="post">
                        {% if table.name == state['table_name'] %}
                        <input type="submit" value="{{ table.name }}" class="active-footer-input">
                        {% else %}
                        <input type="submit" value="{{ table.name }}" class="footer-input">
                        {% endif %}
                    </form>
                    {% endfor %}
                    <form action="{{ url_for('create_table') }}" method="post">
                        <input type="text" name="name" placeholder="Table name">
                        <input type="submit" value="Create table">
                    </form>

                </div>
            </main>
            <script>

                // textarea: Pressing ENTER should submit the form
                document.addEventListener('keydown', function (event) {
                    // pressing shift-enter should insert a new line
                    if (event.target.tagName === 'TEXTAREA' && event.key === 'Enter' && !event.shiftKey) {
                        event.preventDefault();
                        event.target.form.querySelector('input[type="submit"]').click();
                    }
                });

                // on date close, do submit
                document.addEventListener('change', function (event) {
                    if (event.target.type === 'datetime-local') {
                        event.target.form.querySelector('input[type="submit"]').click();
                    }
                });


                // when the stickied thead is on top after a scroll-vertical, add a class: "sticky"
                document.addEventListener('scroll', function (event) {
                    var thead = document.querySelector('thead');
                    if (thead.getBoundingClientRect().top <= 0) {
                        thead.classList.add('sticky');
                    } else {
                        thead.classList.remove('sticky');
                    }
                });
                content = document.querySelector('.content');
                content.addEventListener('scroll', function (event) {
                    var thead = document.querySelector('thead');
                    if (thead.getBoundingClientRect().top <= 0) {
                        thead.classList.add('sticky');
                    } else {
                        thead.classList.remove('sticky');
                    }
                });

            </script>
        </body>
    </html>""", tables=tables, state=state, columns=columns, rows=rows, table=table, cell_to_input=cell_to_input, cell_to_class=cell_to_class)

def main():
    create_table_state()
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=True)

if __name__ == "__main__":
    main()
