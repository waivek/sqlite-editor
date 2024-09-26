

from flask import request
from flask import render_template_string
from flask import render_template
from flask import Flask
from flask import Request
from flask import redirect
from flask import url_for
from flask_cors import CORS
from dbutils import Connection
from waivek import read, write, rel2abs
import os
from datetime import datetime, timezone, timedelta
import timeago
import json
from state import get_state
from flask import session
import html

app = Flask(__name__)
app.config['Access-Control-Allow-Origin'] = '*'
CORS(app)

@app.route('/api/tables/<table_name>/delete', methods=['POST'])
def delete_table(table_name):
    connection.execute(f"DROP TABLE [{table_name}];")
    state = request_to_state(request)
    state._refresh_table_configs_of_active_db_config()
    return redirect(url_for('index'))

def request_to_state(request: Request):
    # user_id = int(request.cookies['id'])
    user_id = int(session['id'])
    return get_state(user_id)

def request_to_connection(request: Request):
    state = request_to_state(request)
    if not state.active_db_path:
        raise Exception("No active db path")
    return Connection(state.active_db_path)

@app.route('/api/tables/<table_name>/select', methods=['POST'])
def select_table(table_name):
    # get id by request cookie
    db_path = request.form.get('db_path')
    state = request_to_state(request)
    state.set_active_table(table_name)
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
    connection = request_to_connection(request)

    columns = []
    cursor = connection.execute("SELECT * FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
    tables = cursor.fetchall()

    cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
    pragma_rows = cursor.fetchall()
    for column in pragma_rows:
        columns.append(column['name'])
    values = []
    for column in columns:
        values.append(request.form.get(column))
    escaped_columns = [ f"[{column}]" for column in columns ]

    query = f"INSERT INTO [{table_name}] ({', '.join(escaped_columns)}) VALUES ({', '.join(['?' for _ in columns])});"

    try:
        connection.execute(query, values)
    except:
        return { "error": "Failed to insert row", "query": query, "values": values }
    connection.commit()
    # return { "success": "Inserted row", "query": query, "values": values }
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
    if type(value) == bytes: 
        return 'blob'
    value = str(value)
    if '.mp4' or '.mp4?' or '.webm' or '.webm?' in value:
        return 'video'
    if value.endswith('.jpg') or value.endswith('.png') or value.endswith('.jpeg'):
        return 'image'
    if '.jpg?' in value or '.png?' in value or '.jpeg?' in value:
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
    if type(value) == bytes:
        return "<div>{0}</div>".format(value)
    value = str(value)
    value = html.escape(value)
    default = r'<input type="text" name="value" value="{0}">'.format(value)
    textarea_html = get_textarea_html(value)
    if '.mp4' in value or '.mp4?' in value or '.webm' in value or '.webm?' in value:
        video_html = r'<video controls preload="metadata"><source src="{0}" type="video/mp4"></video>'.format(value)
        clickable_video_html = r'<a href="{0}">{1}</a>'.format(value, video_html)
        return r"""
        <div class="tall">
            <div>{0}</div>
            {1}
        </div>
        """.format(clickable_video_html, textarea_html)
    if value.endswith('.jpg') or value.endswith('.png') or value.endswith('.jpeg') or '.jpg?' in value or '.png?' in value or '.jpeg?' in value:
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
    start_date_epoch = start_date.timestamp()
    end_date_epoch = end_date.timestamp()
    try:
        if int(string) > end_date_epoch or int(string) < 0:
            return False
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
    db_path = request.form['db_path']
    state = request_to_state(request)
    state.set_active_db_path(db_path)
    state.set_active_table_to_first_if_present_and_no_active_table()
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

@app.route("/api/page/<page_number>", methods=['POST'])
def page(page_number):
    state = request_to_state(request)
    state.set_page(page_number)
    return redirect(url_for('index'))

@app.route('/api/hide_column', methods=['POST'])
def hide_column():
    state = request_to_state(request)
    column_name = request.args.get('column_name')
    state.hide_column(column_name)
    return redirect(url_for('index'))

@app.route('/api/update_column_visibility_batch', methods=['POST'])
def update_column_visibility_batch():
    state = request_to_state(request)
    active_table_config = state.get_active_table_config()
    if not active_table_config:
        raise Exception("No active table config")
    table_name = active_table_config.name
    connection = request_to_connection(request)
    # get column names
    cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
    columns = cursor.fetchall()
    column_names = [ column['name'] for column in columns ]
    selected_column_names = request.form.getlist('column_names')
    hidden_column_names = set(column_names) - set(selected_column_names)
    state.clear_hidden_columns()
    state.hide_columns_batch(hidden_column_names)
    return redirect(url_for('index'))

@app.route('/api/add_column_name_to_sort_column_pairs', methods=['POST'])
def add_column_name_to_sort_column_pairs():
    state = request_to_state(request)
    column_name = request.form.get('column_name')
    sort_type = request.form.get('sort_type')
    state.add_column_name_to_sort_column_pairs(column_name, sort_type)
    return redirect(url_for('index'))

@app.route('/api/remove_column_name_from_sort_column_pairs', methods=['POST'])
def remove_column_name_from_sort_column_pairs():
    state = request_to_state(request)
    column_name = request.form.get('column_name')
    state.remove_column_name_from_sort_column_pairs(column_name)
    return redirect(url_for('index'))

@app.route('/views/view_batch_select_column_names', methods=['GET'])
def view_batch_select_column_names():
    state = request_to_state(request)
    connection = request_to_connection(request)
    table_config = state.get_active_table_config()
    if not table_config:
        raise Exception("No active table config")
    table_name = table_config.name
    hidden_column_names = table_config.hidden_column_names
    cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
    columns = cursor.fetchall()
    return render_template_string("""
    <html>
        <head>
            <title>Editor API</title>
            <link rel="stylesheet" href="{{ url_for('static', filename='css/base-dark.css') }}">
            <link rel="stylesheet" href="{{ url_for('static', filename='css/editor.css') }}">
            <style>
            label { user-select: none; }
            </style>
        </head>
        <body>
            <div class="container font-mono">
                <div class="content">
                    <div class="scrollable-content">
                        <div class="inner-scrollable-content">
                            <form action="{{ url_for('update_column_visibility_batch') }}" method="post">
                                <div class="tall">
                                    <div>
                                        {% for column in columns %}
                                        <label class="wide center-h">
                                            <input type="checkbox" name="column_names" value="{{ column.name }}" {% if column.name not in hidden_column_names %}checked{% endif %}>
                                            <span>{{ column.name }}</span>
                                        </label>
                                        {% endfor %}
                                    </div>
                                    <div><input type="submit" value="Update"></div>
                                    <!-- controls to "Select All" and "Select None" via javascript -->
                                    <div>
                                        <input type="button" value="Select All" onclick="document.querySelectorAll('input[name=column_names]').forEach((input) => input.checked = true)">
                                        <input type="button" value="Select None" onclick="document.querySelectorAll('input[name=column_names]').forEach((input) => input.checked = false)">
                                    </div>

                                </div>
                            </form>
                        </div>
                    </div>
                </div>
            </div>
        </body>
    </html>
    """, state=state, columns=columns, table_name=table_name, hidden_column_names=hidden_column_names)

@app.route('/', methods=['GET'])
def index():
    if 'id' not in session:
        session['id'] = 1
        return redirect(url_for('index'))

    global connection

    state = request_to_state(request)

    if state.active_db_path:
        connection = Connection(state.active_db_path)

    db_paths = get_db_paths()
    # db_paths = []
    # sort db_paths on mtime
    db_paths = sorted(db_paths, key=lambda db_path: os.path.getmtime(db_path), reverse=True)
    db_path_objects = [ { "path": db_path, "mtime": os.path.getmtime(db_path), 
                         "size": os.path.getsize(db_path),
                         "size_human": "{0} KB".format(int(os.path.getsize(db_path) / 1024)),
                         "mtime_human": timeago.format(os.path.getmtime(db_path))
                         } for db_path in db_paths ]
    for db_path_object in db_path_objects:
        db_path_object['human'] = f"{db_path_object['path']} ({db_path_object['size_human']}, {db_path_object['mtime_human']})"
    # put empty db_path_object with size 0 at the end
    db_path_objects = sorted(db_path_objects, key=lambda db_path_object: db_path_object['size'] == 0)


    
    tables = []
    columns = []
    rows = []
    table_name = None
    autoincrementing_primary_key_name = None
    pagination = None
    table_config = None

    if state.active_db_path:
        cursor = connection.execute("SELECT * FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        tables = cursor.fetchall()
        table_config = state.get_active_table_config()

    if table_config:

        table_name = table_config.name
        cursor = connection.execute(f"PRAGMA table_info([{table_name}]);")
        columns = cursor.fetchall()
        columns = [ column for column in columns if column['name'] not in table_config.hidden_column_names ]

        autoincrementing_primary_key_name = get_autoincrementing_primary_key_or_none(table_name)

        order_by_clause = ""
        if table_config.sort_column_pairs:
            sort_column_pairs = table_config.sort_column_pairs
            order_by_clause = "ORDER BY " + ", ".join([ f"[{column_name}] {sort_type}" for column_name, sort_type in sort_column_pairs ])

        rows, pagination = paginate("SELECT *", table_name, "", order_by_clause, table_config.page, table_config.page_size)

    # feature_flag = False
    feature_flag = True
    return render_template_string("""
    <html>
        <head>
            <title>Editor API</title>
            {% if feature_flag %}

            <link rel="stylesheet" href="{{ url_for('static', filename='ui-components-css/css-utilities/wide-tall.css') }}"> 
            <link rel="stylesheet" href="{{ url_for('static', filename='ui-components-css/css-themes/dark-gray-mono.css') }}"> 

            <link rel="stylesheet" href="{{ url_for('static', filename='css/editor-2.css') }}"> 

            {% else %}
            <link rel="stylesheet" href="{{ url_for('static', filename='css/base-dark.css') }}">  
            <link rel="stylesheet" href="{{ url_for('static', filename='css/editor.css') }}"> 
            {% endif %}
            <script>
                function handle_image_error(image) {
                    console.log('Image Error');
                    image.classList.replace('image-success', 'image-failed');
                    image.alt = 'Image errored';
                }
            </script>
            <style>
            .justify-between { justify-content: space-between; }
            .flex-wrap { flex-wrap: wrap; }
            .font-bold { font-weight: bold; }
            .red { color: red !important; }
            .gray { color: gray !important; }
            .white { color: white !important; }
            </style>
        </head>
        <body>
            <div class="container font-mono">
                {% if feature_flag %}
                <div class="content tall">
                {% else %}
                <div class="content">
                    <div class="scrollable-content">
                        <div class="inner-scrollable-content tall">
                {% endif %}

                    
                            <div class="wide flex-wrap justify-between">
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
                                        {% for db_path_object in db_path_objects %}
                                        {% if db_path_object.path == active_db_path %}
                                        <option value="{{ db_path_object.path }}" selected>{{ db_path_object.human }}</option>
                                        {% else %}
                                        <option class="{{ 'gray' if db_path_object.size == 0 else '' }}" value="{{ db_path_object.path }}">{{ db_path_object.human }}</option>
                                        {% endif %}
                                        {% endfor %}
                                    </select>
                                    <input type="submit" value="Load DB">
                                </form>
                            </div>
                            {% if active_table_name %}
                            <!-- pagination -->
                            <div class="wide center-h">
                                <div class="wide center-h">
                                    <span>Total: {{ pagination["total"] }}</span>
                                    {% if pagination["is_first_page"] %}
                                    <span class="gray">First</span>
                                    {% else %}
                                    <form action="{{ url_for('page', page_number=1) }}" method="post">
                                        <input type="submit" value="First">
                                    </form>
                                    {% endif %}
                                    {% if not pagination["is_first_page"] %}
                                    <form action="{{ url_for('page', page_number=pagination['prev']) }}" method="post">
                                        <input type="submit" value="Prev">
                                    </form>
                                    {% else %}
                                    <span class="gray">Prev</span>
                                    {% endif %}
                                    <span>Page {{ pagination["page"] }} of {{ pagination["page_count"] }}</span>
                                    {% if not pagination["is_last_page"] %}
                                    <form action="{{ url_for('page', page_number=pagination['next']) }}" method="post">
                                        <input type="submit" value="Next">
                                    </form>
                                    {% else %}
                                    <span class="gray">Next</span>
                                    {% endif %}
                                    {% if not pagination["is_last_page"] %}
                                    <form action="{{ url_for('page', page_number=pagination['page_count']) }}" method="post">
                                        <input type="submit" value="Last">
                                    </form>
                                    {% else %}
                                    <span class="gray">Last</span>
                                    {% endif %}
                                </div>

                                <div>
                                    <div>
                                        <a href="{{ url_for('view_batch_select_column_names') }}">Batch select column names</a>
                                    </div>
                                </div>
                            </div>
                            {% endif %}




                            {% if active_db_path and active_table_name %}
                            <table>
                                <thead>
                                    <tr>
                                        {% for column in columns %}
                                        <th>
                                            <div class="tall">
                                                <div class="font-bold">{{ column.name }} ({{ column.type }})</div>
                                                <div class="wide center-h thead-controls">
                                                    <span>
                                                        <form action="{{ url_for('hide_column', db_path=active_db_path, table_name=active_table_name, column_name=column.name) }}" method="POST">
                                                            <input type="submit" value="Hide" class="gray">
                                                        </form>
                                                    </span>
                                                    {% if (column.name, 'ASC') not in state.get_active_table_config().sort_column_pairs %}
                                                    <span>
                                                        <form action="{{ url_for('add_column_name_to_sort_column_pairs', db_path=active_db_path, table_name=active_table_name) }}" method="POST">
                                                            <input type="hidden" name="column_name" value="{{ column.name }}">
                                                            <input type="hidden" name="sort_type" value="ASC">
                                                            <input type="submit" value="ASC" class="gray">
                                                        </form>
                                                    </span>
                                                    {% else %}
                                                    <span class="font-bold white">ASC</span>
                                                    {% endif %}

                                                    {% if (column.name, 'DESC') not in state.get_active_table_config().sort_column_pairs %}
                                                    <span>
                                                        <form action="{{ url_for('add_column_name_to_sort_column_pairs', db_path=active_db_path, table_name=active_table_name) }}" method="POST">
                                                            <input type="hidden" name="column_name" value="{{ column.name }}">
                                                            <input type="hidden" name="sort_type" value="DESC">
                                                            <input type="submit" value="DESC" class="gray">
                                                        </form>
                                                    </span>
                                                    {% else %}
                                                    <span class="font-bold white">DESC</span>
                                                    {% endif %}
                                                    {% if (column.name, 'ASC') in state.get_active_table_config().sort_column_pairs or (column.name, 'DESC') in state.get_active_table_config().sort_column_pairs %}
                                                    <span>
                                                        <form action="{{ url_for('remove_column_name_from_sort_column_pairs', db_path=active_db_path, table_name=active_table_name) }}" method="POST">
                                                            <input type="hidden" name="column_name" value="{{ column.name }}">
                                                            <input type="submit" value="Clear" class="gray">
                                                        </form>
                                                    </span>
                                                    {% endif %}

                                                </div>
                                            </div>

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
                                                {% elif cell_to_class(row[column.name]) == 'blob' %}
                                                {{ row[column.name] }}
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
                                            {% for column in columns %}
                                                {% if autoincrementing_primary_key_name and column.name == autoincrementing_primary_key_name %}
                                                <td>
                                                    <div style="color: gray">{{ column.name }}</div>
                                                    <div style="color: gray">AUTOINCREMENT</div>
                                                </td>
                                                {% else %}
                                                <td>
                                                    <input type="text" name="{{ column.name }}" placeholder="{{ column.name }}">
                                                </td>
                                                {% endif %}
                                            {% endfor %}
                                        </tr>
                                        <!-- make td aligned to right -->
                                        <tr>
                                            <td colspan="{{ columns|length }}" style="text-align: right;"><input type="submit" value="Add row"></td>
                                        </tr>
                                    </form>

                                </tbody>

                            </table>
                            {% endif %}
                </div> <!-- end div.content -->
                    {% if not feature_flag  %}
                    </div>
                    </div>
                    {% endif %}
                <div class="wide bottom">
                    {% for table in tables %}
                    <form action="{{ url_for('select_table', table_name=table.name) }}" method="post">
                        {% if table.name == active_table_name %}
                        <input type="submit" value="{{ table.name }}" class="active-footer-input font-bold">
                        {% else %}
                        <input type="submit" value="{{ table.name }}" class="footer-input gray">
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
    </html>""", tables=tables, state=state, columns=columns, rows=rows, cell_to_input=cell_to_input, cell_to_class=cell_to_class, db_path_objects=db_path_objects, json=json, active_db_path=state.active_db_path, active_table_name=table_name, autoincrementing_primary_key_name=autoincrementing_primary_key_name, pagination=pagination, feature_flag=feature_flag)

import sqlite3
connection : sqlite3.Connection

def main():
    secret_key = 'secret'
    app.secret_key = secret_key
    app.run(host='0.0.0.0', port=3000, debug=True, use_reloader=True)

if __name__ == "__main__":
    main()
