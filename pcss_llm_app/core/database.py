import sqlite3
import datetime
from pathlib import Path

class DatabaseManager:
    def __init__(self, db_path=None):
        if db_path is None:
            project_dir = Path(__file__).resolve().parent.parent.parent
            self.db_path = str(project_dir / "conversations.db")
        else:
            self.db_path = db_path
        self._init_db()

    def _get_connection(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Conversations table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                created_at TIMESTAMP,
                model TEXT,
                mode TEXT,
                agent_profile TEXT,
                scratchpad TEXT
            )
        ''')
        
        # Messages table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conversation_id INTEGER,
                role TEXT,
                content TEXT,
                timestamp TIMESTAMP,
                rating INTEGER DEFAULT 0,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id)
            )
        ''')
        
        # Comprehensive migration check for existing 'messages' table
        try:
            # Check for missing columns (rating)
            cursor.execute("PRAGMA table_info(messages)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'rating' not in columns:
                cursor.execute('ALTER TABLE messages ADD COLUMN rating INTEGER DEFAULT 0')
        except sqlite3.OperationalError:
            # Table might not exist yet if CREATE TABLE IF NOT EXISTS failed
            # (which it shouldn't, but we be defensive)
            pass
            
        # Comprehensive migration check for existing 'conversations' table
        try:
            cursor.execute("PRAGMA table_info(conversations)")
            columns = [col[1] for col in cursor.fetchall()]
            if 'agent_profile' not in columns:
                cursor.execute('ALTER TABLE conversations ADD COLUMN agent_profile TEXT')
            if 'scratchpad' not in columns:
                cursor.execute('ALTER TABLE conversations ADD COLUMN scratchpad TEXT')
        except sqlite3.OperationalError:
            pass
        
        conn.commit()
        conn.close()

    def create_conversation(self, title, model, mode="chat", agent_profile=""):
        conn = self._get_connection()
        cursor = conn.cursor()
        created_at = datetime.datetime.now()
        cursor.execute(
            'INSERT INTO conversations (title, created_at, model, mode, agent_profile, scratchpad) VALUES (?, ?, ?, ?, ?, ?)',
            (title, created_at, model, mode, agent_profile, "")
        )
        conversation_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return conversation_id

    def add_message(self, conversation_id, role, content, rating=0):
        conn = self._get_connection()
        cursor = conn.cursor()
        timestamp = datetime.datetime.now()
        cursor.execute(
            'INSERT INTO messages (conversation_id, role, content, timestamp, rating) VALUES (?, ?, ?, ?, ?)',
            (conversation_id, role, content, timestamp, rating)
        )
        msg_id = cursor.lastrowid
        conn.commit()
        conn.close()
        return msg_id

    def get_conversations(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM conversations ORDER BY created_at DESC')
        rows = cursor.fetchall()
        conn.close()
        return rows

    def get_conversation(self, conversation_id):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, title, created_at, model, mode, agent_profile, scratchpad FROM conversations WHERE id = ?', (conversation_id,))
        row = cursor.fetchone()
        conn.close()
        return row

    def get_messages(self, conversation_id):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, role, content, timestamp, rating FROM messages WHERE conversation_id = ? ORDER BY timestamp ASC', (conversation_id,))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def delete_conversation(self, conversation_id):
        conn = self._get_connection()
        cursor = conn.cursor()
        # Delete messages first (cascade simulation)
        cursor.execute('DELETE FROM messages WHERE conversation_id = ?', (conversation_id,))
        cursor.execute('DELETE FROM conversations WHERE id = ?', (conversation_id,))
        conn.commit()
        conn.close()

    def clear_all_conversations(self):
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('DELETE FROM messages')
        cursor.execute('DELETE FROM conversations')
        conn.commit()
        conn.close()

    def update_message_rating(self, message_id, rating):
        """Update rating for a specific message."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE messages SET rating = ? WHERE id = ?', (rating, message_id))
        conn.commit()
        conn.close()

    def get_top_rated_interactions(self, model, limit=3):
        """
        Get highly rated interactions (thumbs up) for a specific model.
        Returns pairs of (user_question, agent_response).
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # We find assistant messages with rating > 0, then find the immediately preceding user message
        query = '''
            SELECT m1.content as user_msg, m2.content as agent_msg
            FROM messages m2
            JOIN conversations c ON m2.conversation_id = c.id
            JOIN messages m1 ON m1.conversation_id = c.id AND m1.id = (
                SELECT MAX(id) FROM messages 
                WHERE conversation_id = c.id AND role = 'user' AND id < m2.id
            )
            WHERE m2.role = 'assistant' AND m2.rating > 0 AND c.model = ?
            ORDER BY m2.rating DESC, m2.timestamp DESC
            LIMIT ?
        '''
        cursor.execute(query, (model, limit))
        rows = cursor.fetchall()
        conn.close()
        return rows

    def update_conversation_scratchpad(self, conversation_id, scratchpad):
        """Persist agent's internal thought process to DB."""
        conn = self._get_connection()
        cursor = conn.cursor()
        cursor.execute('UPDATE conversations SET scratchpad = ? WHERE id = ?', (scratchpad, conversation_id))
        conn.commit()
        conn.close()
