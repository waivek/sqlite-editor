
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
import json

app = Flask(__name__)
app.config['Access-Control-Allow-Origin'] = '*'
CORS(app)

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
    if not os.path.exists(state_path) or os.path.getsize(state_path) == 0:
        state = {}
        state["settings"] = { "db_path": None }
        write(state, state_path)

    db_paths = get_db_paths()
    for db_path in db_paths:
        if db_path not in read(state_path):
            state = read(state_path)
            state[db_path] = { 'table_name': None }
            write(state, state_path)

    state = read(state_path)
    return state

@app.route('/api/tables/<table_name>/select', methods=['POST'])
def select_table(table_name):
    db_path = request.form.get('db_path')
    state = create_table_state()
    state[db_path]['table_name'] = table_name
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

def paginate(select_clause, table_name, where_clause, order_by_clause, page_number, page_size):
    # page_number is 1-indexed
    offset = (page_number - 1) * page_size
    cursor = connection.execute(f"{select_clause} FROM [{table_name}] {where_clause} {order_by_clause} LIMIT {page_size} OFFSET {offset};")
    rows = cursor.fetchall()
    cursor_2 = connection.execute(f"SELECT COUNT(*) FROM [{table_name}] {where_clause};")
    row_count = cursor_2.fetchone()[0]
    page_count = row_count // page_size
    if row_count % page_size != 0:
        page_count += 1

    pagination = { 
                  "page": page_number, 
                  "page_count": page_count, 
                  "is_first_page": page_number == 1, 
                  "is_last_page": page_number == page_count, 
                  "prev": page_number - 1, 
                  "next": page_number + 1,
                  "total": row_count
                  }
    return rows, pagination


def cell_to_input(value):
    if value is None:
        return r'<input type="text" name="value" value="">'
    value = str(value)
    default = r'<input type="text" name="value" value="{0}">'.format(value)
    textarea_html = get_textarea_html(value)
    if value.endswith('.jpg') or value.endswith('.png') or value.endswith('.jpeg'):
        image_html = r'<img src="{0}" class="image-success" alt="{0}" title="{0}" onerror="handle_image_error(this)">'.format(value)
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
            date = parse_date_iso(value)
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

def parse_date_iso(string):
    # handle trailing 'Z'
    if string.endswith('Z'):
        string = string[:-1]
    return datetime.fromisoformat(string)


def is_date_iso(string):
    try:
        parse_date_iso(string)
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


def get_db_paths():
    from getdbpaths import update_db_paths_text_file
    from waivek import readlines
    text_file_path = update_db_paths_text_file()
    return readlines(text_file_path)

@app.route('/api/load_db', methods=['POST'])
def load_db():
    db_path = request.form.get('db_path')
    state = create_table_state()
    state['settings']['db_path'] = db_path
    write(state, rel2abs('data/state.json'))
    return redirect(url_for('index'))

def get_autoincrementing_primary_key_or_none(table_name):
    cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
    columns = cursor.fetchall()
    for column in columns:
        if column['pk'] == 1:  # primary key
            cursor.execute(f"SELECT * FROM sqlite_master WHERE type='table' AND name='{table_name}'")
            table_info = cursor.fetchone()
            if "AUTOINCREMENT" in table_info[4]:
                return column['name']
    return None

def update_page(page):
    db_path = request.form.get('db_path')
    table_name = request.form.get('table_name')


@app.route('/', methods=['GET'])
def index():
    global connection

    state = create_table_state()

    if state["settings"]["db_path"]:
        connection = Connection(state["settings"]["db_path"])

    db_paths = get_db_paths()
    
    tables = []
    columns = []
    rows = []
    table = []
    settings = state["settings"]
    db_path = settings["db_path"]
    table_name = None
    autoincrementing_primary_key_name = None
    pagination = None
    page_size = 20
    page = 1


    if db_path:
        table_name = state[db_path]['table_name']
        cursor = connection.execute("SELECT * FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = cursor.fetchall()
        # get page_size from data/state.json. 
        # key: state[db_path]['page_size']
        # if not present, default to 20 and write to data/state.json
        if db_path in state and 'page_size' in state[db_path]:
            page_size = state[db_path]['page_size']
        else:
            state[db_path]['page_size'] = page_size
            write(state, rel2abs('data/state.json'))
        # do same for page
        if db_path in state and 'page' in state[db_path]:
            page = state[db_path]['page']
        else:
            state[db_path]['page'] = page
            write(state, rel2abs('data/state.json'))


    if table_name:
        cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
        columns = cursor.fetchall()

        # check if there is an autoincrementing primary key
        autoincrementing_primary_key_name = get_autoincrementing_primary_key_or_none(table_name)

        # cursor = connection.execute(f"SELECT * FROM [{table_name}] LIMIT 20;")
        # rows = cursor.fetchall()
        rows, pagination = paginate("SELECT *", table_name, "", "", 1, 20)

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
                body { margin: 0; padding: 0; }
                body, .container, .content, .bottom, .scrollable-content {
                    padding: 0;
                    margin: 0;
                    box-sizing: border-box;
                }

                body {
                    height: 100%;
                }
                table {
                    width: max-content;
                }
                .container {
                    display: flex;
                    flex-direction: column;
                    height: 100vh;
                    box-sizing: border-box; /* Ensures padding is included in the height */
                }
                .content {
                    flex: 1;
                    overflow: hidden;
                    box-sizing: border-box; /* Ensures padding is included in the height */
                }
                .scrollable-content {
                    height: 100%;
                    overflow: hidden; /* Prevents internal scrolling */
                    box-sizing: border-box; /* Ensures padding is included in the height */

                }

                .inner-scrollable-content {
                    height: 100%;
                    overflow-y: auto; /* Makes this content scrollable */
                    padding: 1em;
                    box-sizing: border-box;
                }

                .container { 
                    background: var(--main-background-color);
                    color: white;
                }
                /* table { width: auto; } */

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


                form input[type="text"] {
                    border-color: var(--border-color);
                }
                thead {
                    position: sticky;
                    top: -1rem;
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


                .bottom {
                    width: 100%;
                    background: var(--main-background-color);
                    /* bottom: 0; */
                    padding: 8px;
                    margin: 0;
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

                /* google sheets style scrollbars */

                ::-webkit-scrollbar {
                    width: 12px;
                    height: 12px;
                }

                ::-webkit-scrollbar-thumb {
                    background: var(--border-color);
                    border-radius: 6px;
                }

                ::-webkit-scrollbar-thumb:hover {
                    background: #666;
                }

                ::-webkit-scrollbar-track {
                    background: var(--main-background-color);
                }

                ::-webkit-scrollbar-corner {
                    background: var(--main-background-color);
                }

                /* end google sheets style scrollbars */


                input[type="datetime-local"], input {
                    color-scheme: dark;
                }

                .image-success {
                    max-width: 100px;
                    max-height: 100px;
                }
                .image-failed {
                    /* line-break: auto;
                    width: 100%;*/
                }


            </style>
            <script>
                function handle_image_error(image) {
                    image.classList.replace('image-success', 'image-failed');
                    image.alt = 'Image errored';
                }
            </script>
        </head>
        <body>
            <div class="container font-mono">
                <div class="content">
                    <div class="scrollable-content">
                        <div class="inner-scrollable-content">
                            <div class="wide">
                                {% if active_table_name %}
                                <form action="{{ url_for('add_column', table_name=active_table_name) }}" method="post">
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
                                {% endif %}
                                <form action="{{ url_for('load_db') }}" method="post">
                                    <select name="db_path" size="1">
                                        {% for db_path in db_paths %}
                                        {% if db_path == active_db_path %}
                                        <option value="{{ db_path }}" selected>{{ db_path }}</option>
                                        {% else %}
                                        <option value="{{ db_path }}">{{ db_path }}</option>
                                        {% endif %}
                                        {% endfor %}
                                    </select>
                                    <input type="submit" value="Load DB">
                                </form>
                            </div>
                            {% if active_table_name %}
                            <!-- pagination -->
                            <div class="wide">
                                <span>Total: {{ pagination["total"] }}</span>
                                {% if pagination["is_first_page"] %}
                                <span>First</span>
                                {% else %}
                                <form action="{{ url_for('index') }}" method="post">
                                    <input type="hidden" name="page" value="0">
                                    <input type="submit" value="First">
                                </form>
                                {% endif %}
                                {% if pagination["prev"] >= 0 %}
                                <form action="{{ url_for('index') }}" method="post">
                                    <input type="hidden" name="page" value="{{ pagination['prev'] }}">
                                    <input type="submit" value="Prev">
                                </form>
                                {% else %}
                                <span>Prev</span>
                                {% endif %}
                                <span>Page {{ pagination["page"] }} of {{ pagination["page_count"] }}</span>
                                {% if not pagination["is_last_page"] %}
                                <form action="{{ url_for('index') }}" method="post">
                                    <input type="hidden" name="page" value="{{ pagination['next'] }}">
                                    <input type="submit" value="Next">
                                </form>
                                {% else %}
                                <span>Next</span>
                                {% endif %}
                                {% if not pagination["is_last_page"] %}
                                <form action="{{ url_for('index') }}" method="post">
                                    <input type="hidden" name="page" value="{{ pagination['page_count'] }}">
                                    <input type="submit" value="Last">
                                </form>
                                {% else %}
                                <span>Last</span>
                                {% endif %}
                            </div>
                            {% endif %}
                                



                            {% if active_db_path and active_table_name %}
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
                                                {% if autoincrementing_primary_key_name and column.name == autoincrementing_primary_key_name %}
                                                <span style="color: gray">{{ row['id'] }}</span>
                                                {% else %}
                                                <form action="{{ url_for('update_cell', table_name=active_table_name, column_name=column.name, row_id=row['id']) }}" method="post">

                                                    <!-- cell_to_input(row[column.name]) -->
                                                    {{ cell_to_input(row[column.name]) | safe }}
                                                    <input type="submit" value="Update" hidden>
                                                </form>
                                                {% endif %}
                                            </div>
                                        {% endfor %}
                                    </tr>
                                    {% endfor %}
                                    <form action="{{ url_for('add_row', table_name=active_table_name) }}" method="post">
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
                            {% endif %}
                        </div>
                    </div>
                </div> <!-- end div.content -->
                <div class="wide bottom">
                    {% for table in tables %}
                    <form action="{{ url_for('select_table', table_name=table.name) }}" method="post">
                        {% if table.name == active_table_name %}
                        <input type="submit" value="{{ table.name }}" class="active-footer-input">
                        {% else %}
                        <input type="submit" value="{{ table.name }}" class="footer-input">
                        {% endif %}
                        <!-- hidden payload containing db_path -->
                        <input type="hidden" name="db_path" value="{{ active_db_path }}">
                    </form>
                    {% endfor %}
                    <form action="{{ url_for('create_table') }}" method="post">
                        <input type="text" name="name" placeholder="Table name">
                        <input type="submit" value="Create table">
                    </form>

                </div>
            </div>
            <script>
                console.log("hello from editor-api.py");

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
                content = document.querySelector('.inner-scrollable-content');
                content.addEventListener('scroll', function (event) {
                    var thead = document.querySelector('thead');

                    // if (thead.getBoundingClientRect().top <= 0) {
                    // if (content.scrollTop >= 1) {
                    // check if thead is on top, by comparing to upper edge of `.scrollable-content`

                    if (thead.getBoundingClientRect().top <= content.getBoundingClientRect().top) {
                        thead.classList.add('sticky');
                    } else {
                        thead.classList.remove('sticky');
                    }
                });


            </script>
        </body>
    </html>""", tables=tables, state=state, columns=columns, rows=rows, table=table, cell_to_input=cell_to_input, cell_to_class=cell_to_class, db_paths=db_paths, json=json, active_db_path=db_path, active_table_name=table_name, autoincrementing_primary_key_name=autoincrementing_primary_key_name, pagination=pagination)

state = create_table_state()
settings = state["settings"]
db_path = settings["db_path"]
connection = Connection(":memory:")

def main():
    create_table_state()
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=True)

if __name__ == "__main__":
    main()
