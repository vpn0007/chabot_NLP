from flask import Flask, render_template, request, jsonify, session
import mysql.connector
from typing import List, Dict, Any, Optional
from langchain_ollama import OllamaLLM
import json
import webbrowser
import threading
import time
import sys
import subprocess

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# Global SQL chatbot instance
sql_chatbot = None



class SQLQueryChatbot:
    def __init__(self, db_config: Dict[str, Any] = None):
        """
        Initialize the SQL Query Chatbot for MySQL
        
        Args:
            db_config: MySQL connection configuration dictionary
        """
        self.db_type = "mysql"
        self.db_config = db_config or {}
        self.llm = OllamaLLM(model="llama3.1", temperature=0.1)
        self.db_schema = None
        self.table_info = {}
        self.connection = None
        self.conversation_history = []  # Store conversation history for context
        
        # Initialize database connection and get schema
        if self.db_config:
            self._initialize_database()
    
    def _get_connection(self):
        """Get MySQL database connection"""
        try:
            print(f"🐬 Attempting MySQL connection to host: {self.db_config.get('host', 'unknown')}")
            print(f"🐬 User: {self.db_config.get('user', 'unknown')}, Port: {self.db_config.get('port', 'unknown')}")
            print(f"🐬 Database: {self.db_config.get('database', 'unknown')}")
            return mysql.connector.connect(**self.db_config)
        except Exception as e:
            print(f"❌ Error connecting to MySQL database: {str(e)}")
            print("🐬 MySQL connection troubleshooting:")
            print("   - Check if MySQL server is running")
            print("   - Verify username and password")
            print("   - Ensure database exists")
            print("   - Check network connectivity (port 3306)")
            return None
    
    def _initialize_database(self):
        """Initialize MySQL database connection and extract schema information"""
        try:
            self.connection = self._get_connection()
            if not self.connection:
                return
            
            cursor = self.connection.cursor()
            
            # Get all table names for MySQL
            cursor.execute("SHOW TABLES")
            tables = cursor.fetchall()
            
            self.db_schema = {}
            for table in tables:
                table_name = table[0]  # MySQL returns just the table name
                
                # Get table structure
                cursor.execute(f"DESCRIBE {table_name}")
                columns = cursor.fetchall()
                
                table_info = []
                for col in columns:
                    col_info = {
                        'name': col[0],
                        'type': col[1],
                        'null': col[2],
                        'key': col[3] if len(col) > 3 else None,
                        'default': col[4] if len(col) > 4 else None,
                        'extra': col[5] if len(col) > 5 else None
                    }
                    table_info.append(col_info)
                
                self.db_schema[table_name] = table_info
                
                # Get sample data for context
                cursor.execute(f"SELECT * FROM {table_name} LIMIT 3")
                sample_data = cursor.fetchall()
                if sample_data:
                    self.table_info[table_name] = {
                        'columns': table_info,
                        'sample_data': sample_data
                    }
            
            cursor.close()
            print(f"✅ Database schema loaded: {len(self.db_schema)} tables found")
                
        except Exception as e:
            print(f"❌ Error initializing database: {str(e)}")
            self.db_schema = {}
    
    def _create_system_prompt(self) -> str:
        """Create a comprehensive system prompt for SQL generation"""
        schema_info = ""
        if self.db_schema:
            schema_info = "Database Schema:\n"
            for table_name, columns in self.db_schema.items():
                schema_info += f"\nTable: {table_name}\n"
                for col in columns:
                    # MySQL columns have different structure
                    null_marker = " NOT NULL" if col['null'] == 'NO' else ""
                    schema_info += f"  - {col['name']}: {col['type']}{null_marker}\n"
                
                # Add sample data if available
                if table_name in self.table_info:
                    sample_data = self.table_info[table_name]['sample_data']
                    if sample_data:
                        schema_info += f"  Sample data: {sample_data[:2]}\n"
        
        return f"""You are an expert SQL query generator for MYSQL databases. Your task is to convert English language queries into accurate, executable MySQL SQL queries.

{schema_info}

CRITICAL RULE - BACKTICKS FOR RESERVED WORDS:
- Use backticks (`) around table or column names ONLY if they are MySQL reserved words
- Generally write table names directly: "SELECT * FROM users;"
- Use backticks for reserved words: "SELECT `order`, `group` FROM `table`;"
- Most common names don't need backticks: "SELECT name, age FROM customers;"

CRITICAL RULE - TABLE ALIAS CONSISTENCY:
- ALWAYS use consistent table aliases between FROM clause and SELECT clause
- Define table aliases in FROM clause FIRST, then reference them in SELECT
- NEVER reference an alias in SELECT that is not defined in FROM clause
- Use meaningful aliases: PC for PATIENT_CHRONICDISEASE, PA for PATIENT_ALLERGY, D for DIMDISEASE
- Example: FROM PATIENT_CHRONICDISEASE PC → SELECT PC.CHRONICDISEASEID (NOT PD.CHRONICDISEASEID)

JOIN RULES:
- When joining multiple tables, use clear table aliases
- Always define aliases in FROM clause before using them in SELECT
- Ensure JOIN conditions use the correct table aliases
- Avoid unnecessary self-joins unless explicitly requested
- Use INNER JOIN for standard relationships, LEFT JOIN for optional relationships

CRITICAL JOIN LOGIC RULES:
- ALWAYS think about the logical relationship between tables before joining
- NEVER join tables on fields that don't have a logical relationship
- Patients are NOT diseases - don't join PATIENT_ID = DISEASE_ID
- Use bridge tables to connect related entities (e.g., PATIENT_CHRONICDISEASE connects patients to diseases)
- Understand the data model: Patient → Bridge Table → Disease (not Patient → Disease directly)

BRIDGE TABLE PATTERNS:
- Patient → PATIENT_CHRONICDISEASE → DIMDISEASE (for chronic conditions)
- Patient → PATIENT_ALLERGY → DIMDISEASE (for allergies)
- Encounter → BRIDGE_ENCOUNTERDOCTOR → Doctor (for doctor assignments)
- Always go through the bridge table, never skip it

CORRECT JOIN PATTERNS:
- Patient to Disease: JOIN PATIENT_CHRONICDISEASE PC ON P.PATIENT_ID = PC.PATIENT_ID, THEN JOIN DIMDISEASE D ON PC.CHRONICDISEASEID = D.DISEASE_ID
- Patient to Allergy: JOIN PATIENT_ALLERGY PA ON P.PATIENT_ID = PA.PATIENT_ID, THEN JOIN DIMDISEASE D ON PA.ALLERGYID = D.DISEASE_ID
- Never: JOIN DIMDISEASE D ON P.PATIENT_ID = D.DISEASE_ID (this makes no sense!)

IMPORTANT RULES:
1. Generate ONLY the SQL query, no explanations or additional text
2. Use MySQL SQL syntax (NOT Snowflake, SQL Server, or Oracle syntax)
3. Use LIMIT for limiting results (NOT TOP)
4. Include appropriate JOINs when multiple tables are referenced
5. Use table aliases for clarity when joining multiple tables
6. Always include a semicolon at the end
7. If the query is ambiguous, ask for clarification
8. Use appropriate aggregate functions (COUNT, SUM, AVG, etc.) when needed
9. Include WHERE clauses for filtering when specified
10. Use ORDER BY when sorting is mentioned
11. Use LIMIT when "top N" or "first N" is mentioned
12. If user asks for "all" or "every" or doesn't specify a limit, don't add LIMIT
13. Only add LIMIT when user explicitly requests a specific number of rows
14. For queries like "show me all data" or "get every row", use SELECT * FROM table; (no LIMIT)
15. For queries like "show me 10 rows" or "get first 5", use SELECT * FROM table LIMIT 10;

MYSQL-SPECIFIC RULES:
- Use LIMIT instead of TOP: "SELECT * FROM table LIMIT 10;" (NOT "SELECT TOP 10 * FROM table;")
- Use backticks (`) only for reserved words: "SELECT `order` FROM `table`;"
- Use proper MySQL schema notation: "database.table" or just "table"
- Use MySQL-specific data types: VARCHAR, INT, DATETIME, TEXT, etc.
- Use double quotes (") for string literals, single quotes (') also work

MYSQL DATE FUNCTIONS (USE THESE, NOT Snowflake or PostgreSQL functions):
- For age calculation: TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) AS age
- For date parts: YEAR(date_column), MONTH(date_column), DAY(date_column)
- For date arithmetic: DATE_ADD(date_column, INTERVAL 1 YEAR), DATE_SUB(date_column, INTERVAL 3 MONTH)
- For date differences: DATEDIFF(end_date, start_date) AS days, TIMESTAMPDIFF(MONTH, start_date, end_date) AS months
- For current date/time: CURDATE(), NOW(), CURTIME()
- For date formatting: DATE_FORMAT(date_column, '%Y-%m-%d'), STR_TO_DATE('2024-01-01', '%Y-%m-%d')
- For date extraction: EXTRACT(MONTH FROM date_column), EXTRACT(YEAR FROM date_column)

SNOWFLAKE FUNCTIONS TO AVOID (NOT AVAILABLE IN MYSQL):
- ❌ CURRENT_DATE() function - use CURDATE() instead
- ❌ DATEADD() function - use DATE_ADD() instead
- ❌ DATE_TRUNC() function - use DATE_FORMAT() with appropriate format instead
- ❌ TO_CHAR() function - use DATE_FORMAT() instead

CORRECT EXAMPLES:
- "Show me all employees" → "SELECT * FROM employees;" (no LIMIT)
- "Show first 10 rows" → "SELECT * FROM table LIMIT 10;"
- "Show me 5 rows" → "SELECT * FROM table LIMIT 5;"
- "Count users in each department" → "SELECT department, COUNT(*) as user_count FROM users GROUP BY department;"
- "Find customers who made purchases in 2024" → "SELECT * FROM customers WHERE customer_id IN (SELECT DISTINCT customer_id FROM orders WHERE YEAR(order_date) = 2024);"
- "Get all data from disease table" → "SELECT * FROM disease;" (no LIMIT)

MYSQL-SPECIFIC EXAMPLES:
- "Calculate age from birth date" → "SELECT TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) AS age FROM users;"
- "Get patients with age calculation" → "SELECT patient_id, TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) AS age FROM patients;"
- "Date arithmetic - add 1 year" → "SELECT DATE_ADD(start_date, INTERVAL 1 YEAR) AS next_year FROM events;"
- "Date difference in months" → "SELECT TIMESTAMPDIFF(MONTH, start_date, end_date) AS months_between FROM projects;"
- "Format date as string" → "SELECT DATE_FORMAT(created_date, '%Y-%m-%d') AS formatted_date FROM orders;"

CORRECT JOIN EXAMPLES:
- "Patient ID and chronic disease from patient chronic disease and dimdisease tables" →
  "SELECT PC.PATIENT_ID, PC.CHRONICDISEASEID, D.ADMISSION_DIAGNOSIS 
   FROM PATIENT_CHRONICDISEASE PC 
   JOIN DIMDISEASE D ON PC.CHRONICDISEASEID = D.DISEASE_ID;"

- "Patient ID and chronic disease with disease name from multiple tables" →
  "SELECT P.PATIENT_ID, PC.CHRONICDISEASEID, D.DISEASE_TYPE, D.DISEASE_SEVERITY
   FROM PATIENT_CHRONICDISEASE PC 
   JOIN PATIENT_ALLERGY PA ON PC.PATIENT_ID = PA.PATIENT_ID
   JOIN DIMDISEASE D ON PA.ALLERGYID = D.DISEASE_ID
   JOIN DIMPATIENT P ON PC.PATIENT_ID = P.PATIENT_ID;"

BRIDGE TABLE JOIN EXAMPLES:
- "Patient demographics with chronic disease count by disease type" →
  "SELECT D.DISEASE_TYPE, COUNT(DISTINCT P.PATIENT_ID) AS PATIENT_COUNT
   FROM DIMPATIENT P
   LEFT JOIN PATIENT_CHRONICDISEASE PC ON P.PATIENT_ID = PC.PATIENT_ID
   LEFT JOIN DIMDISEASE D ON PC.CHRONICDISEASEID = D.DISEASE_ID
   GROUP BY D.DISEASE_TYPE;"

- "Patient allergy analysis with disease details" →
  "SELECT P.PATIENT_ID, P.FIRST_NAME, D.DISEASE_TYPE, D.DISEASE_SEVERITY
   FROM DIMPATIENT P
   LEFT JOIN PATIENT_ALLERGY PA ON P.PATIENT_ID = PA.PATIENT_ID
   LEFT JOIN DIMDISEASE D ON PA.ALLERGYID = D.DISEASE_ID;"

INCORRECT EXAMPLES (UNNECESSARY BACKTICKS - DON'T DO THIS):
- ❌ "SELECT * FROM \`users\`;" (unless 'users' is a reserved word)
- ❌ "SELECT \`name\`, \`age\` FROM \`customers\`;" (unless these are reserved words)
- ❌ "SELECT * FROM \`table\` LIMIT 10;" (only use backticks if needed)

INCORRECT MYSQL EXAMPLES (DON'T DO THIS):
- ❌ "SELECT DATEDIFF('YEAR', birth_date, CURRENT_DATE()) AS age" - use TIMESTAMPDIFF(YEAR, birth_date, CURDATE()) instead
- ❌ "SELECT CURRENT_TIMESTAMP()" - use NOW() instead (though both work)
- ❌ "SELECT DATEADD('YEAR', 1, birth_date)" - use DATE_ADD(birth_date, INTERVAL 1 YEAR) instead
- ❌ "SELECT TO_CHAR(date_column, 'YYYY-MM-DD')" - use DATE_FORMAT(date_column, '%Y-%m-%d') instead
- ❌ "SELECT * FROM table LIMIT 10 OFFSET 20" - use "SELECT * FROM table LIMIT 20, 10" for MySQL < 8.0

INCORRECT JOIN EXAMPLES (DON'T DO THIS):
- ❌ "SELECT PD.CHRONICDISEASEID" when PD alias is not defined
- ❌ "SELECT T1.PATIENT_ID, T2.CHRONICDISEASEID" when T2 is not defined
- ❌ Unnecessary self-joins: "JOIN PATIENT_CHRONICDISEASE T3 ON T1.PATIENT_ID = T3.PATIENT_ID"

INCORRECT JOIN LOGIC (DON'T DO THIS):
- ❌ "JOIN DIMDISEASE D ON P.PATIENT_ID = D.DISEASE_ID" - Patients are NOT diseases!
- ❌ "JOIN PATIENT_CHRONICDISEASE PC ON P.PATIENT_ID = PC.DISEASE_ID" - Wrong field relationship!
- ❌ "JOIN PATIENT_ALLERGY PA ON P.PATIENT_ID = PA.DISEASE_ID" - Wrong field relationship!
- ❌ Skipping bridge tables: "JOIN DIMPATIENT P ON DIMDISEASE D" - No logical connection!
- ❌ Joining unrelated fields: "JOIN table1 ON table1.field1 = table2.field2" without logical relationship

Remember: Generate ONLY the SQL query, nothing else. NEVER use backticks (`) around table names. Write table names directly. ALWAYS ensure table aliases are consistent between FROM and SELECT clauses."""
    
    def _create_query_prompt(self, english_query: str) -> str:
        """Create a prompt for converting English to SQL"""
        system_prompt = self._create_system_prompt()
        conversation_context = self.get_conversation_context()
        
        return f"""{system_prompt}{conversation_context}

English Query: {english_query}

SQL Query:"""
    
    def generate_sql(self, english_query: str) -> str:
        """
        Generate SQL query from English language query
        
        Args:
            english_query: Natural language query in English
            
        Returns:
            Generated SQL query string
        """
        try:
            # Create the prompt
            prompt = self._create_query_prompt(english_query)
            
            # Generate response using llama3.1
            response = self.llm.invoke(prompt)
            
            print(f"🔍 DEBUG: Raw LLM response: {response}")
            
            # Clean up the response
            sql_query = response.strip()
            
            # Remove any markdown formatting if present
            if sql_query.startswith("```sql"):
                sql_query = sql_query[6:]
            if sql_query.endswith("```"):
                sql_query = sql_query[:-3]
            
            sql_query = sql_query.strip()
            
            # Note: Keep backticks for MySQL reserved words if needed
            # sql_query = sql_query.replace('`', '')  # Commented out for MySQL compatibility
            
            print(f"🔍 DEBUG: Cleaned SQL query: {sql_query}")
            
            # Ensure it ends with semicolon
            if not sql_query.endswith(';'):
                sql_query += ';'
            
            return sql_query
            
        except Exception as e:
            print(f"❌ Error in generate_sql: {str(e)}")
            print(f"❌ Prompt used: {prompt[:200]}...")
            return None
    
    def validate_sql(self, sql_query: str) -> Dict[str, Any]:
        """
        Validate the generated SQL query
        
        Args:
            sql_query: SQL query to validate
            
        Returns:
            Dictionary with validation results
        """
        try:
            if not self.connection:
                return {"valid": False, "error": "No database connection available"}
            
            # Skip validation for certain MySQL commands that don't work with EXPLAIN
            skip_validation_commands = ['SHOW TABLES', 'SHOW DATABASES', 'DESCRIBE', 'SHOW CREATE TABLE', 'SHOW COLUMNS']
            if any(cmd in sql_query.upper() for cmd in skip_validation_commands):
                return {
                    "valid": True,
                    "message": "MySQL command (skipped validation)"
                }
            
            cursor = self.connection.cursor()
            
            # For MySQL, we can use EXPLAIN to validate
            cursor.execute(f"EXPLAIN {sql_query}")
            plan = cursor.fetchall()
            
            cursor.close()
            
            return {
                "valid": True,
                "plan": plan,
                "message": "SQL query is syntactically valid"
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": str(e),
                "message": "SQL query has syntax errors"
            }
    
    def execute_query(self, sql_query: str, limit: int = None, offset: int = None, get_total_count: bool = False) -> Dict[str, Any]:
        """
        Execute the SQL query and return results with optional pagination
        
        Args:
            sql_query: SQL query to execute
            limit: Maximum number of rows to return (None = no limit)
            offset: Number of rows to skip (for pagination)
            get_total_count: Whether to return total count of all records
            
        Returns:
            Dictionary with execution results
        """
        try:
            if not self.connection:
                return {"error": "No database connection available"}
            
            cursor = self.connection.cursor()
            
            # Handle database-specific commands
            db_commands = ['SHOW TABLES', 'SHOW DATABASES', 'DESCRIBE', 'SHOW CREATE TABLE']
            is_db_command = any(cmd in sql_query.upper() for cmd in db_commands)
            
            total_count = None
            
            # Get total count if requested and it's a SELECT query
            if (get_total_count and 
                sql_query.strip().upper().startswith("SELECT") and 
                not is_db_command):
                # Create a count query from the original query
                count_query = f"SELECT COUNT(*) FROM ({sql_query.rstrip(';')}) AS count_subquery;"
                try:
                    cursor.execute(count_query)
                    total_count = cursor.fetchone()[0]
                except Exception as e:
                    print(f"Warning: Could not get total count: {e}")
                    total_count = None
            
            # Add pagination if requested and it's a SELECT query (but not a database command)
            paginated_query = sql_query
            if (sql_query.strip().upper().startswith("SELECT") and 
                "LIMIT" not in sql_query.upper() and 
                not is_db_command):
                
                # Add LIMIT and OFFSET for pagination
                if limit is not None:
                    if offset is not None:
                        paginated_query = sql_query.rstrip(';') + f" LIMIT {limit} OFFSET {offset};"
                    else:
                        paginated_query = sql_query.rstrip(';') + f" LIMIT {limit};"
            
            cursor.execute(paginated_query)
            
            # Get column names
            columns = [description[0] for description in cursor.description] if cursor.description else []
            
            # Get results
            results = cursor.fetchall()
            
            cursor.close()
            
            response = {
                "success": True,
                "columns": columns,
                "results": results,
                "row_count": len(results),
                "sql_executed": paginated_query
            }
            
            if total_count is not None:
                response["total_count"] = total_count
            
            return response
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "sql_attempted": sql_query
            }
    
    def add_to_conversation(self, user_query: str, sql_query: str, result: Dict[str, Any]):
        """Add query and result to conversation history"""
        self.conversation_history.append({
            'user_query': user_query,
            'sql_query': sql_query,
            'result': result,
            'timestamp': None  # Could add timestamp if needed
        })
        
        # Keep only last 10 conversations to avoid memory issues
        if len(self.conversation_history) > 10:
            self.conversation_history = self.conversation_history[-10:]
    
    def get_conversation_context(self) -> str:
        """Get conversation context for follow-up queries"""
        if not self.conversation_history:
            return ""
        
        context = "\n\nPrevious queries and results:\n"
        for i, conv in enumerate(self.conversation_history[-3:], 1):  # Last 3 conversations
            context += f"\n{i}. User: {conv['user_query']}\n"
            context += f"   SQL: {conv['sql_query']}\n"
            if conv['result'].get('success'):
                context += f"   Result: {conv['result']['row_count']} rows returned\n"
            else:
                context += f"   Result: Error - {conv['result'].get('error', 'Unknown error')}\n"
        
        return context
    
    def clear_conversation(self):
        """Clear conversation history"""
        self.conversation_history = []
    
    def close_connection(self):
        """Close the database connection"""
        if self.connection:
            self.connection.close()
            self.connection = None

@app.route('/')
def index():
    """Main page - redirect to SQL interface"""
    return render_template('sql.html')

@app.route('/sql')
def sql_interface():
    """SQL Query Interface"""
    return render_template('sql.html')



@app.route('/api/sql/init', methods=['POST'])
def init_sql_chatbot():
    """Initialize SQL chatbot with database connection"""
    global sql_chatbot
    
    try:
        # Import MySQL configuration
        from config import MYSQL_CONFIG
        
        # Use MySQL configuration
        db_type = "mysql"
        db_config = MYSQL_CONFIG
        
        print(f"🔍 DEBUG: Using MySQL database configuration")
        print("🐬 Using MySQL database configuration")
            
    except ImportError:
        return jsonify({'error': 'config.py not found. Please create it with your database credentials.'}), 500
    
    try:
        print(f"🔧 Initializing SQLQueryChatbot with db_type: {db_type}")
        print(f"🔧 Config keys: {list(db_config.keys())}")
        
        sql_chatbot = SQLQueryChatbot(db_config=db_config)
        
        if not sql_chatbot.connection:
            error_msg = f'Failed to connect to {db_type} database. Please check your credentials.'
            print(f"❌ {error_msg}")
            return jsonify({'error': error_msg}), 500
        
        return jsonify({
            'success': True,
            'message': 'SQL chatbot initialized successfully',
            'tables': list(sql_chatbot.db_schema.keys()) if sql_chatbot.db_schema else []
        })
        
    except Exception as e:
        return jsonify({'error': f'Error initializing SQL chatbot: {str(e)}'}), 500

@app.route('/api/sql/query', methods=['POST'])
def process_sql_query():
    """Process English query and return SQL + results"""
    global sql_chatbot
    
    if not sql_chatbot:
        return jsonify({'error': 'SQL chatbot not initialized. Please initialize first.'}), 400
    
    data = request.get_json()
    english_query = data.get('query', '').strip()
    
    if not english_query:
        return jsonify({'error': 'No query provided'}), 400
    
    try:
        # Get pagination parameters from request
        offset = data.get('offset', 0)
        limit = data.get('limit')
        get_total_count = data.get('get_total_count', False)
        
        # Generate SQL from English query
        sql_query = sql_chatbot.generate_sql(english_query)
        
        # Check if SQL generation failed
        if sql_query is None:
            return jsonify({
                'english_query': english_query,
                'error': 'Failed to generate SQL query. Please try rephrasing your question.'
            }), 400
        
        # Validate SQL
        validation = sql_chatbot.validate_sql(sql_query)
        
        if not validation["valid"]:
            return jsonify({
                'english_query': english_query,
                'sql_query': sql_query,
                'valid': False,
                'error': validation.get('error', 'Unknown validation error'),
                'message': validation.get('message', 'SQL validation failed')
            })
        
        # Execute query with pagination parameters
        result = sql_chatbot.execute_query(sql_query, limit=limit, offset=offset, get_total_count=get_total_count)
        
        # Add to conversation history
        sql_chatbot.add_to_conversation(english_query, sql_query, result)
        
        if result.get("success"):
            response = {
                'english_query': english_query,
                'sql_query': sql_query,
                'valid': True,
                'success': True,
                'columns': result['columns'],
                'results': result['results'],
                'row_count': result['row_count'],
                'sql_executed': result['sql_executed'],
                'conversation_count': len(sql_chatbot.conversation_history)
            }
            
            # Add total count if available
            if 'total_count' in result:
                response['total_count'] = result['total_count']
            
            return jsonify(response)
        else:
            return jsonify({
                'english_query': english_query,
                'sql_query': sql_query,
                'valid': True,
                'success': False,
                'error': result.get('error', 'Unknown execution error'),
                'sql_attempted': result.get('sql_attempted', sql_query),
                'conversation_count': len(sql_chatbot.conversation_history)
            })
            
    except Exception as e:
        return jsonify({
            'english_query': english_query,
            'error': f'Error processing query: {str(e)}'
        }), 500

@app.route('/api/sql/schema')
def get_database_schema():
    """Get database schema information"""
    global sql_chatbot
    
    if not sql_chatbot:
        return jsonify({'error': 'SQL chatbot not initialized'}), 400
    
    return jsonify({
        'schema': sql_chatbot.db_schema,
        'tables': list(sql_chatbot.db_schema.keys()) if sql_chatbot.db_schema else []
    })

@app.route('/api/sql/conversation/history')
def get_conversation_history():
    """Get conversation history"""
    global sql_chatbot
    
    if not sql_chatbot:
        return jsonify({'error': 'SQL chatbot not initialized'}), 400
    
    return jsonify({
        'history': sql_chatbot.conversation_history,
        'count': len(sql_chatbot.conversation_history)
    })

@app.route('/api/sql/conversation/clear', methods=['POST'])
def clear_conversation():
    """Clear conversation history"""
    global sql_chatbot
    
    if not sql_chatbot:
        return jsonify({'error': 'SQL chatbot not initialized'}), 400
    
    sql_chatbot.clear_conversation()
    return jsonify({
        'success': True,
        'message': 'Conversation history cleared'
    })

def open_browser():
    """Open browser after a short delay"""
    try:
        time.sleep(3)  # Wait for Flask to start
        print("🌐 Opening browser automatically...")
        
        # Try to open specific browsers in order of preference
        browsers_opened = False
        
        try:
            # Method 1: Try to open with specific browser names
            if sys.platform.startswith('darwin'):  # macOS
                # Try Safari first, then Chrome
                try:
                    result = subprocess.run(['open', '-a', 'Safari', 'http://localhost:5004'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print("✅ Opened with Safari")
                        browsers_opened = True
                    else:
                        print(f"⚠️  Safari failed: {result.stderr}")
                except Exception as e:
                    print(f"⚠️  Safari error: {e}")
                
                if not browsers_opened:
                    try:
                        result = subprocess.run(['open', '-a', 'Google Chrome', 'http://localhost:5004'], 
                                              capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            print("✅ Opened with Google Chrome")
                            browsers_opened = True
                        else:
                            print(f"⚠️  Chrome failed: {result.stderr}")
                    except Exception as e:
                        print(f"⚠️  Chrome error: {e}")
                
                if not browsers_opened:
                    try:
                        result = subprocess.run(['open', 'http://localhost:5004'], 
                                              capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            print("✅ Opened with default browser")
                            browsers_opened = True
                        else:
                            print(f"⚠️  Default browser failed: {result.stderr}")
                    except Exception as e:
                        print(f"⚠️  Default browser error: {e}")
                        
            elif sys.platform.startswith('win'):   # Windows
                # Try Edge first, then Chrome
                try:
                    result = subprocess.run(['start', 'msedge', 'http://localhost:5004'], 
                                          shell=True, capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print("✅ Opened with Microsoft Edge")
                        browsers_opened = True
                    else:
                        print(f"⚠️  Edge failed: {result.stderr}")
                except Exception as e:
                    print(f"⚠️  Edge error: {e}")
                
                if not browsers_opened:
                    try:
                        result = subprocess.run(['start', 'chrome', 'http://localhost:5004'], 
                                              shell=True, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            print("✅ Opened with Google Chrome")
                            browsers_opened = True
                        else:
                            print(f"⚠️  Chrome failed: {result.stderr}")
                    except Exception as e:
                        print(f"⚠️  Chrome error: {e}")
                
                if not browsers_opened:
                    try:
                        result = subprocess.run(['start', 'http://localhost:5004'], 
                                              shell=True, capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            print("✅ Opened with default browser")
                            browsers_opened = True
                        else:
                            print(f"⚠️  Default browser failed: {result.stderr}")
                    except Exception as e:
                        print(f"⚠️  Default browser error: {e}")
                        
            else:  # Linux
                try:
                    result = subprocess.run(['google-chrome', 'http://localhost:5004'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        print("✅ Opened with Google Chrome")
                        browsers_opened = True
                    else:
                        print(f"⚠️  Chrome failed: {result.stderr}")
                except Exception as e:
                    print(f"⚠️  Chrome error: {e}")
                
                if not browsers_opened:
                    try:
                        result = subprocess.run(['xdg-open', 'http://localhost:5004'], 
                                              capture_output=True, text=True, timeout=5)
                        if result.returncode == 0:
                            print("✅ Opened with default browser")
                            browsers_opened = True
                        else:
                            print(f"⚠️  Default browser failed: {result.stderr}")
                    except Exception as e:
                        print(f"⚠️  Default browser error: {e}")
            
        except Exception as e:
            print(f"⚠️  System-specific browser failed: {e}")
            
        # Fallback to webbrowser module if system-specific methods failed
        if not browsers_opened:
            print("🔄 Trying webbrowser module fallback...")
            try:
                webbrowser.open('http://localhost:5004')
                print("✅ Opened with webbrowser module")
                browsers_opened = True
            except Exception as e:
                print(f"⚠️  Webbrowser module failed: {e}")
        
        if browsers_opened:
            print("✅ Browser opened successfully!")
        else:
            print("❌ All browser opening methods failed")
            print("🌐 Please manually open: http://localhost:5004")
            print("💡 You can also use the 'Open in New Tab' button on the page")
        
    except Exception as e:
        print(f"⚠️  Could not open browser automatically: {e}")
        print("🌐 Please manually open: http://localhost:5004")
        print("💡 You can also use the 'Open in New Tab' button on the page")

if __name__ == '__main__':
    print("Starting SQL Query Chatbot...")
    print("Make sure Ollama is running with the llama3.1 model!")
    print("You can start Ollama with: ollama run llama3.1")
    
    # Start browser opening in a separate thread
    browser_thread = threading.Thread(target=open_browser, daemon=False)
    browser_thread.start()
    
    print("🚀 Starting Flask server...")
    print("🌐 The web interface will be available at: http://localhost:5004")
    print("📱 Browser should open automatically, but you can also manually navigate to the URL")
    
    try:
        app.run(debug=False, host='0.0.0.0', port=5004)
    except KeyboardInterrupt:
        print("\n\n👋 SQL Query Chatbot stopped. Goodbye!")
    except Exception as e:
        print(f"\n❌ Error running Flask app: {e}")

