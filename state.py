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

class TableConfig:
    # db_path, name, page, page_size
    def __init__(self, db_path: str, name: str):

        self.name = name
        self.page: int = 1
        self.page_size: int = 20
        self.db_path = db_path

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

        self._save_path = rel2abs(f"data/state_{id}.json")

        if not os.path.exists(os.path.dirname(self._save_path)):
            os.makedirs(os.path.dirname(self._save_path))

        self.id = id

        self.active_db_path: str | None
        self.db_configs: list[DatabaseConfig]

        self.active_db_path = None
        self.db_configs = []


        text_file_path = update_db_paths_text_file()
        db_paths = readlines(text_file_path)
        # sort db_paths by mtime
        db_paths.sort(key=lambda db_path: os.path.getmtime(db_path), reverse=True)
        for db_path in db_paths:
            self.db_configs.append(DatabaseConfig(db_path))

    def _get_active_db_config(self):
        if not self.active_db_path:
            return None
        return next(db_config for db_config in self.db_configs if db_config.path == self.active_db_path)

    def _refresh_table_configs(self):
        db_config = self._get_active_db_config()
        assert db_config
        connection = Connection(db_config.path)
        cursor = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%';")
        table_names = [table_name[0] for table_name in cursor.fetchall()]
        for table_name in table_names:
            if table_name not in [table_config.name for table_config in db_config.table_configs]:
                table_config = TableConfig(db_config.path, table_name)
                db_config.table_configs.append(table_config)

    def __str__(self):
        return json.dumps(self, default=vars, indent=4)

    def _save(self):
        D = json.loads(str(self))
        write(D, self._save_path)

    def set_active_db_path(self, db_path: str):
        possible_db_paths = [db_config.path for db_config in self.db_configs]
        if db_path not in possible_db_paths:
            raise Exception(f"Invalid db_path: {db_path}")

        self.active_db_path = db_path
        self._refresh_table_configs()
        self._save()

    def set_active_table(self, table_name):
        db_config = self._get_active_db_config()
        if not db_config:
            raise Exception("No active db_config")
        self._refresh_table_configs()
        if table_name not in [table_config.name for table_config in db_config.table_configs]:
            raise Exception(f"Invalid table_name: {table_name}")
        db_config.active_table_name = table_name
        self._save()
    
    def get_active_table_config(self):
        db_config = self._get_active_db_config()
        if not db_config:
            raise Exception("No active db_config")
        return next(table_config for table_config in db_config.table_configs if table_config.name == db_config.active_table_name)

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

def main():
    state_id = 1
    state = State(state_id)

    db_path = state.db_configs[0].path
    state.set_active_db_path(db_path)
    table_name = "items"
    state.set_active_table(table_name)
    table_config = state.get_active_table_config()

    state.set_active_db_path("/home/vivek/hateoas/data/main.db")
    table_name = "sequences"
    state.set_active_table(table_name)

    state.print_tree()
    # print(state)
    # ic(table_config)

if __name__ == "__main__":
    with handler():
        main()


