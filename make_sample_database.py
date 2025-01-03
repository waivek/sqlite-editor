from box import Timer
timer = Timer()
from box import handler, ic, ib , rel2abs, Connection
from lorem import paragraph
import os
import textwrap

def main():
    # Remove existing database if it exists
    db_path = rel2abs("data/sample.db")
    if os.path.exists(db_path):
        os.remove(db_path)

    # Long lorem ipsum text
    lorem_text = paragraph()
    
    # Short text
    short_text = "Hello, world!"
    
    # Normal length URL
    sample_url = "https://example.com/blog/article-123"
    
    # Really long URL
    long_url = "https://example.com/very/long/path/with/many/segments/and/parameters?id=12345&user=john&session=abc123xyz789&category=main&subcategory=items&filter=active&sort=desc&page=1&limit=50&format=json"
    
    # Unix epoch timestamp (e.g., January 1, 2024 00:00:00 UTC)
    epoch_date = 1704067200
    
    # Sample number
    sample_number = 42
    
    connection = Connection("data/sample.db")
    
    # Create table if it doesn't exist
    connection.execute("""
        CREATE TABLE IF NOT EXISTS samples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            text_content TEXT,
            url TEXT,
            date_epoch INTEGER,
            number INTEGER
        )
    """)
    
    # Wrapped lorem ipsum text (80 characters per line)
    wrapped_lorem = textwrap.fill(paragraph(), width=80)
    print(wrapped_lorem)
    
    # Insert two rows with different text lengths and URLs
    connection.execute("""
        INSERT INTO samples (text_content, url, date_epoch, number)
        VALUES (?, ?, ?, ?)
    """, (short_text, sample_url, epoch_date, sample_number))
    
    connection.execute("""
        INSERT INTO samples (text_content, url, date_epoch, number)
        VALUES (?, ?, ?, ?)
    """, (lorem_text, long_url, epoch_date, sample_number))
    
    # Insert third row with wrapped lorem ipsum
    connection.execute("""
        INSERT INTO samples (text_content, url, date_epoch, number)
        VALUES (?, ?, ?, ?)
    """, (wrapped_lorem, sample_url, epoch_date, sample_number))
    
    connection.commit()

if __name__ == "__main__":
    with handler():
        main()

# run.vim: term python %
