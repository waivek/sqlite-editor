import os
from waivek import readlines, ic
import time
from waivek import rel2abs
import sys

def get_files(start_dir, depth, ignore_hidden=True, ignore_vcs=True, extensions=None):
    if extensions is None:
        extensions = ["db", "sqlite", "sqlite3"]

    files_list = []
    vcs_dirs = {'.git', '.hg', '.svn', '.bzr'}

    def recurse(current_dir, current_depth):
        if current_depth > depth:
            return
        try:
            with os.scandir(current_dir) as snandir_iterator:
                for entry in snandir_iterator:
                    if ignore_hidden and entry.name.startswith('.'):
                        continue
                    if ignore_vcs and entry.name in vcs_dirs:
                        continue
                    if entry.is_symlink():
                        continue
                    if entry.is_file() and entry.name.split('.')[-1] in extensions:
                        files_list.append(entry.path)
                    elif entry.is_dir():
                        recurse(entry.path, current_depth + 1)
        except PermissionError:
            pass

    recurse(start_dir, 1)
    return files_list

def is_sqlite_file(file_path):
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
            return header == b"SQLite format 3\x00"
    except Exception as e:
        return False

def get_db_paths(start_directory, max_depth=10, ignore_hidden_files=True, ignore_vcs_files=True, file_extensions=["db", "sqlite", "sqlite3"]):
    files = get_files(start_directory, max_depth, ignore_hidden=ignore_hidden_files, ignore_vcs=ignore_vcs_files, extensions=file_extensions)
    files = [ file for file in files if is_sqlite_file(file) ]
    return files

def all_paths_present_in_db_paths_text_file():
    db_paths = readlines("data/db_paths.txt")
    for path in db_paths:
        if not os.path.exists(path):
            return False
    return True

def update_db_paths_text_file():
    output_path = rel2abs("data/db_paths.txt")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    # if modified in the last hour, don't update
    if os.path.exists(output_path) and all_paths_present_in_db_paths_text_file():
        last_modified = os.path.getmtime(output_path)
        if time.time() - last_modified < 3600:
            return output_path
    home_dir = os.path.expanduser("~")
    db_paths = get_db_paths(home_dir, ignore_hidden_files=False)
    with open(output_path, "w") as f:
        for path in db_paths:
            f.write(path + "\n")
    return output_path

def cron():
    update_db_paths_text_file()

if __name__ == "__main__":
    from waivek import Timer
    timer = Timer()
    # path = update_db_paths_text_file()
    # lines = readlines(path)
    # for line in lines:
        # print(line)

    timer.start("get_db_paths")
    paths = get_db_paths(os.path.expanduser("~"), ignore_hidden_files=False)
    timer.print("get_db_paths")
    # for path in paths:
    #     print(path)

    sys.exit(0)
    # Example usage
    start_directory = "/home/vivek"
    max_depth = 10
    ignore_hidden_files = True
    ignore_vcs_files = True
    file_extensions = ["db", "sqlite", "sqlite3"]

    timer.start("get_files")
    file_paths = get_files(start_directory, max_depth, ignore_hidden=ignore_hidden_files, ignore_vcs=ignore_vcs_files, extensions=file_extensions)
    timer.print("get_files")
    for path in file_paths:
        print(path)

