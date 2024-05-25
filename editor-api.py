
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
                table { color: white; }
                th { text-align: left; }
            </style>
        </head>
        <body>
            <main class="font-mono">
                <div>
                    {% if state['table_name'] %}
                    <h1>Active Table: {{ state['table_name'] }}</h1>
                    <form action="{{ url_for('add_column', table_name=state['table_name']) }}" method="post">
                        <input type="text" name="name" placeholder="Column name">
                        <!-- dropdown for type: TEXT, INTEGER, REAL, BLOB -->
                        <select name="type">
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
                                <td>
                                    {% if column.name == 'id' %}
                                    {{ row['id'] }}
                                    {% else %}
                                    <form action="{{ url_for('update_cell', table_name=state['table_name'], column_name=column.name, row_id=row['id']) }}" method="post">
                                        <input type="text" name="value" value="{{ row[column.name] }}">
                                        <input type="submit" value="Update" hidden>
                                    </form>
                                    {% endif %}
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
                <div class="wide">
                    {% for table in tables %}
                    <div>
                        <span>{{ table.name }}</span>
                        <div class="wide">
                            <form action="{{ url_for('delete_table', table_name=table.name) }}" method="post">
                                <input type="submit" value="Delete table">
                            </form>
                            <form action="{{ url_for('select_table', table_name=table.name) }}" method="post">
                                <input type="submit" value="Select table">
                            </form>
                        </div>
                    </div>
                    {% endfor %}
                    <form action="{{ url_for('create_table') }}" method="post">
                        <input type="text" name="name" placeholder="Table name">
                        <input type="submit" value="Create table">
                    </form>

                </div>
            </main>
        </body>
    </html>""", tables=tables, state=state, columns=columns, rows=rows, table=table)

def main():
    create_table_state()
    app.run(host='0.0.0.0', port=8000, debug=True, use_reloader=True)

if __name__ == "__main__":
    main()
