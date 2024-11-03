from waivek import Timer   # Single Use
timer = Timer()
from waivek import Code    # Multi-Use
from waivek import handler # Single Use
from waivek import ic, ib     # Multi-Use, import time: 70ms - 110ms
from waivek import rel2abs
from waivek import read, write
Code; ic; ib; rel2abs
import json
from dbutils import Connection
from getdbpaths import update_db_paths_text_file
from waivek import readlines
import os
import timeago
import jsonpickle

class TableConfig:
    # db_path, name, page, page_size
    def __init__(self, db_path: str, name: str):

        self.name = name
        self.page: int = 1
        self.page_size: int = 20
        self.db_path = db_path
        self.hidden_column_names = []
        self.sort_column_pairs = []
        self.column_value_filters_dict = {}

    def update_page(self, page):
        self.page = page
    def update_page_size(self, page_size):
        self.page_size = page_size

    def __str__(self):
        return "TableConfig(db_path={}, name={})".format(self.db_path, self.name)

class DatabaseConfig:

    def __init__(self, path: str):

        self.path = path
        self.active_table_name: str | None = None

        self.table_configs: list[TableConfig] = []

class State:
    # db_configs: List[DatabaseConfig], active_db_path: str, id: int (autoincrement)
    def __init__(self, id: int):

        self.id: int = id
        self.active_db_path: str | None = None
        self.db_configs: list[DatabaseConfig] = []

        text_file_path = update_db_paths_text_file()
        db_paths = readlines(text_file_path)
        db_paths.sort(key=lambda db_path: os.path.getmtime(db_path), reverse=True)

        for db_path in db_paths:
            self.db_configs.append(DatabaseConfig(db_path))

    def _update_for_new_db_configs(self):
        text_file_path = update_db_paths_text_file()
        db_paths = readlines(text_file_path)
        db_paths.sort(key=lambda db_path: os.path.getmtime(db_path), reverse=True)
        for db_path in db_paths:
            if db_path not in [db_config.path for db_config in self.db_configs]:
                new_db_config = DatabaseConfig(db_path)
                self.db_configs.append(new_db_config)
        save_state(self)

    def _get_active_db_config(self):
        if not self.active_db_path:
            return None
        return next(db_config for db_config in self.db_configs if db_config.path == self.active_db_path)

    def _refresh_table_configs_of_active_db_config(self):
        db_config = self._get_active_db_config()
        assert db_config
        connection = Connection(db_config.path)
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        table_names = [table_name[0] for table_name in cursor.fetchall()]
        set_1 = set([table_config.name for table_config in db_config.table_configs])
        set_2 = set(table_names)
        table_names_to_add = set_2 - set_1
        table_names_to_remove = set_1 - set_2
        for table_name in table_names_to_add:
            db_config.table_configs.append(TableConfig(db_config.path, table_name))
        for table_name in table_names_to_remove:
            db_config.table_configs = [table_config for table_config in db_config.table_configs if table_config.name != table_name]

    def __str__(self):
        return json.dumps(self, default=vars, indent=4)

    def set_active_db_path(self, db_path: str):
        self._update_for_new_db_configs()
        possible_db_paths = [db_config.path for db_config in self.db_configs]
        if db_path not in possible_db_paths:
            raise Exception(f"Invalid db_path: {db_path}")

        self.active_db_path = db_path
        self._refresh_table_configs_of_active_db_config()
        save_state(self)
        # self._save()

    def set_active_table(self, table_name):
        db_config = self._get_active_db_config()
        if not db_config:
            raise Exception("No active db_config")
        self._refresh_table_configs_of_active_db_config()
        if table_name not in [table_config.name for table_config in db_config.table_configs]:
            raise Exception(f"Invalid table_name: {table_name}")
        db_config.active_table_name = table_name
        save_state(self)
        # self._save()

    def set_page(self, page_number):
        page_number = int(page_number)
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.update_page(page_number)
        save_state(self)
    
    def get_active_table_config(self):
        db_config = self._get_active_db_config()
        if not db_config:
            raise Exception("No active db_config")
        for table_config in db_config.table_configs:
            if table_config.name == db_config.active_table_name:
                return table_config
        return None

    def set_active_table_to_first_if_present_and_no_active_table(self):
        db_config = self._get_active_db_config()
        if not db_config:
            return None
        if db_config.active_table_name:
            return None
        if len(db_config.table_configs) == 0:
            return None
        self.set_active_table(db_config.table_configs[0].name)

    def clear_hidden_columns(self):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.hidden_column_names = []
        save_state(self)

    def show_column(self, column_name):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.hidden_column_names.remove(column_name)
        save_state(self)

    def hide_column(self, column_name):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.hidden_column_names.append(column_name)
        save_state(self)

    def hide_columns_batch(self, column_names):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.hidden_column_names.extend(column_names)
        save_state(self)

    def add_column_name_to_sort_column_pairs(self, column_name, sort_type):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        # check if `column_name` is in `.sort_column_pairs` and remove if it is
        table_config.sort_column_pairs = [(col, sort) for col, sort in table_config.sort_column_pairs if col != column_name]
        table_config.sort_column_pairs.append((column_name, sort_type))
        save_state(self)

    def remove_column_name_from_sort_column_pairs(self, column_name):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.sort_column_pairs = [(col, sort) for col, sort in table_config.sort_column_pairs if col != column_name]
        save_state(self)

    def clear_column_value_filter(self, column_name):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.column_value_filters_dict.pop(column_name, None)
        save_state(self)

    def set_column_value_filter(self, column_name, values, clause):
        table_config = self.get_active_table_config()
        if not table_config:
            raise Exception("No active table_config")
        table_config.column_value_filters_dict[column_name] = (values, clause)
        save_state(self)

    def print_tree(self):
        active_db_config_path = self.active_db_path
        for db_config in self.db_configs:
            mtime = int(os.path.getmtime(db_config.path))
            mtime_string = Code.LIGHTBLACK_EX + "(modified: {0})".format(timeago.format(mtime))
            filesize = os.path.getsize(db_config.path)
            filesize_kb = int(filesize / 1024)
            color = filesize_kb == 0 and Code.RED or Code.LIGHTMAGENTA_EX
            filesize_string = color + f" [{filesize_kb} KB]"
            active_string = db_config.path == active_db_config_path and Code.LIGHTGREEN_EX + " (active)" or ""
            print(Code.CYAN + db_config.path + filesize_string, Code.LIGHTGREEN_EX + active_string, mtime_string)
            for table_config in db_config.table_configs:
                if table_config.name == db_config.active_table_name:
                    print(" " * 4, table_config.name, Code.LIGHTGREEN_EX + " (active)",)
                else:
                    print(" " * 4, table_config.name)

def get_state_save_path(state_id):
    return rel2abs(f"data/state_{state_id}.json")

def save_state(state: State):
    state_save_path = get_state_save_path(state.id)
    with open(state_save_path, "w") as file:
        state_json: str = jsonpickle.encode(state, indent=4) # type: ignore
        file.write(state_json)

def get_state(state_id) -> State:
    global DEBUG
    state_save_path = get_state_save_path(state_id)
    if not os.path.exists(state_save_path) or os.path.getsize(state_save_path) == 0:
        if DEBUG:
            print(Code.LIGHTRED_EX + "State file not found or empty. Creating new state. (path: {0})".format(state_save_path))
        state = State(state_id)
        save_state(state)
        return state
    with open(state_save_path, "r") as file:
        state_json = file.read()
    state: State = jsonpickle.decode(state_json) # type: ignore
    if DEBUG:
        print(Code.LIGHTGREEN_EX + "State loaded successfully. (path: {0})".format(state_save_path))
    return state

def mutate_state(state: State):

    state.set_active_db_path("/home/vivek/sqlite-editor/data/main.db")
    state.set_active_table("items")

    state.set_active_db_path("/home/vivek/hateoas/data/main.db")
    state.set_active_table("sequences")

def main():
    # if os.path.exists(get_state_save_path(1)):
    #     os.remove(get_state_save_path(1))
    state = get_state(1)
    # mutate_state(state)
    state.print_tree()

DEBUG = False
if __name__ == "__main__":
    with handler():
        main()

